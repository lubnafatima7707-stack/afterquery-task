#!/usr/bin/env python3
"""
Reference non volatile block store for the ECU flash device.

Layout. Every sector carries a header in page 0 holding a generation number and
a seal in page 1 that is programmed only once the sector holds a complete copy
of every live block, so a sector whose header is present but whose seal is
missing was being filled when the supply went away and is ignored. Records are
appended one to a page from page 2 upwards, each carrying its block, its length,
a record sequence number and a checksum over all of it, so a page left half
programmed by a reset fails its checksum and is skipped without being reused.
All live records sit in the active sector, which is what keeps the mount inside
its budget: the mount reads the sector headers, one seal, and the pages of the
active sector only.

When the active sector runs out of pages the store compacts: it erases the next
sector in rotation, reads back every page to prove the erase took, writes the
new header, copies the newest record of each live block forward, and only then
writes the seal. A reset anywhere inside that sequence leaves the old sector
sealed and authoritative and the new one unsealed and ignored, so the worst case
is the work being done again.

The VARIANT string is an authoring switch. It is empty in the shipped solution
and every value it accepts only removes a piece of the design, which is how the
ablation numbers in authoring/evidence were measured.
"""
import json
import sys
import zlib

VARIANT = ""

HDR_MAGIC = b"NVH1"
SEAL_MAGIC = b"NVS1"
REC_MAGIC = 0x52
REC_OVERHEAD = 11
GC_MARGIN = 0


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
        self.block_len = list(cfg["blocks"])
        self.blank = bytes([0xFF]) * self.B
        self.flags, self.knobs = _flags()
        self.budget = float(cfg["tick_budget_ms"]) * self.knobs.get("budget_frac", 1.0)
        self.margin = int(self.knobs.get("margin", GC_MARGIN))
        self.drip = int(self.knobs.get("drip", 0))
        self.last_program_tick = -999
        self.used = 0.0
        self.tick = int(cfg.get("tick", 0))
        self.index = {}
        self.pending = []
        self.retired = set()
        self.active = None
        self.append = None
        self.seq = 0
        self.rseq = 1
        self.gc = None

    # ----------------------------------------------------------- device access

    def _op(self, text):
        self.out.write("OP " + text + "\n")
        self.out.flush()
        return self.inp.readline().strip()

    def _afford(self, cost):
        if "no_budget" in self.flags:
            return True
        return self.used + cost <= self.budget + 1e-9

    def read_page(self, sector, page, charge=True):
        reply = self._op("READ %d %d" % (sector, page))
        if reply == "BUSY":
            return None
        if not reply.startswith("DATA "):
            raise SystemExit(0)
        if charge:
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
        if reply.startswith("BUSY"):
            return int(reply.split()[1])
        return 0

    # ------------------------------------------------------------ page formats

    def is_erased(self, page):
        return page == self.blank

    def header_bytes(self, seq):
        body = HDR_MAGIC + seq.to_bytes(4, "little")
        return body + _crc(body)

    def parse_header(self, page):
        if page is None or len(page) < 12 or page[:4] != HDR_MAGIC:
            return None
        if _crc(page[:8]) != page[8:12]:
            return None
        return int.from_bytes(page[4:8], "little")

    def seal_bytes(self, seq, live):
        body = SEAL_MAGIC + seq.to_bytes(4, "little") + live.to_bytes(2, "little")
        return body + _crc(body)

    def parse_seal(self, page):
        if page is None or len(page) < 14 or page[:4] != SEAL_MAGIC:
            return None
        if _crc(page[:10]) != page[10:14]:
            return None
        return int.from_bytes(page[4:8], "little")

    def record_bytes(self, block, rseq, value):
        body = (bytes([REC_MAGIC, block, len(value)])
                + rseq.to_bytes(4, "little") + value)
        return body + _crc(body)

    def parse_record(self, page):
        if page is None or len(page) < REC_OVERHEAD or page[0] != REC_MAGIC:
            return None
        block = page[1]
        length = page[2]
        if block >= len(self.block_len):
            return None
        if "no_crc" in self.flags:
            length = min(length, self.B - REC_OVERHEAD)
        elif length > self.B - REC_OVERHEAD:
            return None
        body = page[:7 + length]
        if "no_crc" not in self.flags and _crc(body) != page[7 + length:11 + length]:
            return None
        rseq = int.from_bytes(page[3:7], "little")
        return block, rseq, bytes(page[7:7 + length])

    # ------------------------------------------------------------------- mount

    def _read_settled(self, sector, page):
        for _ in range(64):
            data = self.read_page(sector, page)
            if data is not None:
                return data
        return None

    def mount(self):
        if "lazy_scan" in self.flags:
            # Authoring probe only: spend nothing at MOUNT and scan the whole part
            # from inside the ticks instead, answering reads BUSY until it is done.
            self.lazy = {"pos": 0, "pages": {},
                         "targets": [(sector, page) for sector in range(self.S)
                                     for page in range(self.P)]}
            return
        self.lazy = None
        headers = {}
        for sector in range(self.S):
            seq = self.parse_header(self._read_settled(sector, 0))
            if seq is not None:
                headers[sector] = seq
        self.seq = max(headers.values()) if headers else 0
        authoritative = None
        for sector in sorted(headers, key=lambda s: -headers[s]):
            if "no_seal" in self.flags:
                authoritative = sector
                break
            if self.parse_seal(self._read_settled(sector, 1)) == headers[sector]:
                authoritative = sector
                break
        if authoritative is None:
            self._mount_blank()
            return
        self.active = authoritative
        if "full_scan" in self.flags:
            for sector in range(self.S):
                self._scan_sector(sector, sector == authoritative, True)
        else:
            self._scan_sector(authoritative, True, True)

    def _scan_sector(self, sector, is_active, build_index):
        page = 2
        append = None
        while page < self.P:
            data = self._read_settled(sector, page)
            if self.is_erased(data):
                append = page
                break
            record = self.parse_record(data) if build_index else None
            if record is not None:
                block, rseq, value = record
                held = self.index.get(block)
                if held is None or rseq > held[2]:
                    self.index[block] = (sector, page, rseq)
                if rseq >= self.rseq:
                    self.rseq = rseq + 1
            page += 1
        if is_active:
            self.append = append

    def _mount_blank(self):
        for sector in range(self.S):
            page = self._read_settled(sector, 0)
            if page is not None and self.is_erased(page):
                if self.program_page(sector, 0, self.header_bytes(1)):
                    if self.program_page(sector, 1, self.seal_bytes(1, 0)):
                        self.active = sector
                        self.seq = 1
                        self._scan_sector(sector, True, False)
                        return
        self.active = None
        self.append = None
        self.gc = {"phase": "pick", "target": None, "newseq": self.seq + 1,
                   "copy": [], "verify": 0, "done": []}

    # ---------------------------------------------------------------- the tick

    def begin_tick(self, tick):
        self.tick = tick
        self.used = 0.0

    def queue_write(self, rid, block, value):
        self.pending.append([rid, block, value])

    def run_tick(self, reads):
        if getattr(self, "lazy", None) is not None:
            for rid, _block in reads:
                self.out.write("VALUE %d BUSY\n" % rid)
            self._lazy_mount_tick()
            return
        self._answer(reads)
        if "ack_early" in self.flags:
            for item in self.pending:
                if len(item) == 3:
                    item.append(True)
                    self.out.write("ACK %d\n" % item[0])
        self._drain_writes()
        self._advance_gc()

    def _lazy_mount_tick(self):
        lazy = self.lazy
        while lazy["pos"] < len(lazy["targets"]):
            if not self._afford(self.t_read):
                return
            sector, page = lazy["targets"][lazy["pos"]]
            data = self.read_page(sector, page)
            if data is None:
                return
            lazy["pages"][(sector, page)] = data
            lazy["pos"] += 1
        pages = lazy["pages"]
        headers = {}
        for sector in range(self.S):
            seq = self.parse_header(pages.get((sector, 0)))
            if seq is not None:
                headers[sector] = seq
        self.seq = max(headers.values()) if headers else 0
        authoritative = None
        for sector in sorted(headers, key=lambda s: -headers[s]):
            if self.parse_seal(pages.get((sector, 1))) == headers[sector]:
                authoritative = sector
                break
        self.lazy = None
        if authoritative is None:
            self._mount_blank()
            return
        self.active = authoritative
        for page in range(2, self.P):
            data = pages.get((authoritative, page))
            if self.is_erased(data):
                self.append = page
                break
            record = self.parse_record(data)
            if record is not None:
                block, rseq, _value = record
                held = self.index.get(block)
                if held is None or rseq > held[2]:
                    self.index[block] = (authoritative, page, rseq)
                if rseq >= self.rseq:
                    self.rseq = rseq + 1

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
            if page is None:
                self.out.write("VALUE %d BUSY\n" % rid)
                continue
            record = self.parse_record(page)
            if record is None:
                self.out.write("VALUE %d BUSY\n" % rid)
                continue
            self.out.write("VALUE %d %s\n" % (rid, record[2].hex()))

    def _drain_writes(self):
        if self.gc is not None:
            return
        if self.drip and self.tick - self.last_program_tick < self.drip:
            return
        while self.pending:
            if self.active is None or self.append is None or self.append >= self.P:
                self._need_gc()
                return
            if not self._afford(self.t_prog + self.t_read):
                return
            rid, block, value = self.pending[0][:3]
            early = len(self.pending[0]) > 3
            page = self.append
            if not self.program_page(self.active, page, self.record_bytes(block, self.rseq, value)):
                return
            self.append += 1
            check = self.read_page(self.active, page)
            record = self.parse_record(check) if check is not None else None
            if record is None or record[2] != value:
                continue
            self.index[block] = (self.active, page, self.rseq)
            self.rseq += 1
            self.pending.pop(0)
            self.last_program_tick = self.tick
            if not early:
                self.out.write("ACK %d\n" % rid)
            if self.drip:
                return
        self._need_gc()

    def _need_gc(self):
        if self.gc is not None or self.active is None:
            return
        free = self.P - (self.append if self.append is not None else self.P)
        if free <= self.margin:
            self.gc = {"phase": "pick", "target": None, "newseq": self.seq + 1,
                       "copy": sorted(self.index), "verify": 0, "done": []}

    # ------------------------------------------------------------- compaction

    def _pick_target(self):
        start = 0 if self.active is None else self.active
        for step in range(1, self.S + 1):
            cand = (start + step) % self.S
            if cand == self.active or cand in self.retired:
                continue
            return cand
        return None

    def _advance_gc(self):
        gc = self.gc
        while gc is not None:
            phase = gc["phase"]
            if phase == "pick":
                target = self._pick_target()
                if target is None:
                    return
                gc["target"] = target
                if not self.erase_sector(target):
                    return
                gc["phase"] = "wait"
                return
            if phase == "wait":
                if self.busy_ticks() > 0:
                    return
                gc["phase"] = "verify"
                gc["verify"] = 0
                continue
            if phase == "verify":
                if "no_erase_verify" in self.flags:
                    gc["phase"] = "header"
                    continue
                while gc["verify"] < self.P:
                    if not self._afford(self.t_read):
                        return
                    data = self.read_page(gc["target"], gc["verify"])
                    if data is None:
                        return
                    if not self.is_erased(data):
                        self.retired.add(gc["target"])
                        gc["phase"] = "pick"
                        break
                    gc["verify"] += 1
                if gc["phase"] == "pick":
                    continue
                if gc["verify"] >= self.P:
                    gc["phase"] = "header"
                continue
            if phase == "header":
                if not self._afford(self.t_prog):
                    return
                if not self.program_page(gc["target"], 0, self.header_bytes(gc["newseq"])):
                    return
                gc["phase"] = "copy"
                gc["next_page"] = 2
                gc["new_index"] = {}
                continue
            if phase == "copy":
                while gc["copy"]:
                    if not self._afford(self.t_read + self.t_prog):
                        return
                    block = gc["copy"][0]
                    held = self.index.get(block)
                    if held is None:
                        gc["copy"].pop(0)
                        continue
                    data = self.read_page(held[0], held[1])
                    if data is None:
                        return
                    record = self.parse_record(data)
                    if record is None:
                        gc["copy"].pop(0)
                        continue
                    page = gc["next_page"]
                    if page >= self.P:
                        gc["copy"] = []
                        break
                    if not self.program_page(gc["target"], page,
                                             self.record_bytes(block, record[1], record[2])):
                        return
                    gc["next_page"] += 1
                    gc["new_index"][block] = (gc["target"], page, record[1])
                    gc["copy"].pop(0)
                gc["phase"] = "seal"
                continue
            if phase == "seal":
                if "no_seal" in self.flags:
                    self._switch(gc)
                    return
                if not self._afford(self.t_prog):
                    return
                if not self.program_page(gc["target"], 1,
                                         self.seal_bytes(gc["newseq"], len(gc["new_index"]))):
                    return
                self._switch(gc)
                return
            return

    def _switch(self, gc):
        self.index = gc["new_index"]
        self.active = gc["target"]
        self.append = gc["next_page"]
        self.seq = gc["newseq"]
        self.gc = None


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
