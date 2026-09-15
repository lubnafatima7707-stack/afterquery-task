#!/usr/bin/env python3
"""
A second correct store, written to a different design from the reference, so the
bars can be placed against the spread of correct implementations rather than
against one implementation's score.

Both stores have to run the part as an append only log, because the device only
gives one way of rewriting a block. Where they part company is in how a mount
gets its index back.

The reference pays for the mount sector by sector: the last few pages of every
sector are kept back, and when a sector is closed they are filled with a list of
what each of its pages holds, so a mount reads one summary per closed sector and
the pages of the sector still open.

This one pays for it in one place. Two sectors are set aside as a map area and
hold nothing else. Every time a sector is opened for writing, the whole block to
page map as it stands at that moment is written into the map area as a
checkpoint, together with the sector that was just opened and the generation it
carries. A mount reads the newest complete checkpoint and then reads forward
from that sector, which is the only part of the log the checkpoint does not
already describe. Nothing is kept back inside a log sector, so every page but
the header holds a record, and a checkpoint that a reset spoiled costs nothing
but falling back to the one before it and reading one more sector.

The trade is visible in the numbers rather than argued: this design gives up two
sectors of the part and writes the map again on every sector change, and gets
back the pages the reference spends on summaries and a mount that does not grow
with the number of closed sectors.

Reclaim is the part neither design has a choice about: the sector with the
fewest live records is copied out and erased, an erase is read back before the
sector is used and tried again before the sector is given up, and two sectors
are kept blank so that a reclaim which turns up a worn sector still has
somewhere to go.

VARIANT is the authoring switch, empty as shipped. Each value it accepts removes
one piece of this design, which is how the second block of the results table was
measured: a reviewer should not have to take on trust that the pieces of a
shipped solver are load bearing.
"""
import json
import sys
import zlib

VARIANT = ""

LOG_MAGIC = b"CLG2"
MAP_MAGIC = b"CMAP"
REC_TAG = 0x52
MAP_TAG = 0x4D
REC_OVERHEAD = 12
# tag, chunk, chunks, head sector, head page, stamp(4), generation(4), crc(4)
MAP_OVERHEAD = 17
NOWHERE = 0xFF


def _crc(data):
    return (zlib.crc32(data) & 0xFFFFFFFF).to_bytes(4, "little")


def _flags():
    flags, knobs = set(), {}
    for part in VARIANT.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            key, value = part.split("=", 1)
            knobs[key.strip()] = float(value)
        else:
            flags.add(part)
    return flags, knobs


