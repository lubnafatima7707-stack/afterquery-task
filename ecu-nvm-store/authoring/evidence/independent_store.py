#!/usr/bin/env python3
"""
A second correct store, written to a different design from the reference, so the
bars can be placed against the spread of correct implementations rather than
against one implementation's score.

Where the reference keeps every live record in the active sector and compacts
everything forward on each switch, this one treats the whole device as one
circular log: records stay where they were written, the head sector carries an
index snapshot in its second page naming the location of every live block at the
moment the head opened, and reclamation copies whatever is still live out of the
oldest sector and then erases it. Mount reads the sector headers, the newest
usable snapshot and the pages of the head sector. The crash argument is
different too: a sector is erased only after its live records have been written
elsewhere, and a head whose snapshot is missing is abandoned in favour of the
previous one.

VARIANT is the authoring switch, empty as shipped. Each value it accepts removes
one piece of this design, which is how the second block of the results table was
measured: a reviewer should not have to take on trust that the pieces of a
shipped solver are load bearing.
"""
import json
import sys
import zlib

VARIANT = ""

SEC_MAGIC = b"CLOG"
SNAP_MAGIC = b"SNAP"
REC_TAG = 0x7A


def crc4(data):
    return (zlib.crc32(data) & 0xFFFFFFFF).to_bytes(4, "little")


def flags():
    return {part.strip() for part in VARIANT.split(",") if part.strip()}