class Store:
    def __init__(self, cfg, stdin, stdout):
        self.inp = stdin
        self.out = stdout
        self.S = int(cfg["sectors"])
        self.P = int(cfg["pages_per_sector"])
        self.B = int(cfg["page_bytes"])
        self.t_read = float(cfg["t_read_ms"])
        self.t_prog = float(cfg["t_program_ms"])
        self.n_blocks = len(cfg["blocks"])
        self.blank_page = bytes([0xFF]) * self.B
        self.flags, self.knobs = _flags()
        self.budget = float(cfg["tick_budget_ms"]) * self.knobs.get("budget_frac", 1.0)
        self.used = 0.0
        self.tick = int(cfg.get("tick", 0))
        self.last_record = self.P - 1
        self.fan = max(1, (self.B - MAP_OVERHEAD) // 2)
        self.cp_pages = (self.n_blocks + self.fan - 1) // self.fan
        self.slots = max(1, (self.P - 1) // self.cp_pages)
        self.index = {}
        self.live = [0] * self.S
        self.gen = {}
        self.maps = {}
        self.map_cur = None
        self.map_slot = 0
        self.map_seq = 0
        self.stamp = 1
        self.cp_pending = None
        self.pending = []
        self.retired = set()
        self.wiped = set()
        self.head = None
        self.append = None
        self.seq = 0
        self.rseq = 1
        self.gc = None
        self.margin = int(self.knobs.get("margin", 2))
        self.pool = max(1, int(self.knobs.get("pool", 3)))
        self.erase_gap = int(self.knobs.get("erase_gap", 5))
        self.last_erase = -999

    # ----------------------------------------------------------- device access

    def _op(self, text):
        self.out.write("OP " + text + "\n")
        self.out.flush()
        return self.inp.readline().strip()

    def _afford(self, cost):
        if "no_budget" in self.flags:
            return True
        return self.used + cost <= self.budget + 1e-9

    def read_page(self, sector, page):
        reply = self._op("READ %d %d" % (sector, page))
        if reply == "BUSY":
            return None
        if not reply.startswith("DATA "):
            raise SystemExit(0)
        self.used += self.t_read
        return bytes.fromhex(reply[5:])

    def program_page(self, sector, page, payload):
        data = payload + bytes([0xFF]) * (self.B - len(payload))
        reply = self._op("PROGRAM %d %d %s" % (sector, page, data.hex()))
        if reply == "BUSY":
            return False
        if reply != "OK":
            raise SystemExit(0)
        self.used += self.t_prog
        return True

    def erase_sector(self, sector):
        return self._op("ERASE %d" % sector) == "OK"

    def busy_ticks(self):
        reply = self._op("STATUS")
        return int(reply.split()[1]) if reply.startswith("BUSY") else 0

    def settled_read(self, sector, page):
        for _ in range(64):
            data = self.read_page(sector, page)
            if data is not None:
                return data
        return None

    def is_erased(self, page):
        return page == self.blank_page

    # ------------------------------------------------------------ page formats

    def header_bytes(self, magic, seq):
        body = magic + seq.to_bytes(4, "little")
        return body + _crc(body)

    def parse_header(self, magic, page):
        if page is None or len(page) < 12 or page[:4] != magic:
            return None
        if _crc(page[:8]) != page[8:12]:
            return None
        return int.from_bytes(page[4:8], "little")

    def record_bytes(self, block, rseq, value):
        body = (bytes([REC_TAG]) + block.to_bytes(2, "little") + bytes([len(value)])
                + rseq.to_bytes(4, "little") + value)
        return body + _crc(body)

    def parse_record(self, page):
        if page is None or len(page) < REC_OVERHEAD or page[0] != REC_TAG:
            return None
        block = int.from_bytes(page[1:3], "little")
        length = page[3]
        if block >= self.n_blocks:
            return None
        if "no_crc" in self.flags:
            length = min(length, self.B - REC_OVERHEAD)
        elif length > self.B - REC_OVERHEAD:
            return None
        body = page[:8 + length]
        if "no_crc" not in self.flags and _crc(body) != page[8 + length:12 + length]:
            return None
        return block, int.from_bytes(page[4:8], "little"), bytes(page[8:8 + length])

    def chunk_bytes(self, chunk, head, head_page, gen, spots):
        body = bytearray([MAP_TAG, chunk, self.cp_pages, head, head_page])
        body += self.stamp.to_bytes(4, "little") + gen.to_bytes(4, "little")
        for spot in spots:
            body += (bytes([NOWHERE, NOWHERE]) if spot is None
                     else bytes([spot[0], spot[1]]))
        body += bytes([NOWHERE, NOWHERE]) * (self.fan - len(spots))
        return bytes(body) + _crc(bytes(body))

    def parse_chunk(self, page):
        end = 13 + 2 * self.fan
        if page is None or len(page) < end + 4 or page[0] != MAP_TAG:
            return None
        if page[2] != self.cp_pages:
            return None
        if _crc(page[:end]) != page[end:end + 4]:
            return None
        spots = []
        for i in range(self.fan):
            sector, spot = page[13 + 2 * i], page[14 + 2 * i]
            spots.append(None if sector == NOWHERE else (sector, spot))
        return {"chunk": page[1], "head": page[3], "head_page": page[4],
                "stamp": int.from_bytes(page[5:9], "little"),
                "gen": int.from_bytes(page[9:13], "little"), "spots": spots}

    # ------------------------------------------------------------------- mount

    def mount(self):
        logs, maps = {}, {}
        for sector in range(self.S):
            page = self.settled_read(sector, 0)
            seq = self.parse_header(LOG_MAGIC, page)
            if seq is not None:
                logs[sector] = seq
                continue
            seq = self.parse_header(MAP_MAGIC, page)
            if seq is not None:
                maps[sector] = seq
        self.gen = logs
        self.maps = maps
        self.seq = max(logs.values()) if logs else 0
        self.map_seq = max(maps.values()) if maps else 0
        if not logs and not maps:
            self._format()
            return
        check = None
        for sector in sorted(maps, key=lambda s: -maps[s]):
            check = self._newest_checkpoint(sector)
            if check is not None:
                self.map_cur = sector
                self.stamp = check["stamp"] + 1
                break
        if self.map_cur is None and maps:
            self.map_cur = max(maps, key=lambda s: maps[s])
        if self.map_cur is not None:
            self.map_slot = self._free_slot(self.map_cur)
        scanned = set()
        if check is None or "no_checkpoint" in self.flags:
            # nothing usable to start from, so the log is read end to end; this
            # is the cost of a map area that has not caught up yet, not the cost
            # of an ordinary mount
            tail = sorted(logs, key=lambda s: logs[s])
        else:
            for block, spot in enumerate(check["spots"]):
                if spot is None or block >= self.n_blocks:
                    continue
                if spot[0] in logs and 1 <= spot[1] <= self.last_record:
                    self._place(block, spot[0], spot[1])
            tail = [s for s in logs if logs[s] >= check["gen"]]
            tail.sort(key=lambda s: logs[s])
        appends = {}
        for sector in tail:
            appends[sector] = self._scan(sector)
            scanned.add(sector)
        if logs:
            self.head = max(logs, key=lambda s: logs[s])
            if self.head not in scanned:
                appends[self.head] = self._scan(self.head)
            self.append = appends.get(self.head)

    def _free_slot(self, sector):
        """The first slot of a map sector nothing has been written into.

        A checkpoint a reset interrupted leaves pages that can never be made to
        read as a chunk again, so the slot it was going into is spent; the next
        one starts where the writing stopped, not where the newest whole
        checkpoint happens to be.
        """
        for slot in range(self.slots):
            page = self.settled_read(sector, 1 + slot * self.cp_pages)
            if page is not None and self.is_erased(page):
                return slot
        return self.slots

    def _newest_checkpoint(self, sector):
        best = None
        for slot in range(self.slots):
            base = 1 + slot * self.cp_pages
            first = self.parse_chunk(self.settled_read(sector, base))
            if first is None or first["chunk"] != 0:
                continue
            if best is not None and first["stamp"] <= best["stamp"]:
                continue
            spots = list(first["spots"])
            whole = True
            for i in range(1, self.cp_pages):
                part = self.parse_chunk(self.settled_read(sector, base + i))
                if part is None or part["chunk"] != i or part["stamp"] != first["stamp"]:
                    whole = False
                    break
                spots.extend(part["spots"])
            if whole:
                best = dict(first)
                best["spots"] = spots
                best["slot"] = slot
        return best

    def _scan(self, sector):
        """Read a sector page by page, placing its records. Returns the first blank page."""
        page = 1
        while page <= self.last_record:
            data = self.settled_read(sector, page)
            if self.is_erased(data):
                return page
            record = self.parse_record(data)
            if record is not None:
                self._place(record[0], sector, page)
                if record[1] >= self.rseq:
                    self.rseq = record[1] + 1
            page += 1
        return None

    def _place(self, block, sector, page):
        old = self.index.get(block)
        if old is not None:
            self.live[old[0]] -= 1
        self.index[block] = (sector, page)
        self.live[sector] += 1

    def _format(self):
        blank = []
        for sector in range(self.S):
            page = self.settled_read(sector, 0)
            if page is not None and self.is_erased(page):
                blank.append(sector)
            if len(blank) == 2:
                break
        if len(blank) < 2:
            return
        self.seq = 1
        if self.program_page(blank[0], 0, self.header_bytes(LOG_MAGIC, 1)):
            self.gen = {blank[0]: 1}
            self.head = blank[0]
            # page 0 reading blank does not make the rest of the sector blank
            append = self._scan(blank[0])
            self.append = append
        self.map_seq = 1
        if self.program_page(blank[1], 0, self.header_bytes(MAP_MAGIC, 1)):
            self.maps = {blank[1]: 1}
            self.map_cur = blank[1]
            self.map_slot = self._free_slot(blank[1])

    # ---------------------------------------------------------------- the tick

    def begin_tick(self, tick):
        self.tick = tick
        self.used = 0.0

    def queue_write(self, rid, block, value):
        self.pending.append([rid, block, value])

    def run_tick(self, reads):
        self._answer(reads)
        if "ack_early" in self.flags:
            for item in self.pending:
                if len(item) == 3:
                    item.append(True)
                    self.out.write("ACK %d\n" % item[0])
        self._drain()
        self._plan()
        self._advance()

    def _answer(self, reads):
        for rid, block in reads:
            value = None
            for item in reversed(self.pending):
                if item[1] == block:
                    value = item[2]
                    break
            if value is not None:
                self.out.write("VALUE %d %s\n" % (rid, value.hex()))
                continue
            held = self.index.get(block)
            if held is None:
                self.out.write("VALUE %d NONE\n" % rid)
                continue
            page = self.read_page(held[0], held[1])
            record = self.parse_record(page) if page is not None else None
            if record is None or record[0] != block:
                self.out.write("VALUE %d BUSY\n" % rid)
            else:
                self.out.write("VALUE %d %s\n" % (rid, record[2].hex()))

    def room(self):
        if self.head is None or self.append is None:
            return 0
        return self.last_record - self.append + 1

    def _write_record(self, block, value):
        page = self.append
        if not self.program_page(self.head, page, self.record_bytes(block, self.rseq, value)):
            return None
        self.append += 1
        self.rseq += 1
        back = self.read_page(self.head, page)
        again = self.parse_record(back) if back is not None else None
        if again is None or again[2] != value:
            return False
        self._place(block, self.head, page)
        return page

    def _owed(self):
        if "no_reserve" in self.flags or self.blanks():
            return 0
        victim = self._victim()
        return 0 if victim is None else self.live[victim]

    def _drain(self):
        while self.pending:
            if self.room() <= 0 or self.append > self.last_record - self._owed():
                return
            if not self._afford(self.t_prog + self.t_read):
                return
            rid, block, value = self.pending[0][:3]
            early = len(self.pending[0]) > 3
            landed = self._write_record(block, value)
            if landed is None:
                return
            if landed is False:
                continue
            self.pending.pop(0)
            if not early:
                self.out.write("ACK %d\n" % rid)

    # -------------------------------------------------------------- reclaiming

    def spare_sectors(self):
        return [s for s in range(self.S)
                if s not in self.gen and s not in self.maps and s not in self.retired]

    def blanks(self):
        return sorted(self.wiped - self.retired)

    def _victim(self):
        best, score = None, None
        for sector in self.gen:
            if sector == self.head or sector in self.retired:
                continue
            if score is None or self.live[sector] < score:
                best, score = sector, self.live[sector]
        return best

    def _cycle(self, phase, **extra):
        job = {"phase": phase, "target": None, "victim": None, "copy": [],
               "verify": 0, "chunk": 0, "after": "done", "tries": 1}
        job.update(extra)
        return job

    def _plan(self):
        if self.gc is not None:
            return
        blanks = self.blanks()
        if len(blanks) < self.pool:
            spare = [s for s in self.spare_sectors() if s not in self.wiped]
            if spare:
                return self._start(self._cycle("check", target=spare[0],
                                               after="done", tries=0))
        stale = [s for s in self.maps if s != self.map_cur]
        if stale and self.map_cur is not None and self.cp_pending is None:
            # a map sector left behind by a rotation a reset interrupted; it is
            # worth more back in the pool than as a second copy of an older map
            return self._start(self._cycle("wipe", target=stale[0], after="done"))
        if self.map_cur is None and blanks:
            return self._start(self._cycle("maphdr", target=blanks[0]))
        if (self.head is None or self.room() <= self.margin) and blanks:
            return self._start(self._cycle("open"))
        if self.cp_pending is not None and (self.map_slot < self.slots or blanks):
            return self._start(self._cycle("cpspace"))
        if len(blanks) < self.pool:
            victim = self._victim()
            if victim is not None and self.room() >= self.live[victim] + self.margin:
                return self._start(self._cycle("salvage", victim=victim,
                                               copy=self._live_blocks(victim)))

    def _start(self, job):
        self.gc = job

    def _live_blocks(self, sector):
        return [b for b, spot in self.index.items() if spot[0] == sector]

    def _advance(self):
        job = self.gc
        while job is not None:
            phase = job["phase"]
            if phase == "open":
                ready = self.blanks()
                if not ready:
                    self.gc = None
                    return
                target = ready[0]
                if not self._afford(self.t_prog):
                    return
                self.seq += 1
                if not self.program_page(target, 0, self.header_bytes(LOG_MAGIC, self.seq)):
                    return
                self.wiped.discard(target)
                self.gen[target] = self.seq
                self.head = target
                self.append = 1
                # the checkpoint is composed here, before anything is appended,
                # so the only part of the log it does not describe is this
                # sector, and a mount reads this sector and nothing else. It is
                # held until there is somewhere to put it rather than dropped,
                # because every sector opened without one is another sector a
                # mount has to read.
                self.cp_pending = {"spots": self._compose(), "head": self.head,
                                   "gen": self.seq}
                job["phase"] = "done"
                continue
            if phase == "cpspace":
                if "no_checkpoint" in self.flags or self.cp_pending is None:
                    self.cp_pending = None
                    job["phase"] = "done"
                    continue
                job["chunk"] = 0
                if self.map_cur is not None and self.map_slot < self.slots:
                    job["phase"] = "cpwrite"
                    continue
                # the map area has one sector at a time: the next one is taken
                # from the blank pool and the old one is only given up once the
                # new one holds a whole checkpoint, so there is never a moment
                # with no map on the part
                ready = self.blanks()
                if not ready:
                    self.gc = None
                    return
                job["target"] = ready[0]
                job["old"] = self.map_cur
                job["phase"] = "maphdr"
                continue
            if phase == "maphdr":
                target = job["target"]
                if not self._afford(self.t_prog):
                    return
                self.map_seq += 1
                if not self.program_page(target, 0, self.header_bytes(MAP_MAGIC, self.map_seq)):
                    return
                self.wiped.discard(target)
                self.maps[target] = self.map_seq
                self.map_cur = target
                self.map_slot = 0
                job["phase"] = "cpwrite" if self.cp_pending else "done"
                continue
            if phase == "cpwrite":
                base = 1 + self.map_slot * self.cp_pages
                cp = self.cp_pending
                while job["chunk"] < self.cp_pages:
                    if not self._afford(self.t_prog):
                        return
                    part = cp["spots"][job["chunk"] * self.fan:
                                       (job["chunk"] + 1) * self.fan]
                    if not self.program_page(self.map_cur, base + job["chunk"],
                                             self.chunk_bytes(job["chunk"], cp["head"],
                                                              1, cp["gen"], part)):
                        return
                    job["chunk"] += 1
                self.map_slot += 1
                self.stamp += 1
                self.cp_pending = None
                old = job.get("old")
                if old is not None and old in self.maps:
                    job["target"] = old
                    job["after"] = "done"
                    job["tries"] = 1
                    job["phase"] = "wipe"
                    continue
                job["phase"] = "done"
                continue
            if phase == "salvage":
                victim = job["victim"]
                while job["copy"]:
                    if self.room() <= 0:
                        return
                    if not self._afford(3 * self.t_read + self.t_prog):
                        return
                    block = job["copy"][0]
                    spot = self.index.get(block)
                    if spot is None or spot[0] != victim:
                        job["copy"].pop(0)
                        continue
                    data = self.read_page(spot[0], spot[1])
                    if data is None:
                        return
                    record = self.parse_record(data)
                    if record is None or record[0] != block:
                        job["copy"].pop(0)
                        continue
                    landed = self._write_record(block, record[2])
                    if landed is None:
                        return
                    if landed is False:
                        continue
                    job["copy"].pop(0)
                job["target"] = victim
                job["after"] = "done"
                job["tries"] = 1
                job["phase"] = "wipe"
                continue
            if phase == "wipe":
                target = job["target"]
                if self.tick - self.last_erase < self.erase_gap:
                    return
                if not self.erase_sector(target):
                    return
                self.last_erase = self.tick
                self.gen.pop(target, None)
                self.maps.pop(target, None)
                if self.map_cur == target:
                    self.map_cur = None
                self.live[target] = 0
                job["phase"] = "settle"
                job["verify"] = 0
                return
            if phase == "settle":
                if self.busy_ticks() > 0:
                    return
                job["phase"] = "check"
                continue
            if phase == "check":
                target = job["target"]
                if "no_erase_proof" in self.flags:
                    self.wiped.add(target)
                    job["phase"] = job["after"]
                    continue
                while job["verify"] < self.P:
                    if not self._afford(self.t_read):
                        return
                    data = self.read_page(target, job["verify"])
                    if data is None:
                        return
                    if not self.is_erased(data):
                        job["tries"] = job.get("tries", 1) + 1
                        if job["tries"] <= int(self.knobs.get("erase_tries", 2)):
                            job["phase"] = "wipe"
                        else:
                            self.retired.add(target)
                            self.wiped.discard(target)
                            job["phase"] = job["after"]
                        break
                    job["verify"] += 1
                if job["phase"] != "check":
                    continue
                self.wiped.add(target)
                job["phase"] = job["after"]
                continue
            if phase == "done":
                self.gc = None
                return
            return

    def _compose(self):
        spots = []
        for block in range(self.n_blocks):
            spot = self.index.get(block)
            spots.append(spot if spot is not None else None)
        return spots


def main():
    inp = sys.stdin
    out = sys.stdout
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
            store = Store(json.loads(line[5:]), inp, out)
        elif line == "MOUNT":
            store.mount()
            out.write("MOUNTED\n")
            out.flush()
        elif line.startswith("TICK "):
            store.begin_tick(int(line.split()[1]))
            reads = []
        elif line.startswith("WRITE "):
            parts = line.split()
            store.queue_write(int(parts[1]), int(parts[2]), bytes.fromhex(parts[3]))
        elif line.startswith("READ "):
            parts = line.split()
            reads.append((int(parts[1]), int(parts[2])))
        elif line == "GO":
            store.run_tick(reads)
            out.write("DONE\n")
            out.flush()
            reads = []


if __name__ == "__main__":
    main()