class CircularStore:
    def __init__(self, cfg, stdin, stdout):
        self.inp = stdin
        self.out = stdout
        self.n_sectors = int(cfg["sectors"])
        self.n_pages = int(cfg["pages_per_sector"])
        self.page = int(cfg["page_bytes"])
        self.cost_read = float(cfg["t_read_ms"])
        self.cost_prog = float(cfg["t_program_ms"])
        self.allowance = float(cfg["tick_budget_ms"])
        self.lengths = list(cfg["blocks"])
        self.erased_page = bytes([0xFF]) * self.page
        self.spent = 0.0
        self.now = int(cfg.get("tick", 0))
        self.where = {}
        self.queue = []
        self.dead = set()
        self.head = None
        self.cursor = None
        self.gen = 0
        self.stamp = 1
        self.gens = {}
        self.job = None
        self.off = flags()
        self.early = set()

    # device -------------------------------------------------------------------

    def send(self, text):
        self.out.write("OP " + text + "\n")
        self.out.flush()
        return self.inp.readline().strip()

    def room(self, cost):
        return self.spent + cost <= self.allowance + 1e-9

    def fetch(self, sector, page):
        answer = self.send("READ %d %d" % (sector, page))
        if answer == "BUSY":
            return None
        self.spent += self.cost_read
        return bytes.fromhex(answer[5:])

    def store_page(self, sector, page, body):
        filled = body + bytes([0xFF]) * (self.page - len(body))
        answer = self.send("PROGRAM %d %d %s" % (sector, page, filled.hex()))
        if answer == "BUSY":
            return False
        self.spent += self.cost_prog
        return True

    def wipe(self, sector):
        return self.send("ERASE %d" % sector) == "OK"

    def waiting(self):
        answer = self.send("STATUS")
        return int(answer.split()[1]) if answer.startswith("BUSY") else 0

    # encodings ----------------------------------------------------------------

    def sector_page(self, gen):
        body = SEC_MAGIC + gen.to_bytes(4, "little")
        return body + crc4(body)

    def read_sector_page(self, raw):
        if raw is None or len(raw) < 12 or raw[:4] != SEC_MAGIC:
            return None
        if crc4(raw[:8]) != raw[8:12]:
            return None
        return int.from_bytes(raw[4:8], "little")

    def snapshot_page(self, table):
        body = bytearray(SNAP_MAGIC + bytes([len(self.lengths)]))
        for block in range(len(self.lengths)):
            spot = table.get(block)
            if spot is None:
                body += b"\xff\xff"
            else:
                body += ((spot[0] << 7) | spot[1]).to_bytes(2, "little")
        return bytes(body) + crc4(bytes(body))

    def read_snapshot(self, raw):
        if raw is None or len(raw) < 5 or raw[:4] != SNAP_MAGIC:
            return None
        count = raw[4]
        if count != len(self.lengths):
            return None
        end = 5 + 2 * count
        if end + 4 > self.page or crc4(raw[:end]) != raw[end:end + 4]:
            return None
        table = {}
        for block in range(count):
            packed = int.from_bytes(raw[5 + 2 * block:7 + 2 * block], "little")
            if packed == 0xFFFF:
                continue
            table[block] = (packed >> 7, packed & 0x7F, 0)
        return table

    def record_page(self, block, stamp, value):
        body = (bytes([REC_TAG, block, len(value)]) + stamp.to_bytes(4, "little")
                + value)
        return body + crc4(body)

    def read_record(self, raw):
        if raw is None or len(raw) < 11 or raw[0] != REC_TAG:
            return None
        block, size = raw[1], raw[2]
        if block >= len(self.lengths):
            return None
        if "no_crc" in self.off:
            size = min(size, self.page - 11)
        elif size > self.page - 11:
            return None
        body = raw[:7 + size]
        if "no_crc" not in self.off and crc4(body) != raw[7 + size:11 + size]:
            return None
        return block, int.from_bytes(raw[3:7], "little"), bytes(raw[7:7 + size])

    # mount --------------------------------------------------------------------

    def settled_read(self, sector, page):
        for _ in range(64):
            raw = self.fetch(sector, page)
            if raw is not None:
                return raw
        return None

    def mount(self):
        for sector in range(self.n_sectors):
            gen = self.read_sector_page(self.settled_read(sector, 0))
            if gen is not None:
                self.gens[sector] = gen
        if not self.gens:
            self.open_first()
            return
        self.gen = max(self.gens.values())
        for sector in sorted(self.gens, key=lambda s: -self.gens[s]):
            if self.replay(sector):
                self.head = sector
                return
        self.open_first()

    def replay(self, sector):
        table = None
        cursor = None
        page = 1
        while page < self.n_pages:
            raw = self.settled_read(sector, page)
            if raw == self.erased_page:
                cursor = page
                break
            snap = self.read_snapshot(raw)
            if snap is not None:
                table = snap
            else:
                found = self.read_record(raw)
                if found is not None:
                    block, stamp, _ = found
                    if table is None:
                        return False
                    table[block] = (sector, page, stamp)
                    if stamp >= self.stamp:
                        self.stamp = stamp + 1
            page += 1
        if table is None:
            if "no_head_fallback" not in self.off:
                return False
            table = {}
        self.where = table
        self.cursor = cursor
        return True

    def open_first(self):
        for sector in range(self.n_sectors):
            raw = self.settled_read(sector, 0)
            if raw == self.erased_page:
                self.gen += 1
                if self.store_page(sector, 0, self.sector_page(self.gen)):
                    if self.store_page(sector, 1, self.snapshot_page({})):
                        self.head = sector
                        self.gens[sector] = self.gen
                        self.where = {}
                        self.cursor = 2
                        return
        self.head = None
        self.cursor = None
        spare = [s for s in range(self.n_sectors) if s not in self.dead]
        if spare:
            self.job = {"step": "wipe", "target": spare[0], "after": "label"}

    # per tick -----------------------------------------------------------------

    def begin(self, tick):
        self.now = tick
        self.spent = 0.0

    def accept(self, rid, block, value):
        self.queue.append((rid, block, value))

    def serve(self, reads):
        for rid, block in reads:
            answer = None
            for item in reversed(self.queue):
                if item[1] == block:
                    answer = item[2]
                    break
            if answer is not None:
                self.out.write("VALUE %d %s\n" % (rid, answer.hex()))
                continue
            spot = self.where.get(block)
            if spot is None:
                self.out.write("VALUE %d NONE\n" % rid)
                continue
            raw = self.fetch(spot[0], spot[1])
            found = self.read_record(raw) if raw is not None else None
            if found is None or found[0] != block:
                self.out.write("VALUE %d BUSY\n" % rid)
            else:
                self.out.write("VALUE %d %s\n" % (rid, found[2].hex()))

    def tick(self, reads):
        self.serve(reads)
        self.push_queue()
        self.maintain()
        self.work()

    def free_sectors(self):
        return [s for s in range(self.n_sectors)
                if s not in self.gens and s not in self.dead]

    def head_room(self):
        if self.head is None or self.cursor is None:
            return 0
        return self.n_pages - self.cursor

    def push_queue(self):
        while self.queue and self.job is None:
            if self.head_room() <= 0:
                return
            if not self.room(self.cost_prog + self.cost_read):
                return
            rid, block, value = self.queue[0]
            if "ack_early" in self.off and rid not in self.early:
                self.early.add(rid)
                self.out.write("ACK %d\n" % rid)
            page = self.cursor
            if not self.store_page(self.head, page,
                                   self.record_page(block, self.stamp, value)):
                return
            self.cursor += 1
            back = self.fetch(self.head, page)
            check = self.read_record(back) if back is not None else None
            if check is None or check[2] != value or check[0] != block:
                continue
            self.where[block] = (self.head, page, self.stamp)
            self.stamp += 1
            self.queue.pop(0)
            if rid not in self.early:
                self.out.write("ACK %d\n" % rid)

    def maintain(self):
        """Keep one erased sector in reserve and open a new head when full."""
        if self.job is not None:
            return
        spare = self.free_sectors()
        if self.head_room() <= 0:
            if spare:
                self.job = {"step": "wipe", "target": spare[0], "after": "label"}
                return
            victim = self.oldest()
            if victim is not None:
                self.job = {"step": "salvage", "victim": victim, "left": None}
            return
        if not spare:
            victim = self.oldest()
            if victim is not None and self.head_room() > len(self.where) + 2:
                self.job = {"step": "salvage", "victim": victim, "left": None}

    def oldest(self):
        known = [s for s in sorted(self.gens, key=lambda s: self.gens[s])
                 if s != self.head]
        return known[0] if known else None

    def work(self):
        while self.job is not None:
            step = self.job["step"]
            if step == "salvage":
                if not self.copy_out():
                    return
                continue
            if step == "wipe":
                if not self.wipe(self.job["target"]):
                    return
                self.job["step"] = "settle"
                self.job["page"] = 0
                return
            if step == "settle":
                if self.waiting() > 0:
                    return
                self.job["step"] = "prove"
                continue
            if step == "prove":
                target = self.job["target"]
                if "no_erase_proof" in self.off:
                    self.job["page"] = self.n_pages
                while self.job["page"] < self.n_pages:
                    if not self.room(self.cost_read):
                        return
                    raw = self.fetch(target, self.job["page"])
                    if raw is None:
                        return
                    if raw != self.erased_page:
                        self.dead.add(target)
                        self.gens.pop(target, None)
                        self.job = None
                        self.maintain()
                        break
                    self.job["page"] += 1
                if self.job is None or self.job["step"] != "prove":
                    continue
                if self.job["after"] == "release":
                    self.gens.pop(target, None)
                    self.job = None
                    self.maintain()
                    continue
                self.job["step"] = "label"
                continue
            if step == "label":
                target = self.job["target"]
                if not self.room(2 * self.cost_prog):
                    return
                gen = self.gen + 1
                if not self.store_page(target, 0, self.sector_page(gen)):
                    return
                if not self.store_page(target, 1, self.snapshot_page(self.where)):
                    return
                self.gen = gen
                self.gens[target] = gen
                self.head = target
                self.cursor = 2
                self.job = None
                self.maintain()
                continue
            return

    def copy_out(self):
        """Move whatever is still live out of the victim, then erase it."""
        victim = self.job["victim"]
        if self.job["left"] is None:
            self.job["left"] = sorted(b for b, spot in self.where.items()
                                      if spot[0] == victim)
        while self.job["left"]:
            if self.head_room() <= 1:
                self.job = None
                self.maintain()
                return False
            if not self.room(self.cost_read + self.cost_prog):
                return False
            block = self.job["left"][0]
            spot = self.where.get(block)
            if spot is None or spot[0] != victim:
                self.job["left"].pop(0)
                continue
            raw = self.fetch(spot[0], spot[1])
            found = self.read_record(raw) if raw is not None else None
            if found is None or found[0] != block:
                self.job["left"].pop(0)
                continue
            page = self.cursor
            if not self.store_page(self.head, page,
                                   self.record_page(block, self.stamp, found[2])):
                return False
            self.cursor += 1
            self.where[block] = (self.head, page, self.stamp)
            self.stamp += 1
            self.job["left"].pop(0)
        if self.head_room() <= 0:
            self.job = None
            self.maintain()
            return False
        if "no_snapshot_refresh" not in self.off:
            if not self.room(self.cost_prog):
                return False
            if not self.store_page(self.head, self.cursor, self.snapshot_page(self.where)):
                return False
            self.cursor += 1
        self.job = {"step": "wipe", "target": victim, "after": "release"}
        return True


def main():
    inp, out = sys.stdin, sys.stdout
    store = None
    reads = []
    while True:
        line = inp.readline()
        if not line:
            return
        line = line.strip()
        if not line:
            continue
        if line.startswith("BOOT "):
            store = CircularStore(json.loads(line[5:]), inp, out)
        elif line == "MOUNT":
            store.mount()
            out.write("MOUNTED\n")
            out.flush()
        elif line.startswith("TICK "):
            store.begin(int(line.split()[1]))
            reads = []
        elif line.startswith("WRITE "):
            parts = line.split()
            store.accept(int(parts[1]), int(parts[2]), bytes.fromhex(parts[3]))
        elif line.startswith("READ "):
            parts = line.split()
            reads.append((int(parts[1]), int(parts[2])))
        elif line == "GO":
            store.tick(reads)
            out.write("DONE\n")
            out.flush()
            reads = []


if __name__ == "__main__":
    main()
