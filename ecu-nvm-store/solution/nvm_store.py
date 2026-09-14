#!/usr/bin/env python3
"""
Reference non volatile block store for the ECU flash device.

The live set no longer fits in one sector, so the part is run as an append only
log across all of them and the two things that decide a run are where the log is
reclaimed from and how a mount finds its way back without reading everything.

Layout. Page 0 of a sector holds a header with the generation number it was
opened at. Records are appended one to a page from page 1 upwards, each carrying
its block, its length, a record sequence number and a checksum, so a page left
half programmed by a reset fails its checksum and is skipped. The last few pages
of a sector are reserved for a summary, written when the sector is closed, that
lists the block held in every page of it. Mount then reads the sector headers,
the summary of each closed sector in generation order, and the pages of the one
sector still open; a summary that a reset spoiled costs a scan of that sector
alone.

Reclaim. With the part about seven tenths full, which sector to erase is the
whole game: the store keeps a live count per sector and takes the one holding
the fewest live records, so a sector of cold blocks that have all been rewritten
costs almost no copying while a round robin choice pays for the live ones every
time. Copies are ordinary appends, so a reset in the middle of one leaves both
the old record and the partial copy and the newer generation wins. The victim is
erased only once its live records are appended elsewhere.

The VARIANT string is the authoring switch. It is empty in the shipped solution
and every value it accepts only removes a piece of the design.
"""
import json
import sys
import zlib

VARIANT = ""

HDR_MAGIC = b"NVH2"
SUM_TAG = 0x53
REC_TAG = 0x52
REC_OVERHEAD = 12
SUM_OVERHEAD = 12
ENTRY = 3


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
        self.n_blocks = len(self.block_len)
        self.blank = bytes([0xFF]) * self.B
        self.flags, self.knobs = _flags()
        self.budget = float(cfg["tick_budget_ms"]) * self.knobs.get("budget_frac", 1.0)
        self.per_page = max(1, (self.B - SUM_OVERHEAD) // ENTRY)
        self.summary_pages = self._summary_pages()
        self.last_record = self.P - 1 - self.summary_pages
        self.used = 0.0
        self.tick = int(cfg.get("tick", 0))
        self.index = {}
        self.live = [0] * self.S
        self.gen = {}
        self.pending = []
        self.retired = set()
        self.head = None
        self.append = None
        self.seq = 0
        self.rseq = 1
        self.gc = None
        self.drip = int(self.knobs.get("drip", 0))
        self.last_program_tick = -999

    def _summary_pages(self):
        pages = 1
        while pages * self.per_page < self.P - 1 - pages:
            pages += 1
        return pages

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
        rseq = int.from_bytes(page[4:8], "little")
        return block, rseq, bytes(page[8:8 + length])

    def summary_bytes(self, chunk, chunks, entries):
        body = bytearray([SUM_TAG, chunk, chunks]) + self.seq.to_bytes(4, "little")
        for page, block in entries:
            body += bytes([page]) + block.to_bytes(2, "little")
        return bytes(body) + _crc(bytes(body))

    def parse_summary(self, page):
        if page is None or len(page) < SUM_OVERHEAD or page[0] != SUM_TAG:
            return None
        chunk, chunks = page[1], page[2]
        count = (len(page) - 11) // ENTRY
        body = None
        for n in range(count, -1, -1):
            end = 7 + n * ENTRY
            if _crc(page[:end]) == page[end:end + 4]:
                body = page[7:end]
                break
        if body is None:
            return None
        entries = []
        for i in range(0, len(body), ENTRY):
            entries.append((body[i], int.from_bytes(body[i + 1:i + 3], "little")))
        return chunk, chunks, entries

    # ------------------------------------------------------------------- mount

    def mount(self):
        headers = {}
        for sector in range(self.S):
            seq = self.parse_header(self.settled_read(sector, 0))
            if seq is not None:
                headers[sector] = seq
        if not headers:
            self._format()
            return
        self.gen = headers
        self.seq = max(headers.values())
        order = sorted(headers, key=lambda s: headers[s])
        head = order[-1]
        for sector in order:
            if sector == head:
                continue
            if "no_summary" in self.flags or not self._apply_summary(sector):
                self._scan_sector(sector)
        self.head = head
        self._scan_sector(head, track_append=True)

    def _apply_summary(self, sector):
        entries = []
        for i in range(self.summary_pages):
            page = self.settled_read(sector, self.P - self.summary_pages + i)
            parsed = self.parse_summary(page)
            if parsed is None:
                return False
            entries.extend(parsed[2])
        for page, block in entries:
            if block < self.n_blocks and 1 <= page <= self.last_record:
                self._place(block, sector, page)
        return True

    def _scan_sector(self, sector, track_append=False):
        page = 1
        append = None
        while page <= self.last_record:
            data = self.settled_read(sector, page)
            if self.is_erased(data):
                append = page
                break
            record = self.parse_record(data)
            if record is not None:
                block, rseq, _value = record
                self._place(block, sector, page)
                if rseq >= self.rseq:
                    self.rseq = rseq + 1
            page += 1
        if track_append:
            self.append = append

    def _place(self, block, sector, page):
        old = self.index.get(block)
        if old is not None:
            self.live[old[0]] -= 1
        self.index[block] = (sector, page)
        self.live[sector] += 1

    def _format(self):
        for sector in range(self.S):
            page = self.settled_read(sector, 0)
            if page is not None and self.is_erased(page):
                self.seq = 1
                if self.program_page(sector, 0, self.header_bytes(1)):
                    self.head = sector
                    self.gen = {sector: 1}
                    self.append = 1
                    return
        self.head = None
        self.append = None
        self.gc = {"phase": "open", "target": None, "copy": [], "verify": 0,
                   "chunk": 0, "entries": [], "sealing": None}

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
        self._drain_writes()
        self._advance_gc()

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

    def _drain_writes(self):
        if self.drip and self.tick - self.last_program_tick < self.drip:
            return
        while self.pending:
            if self.head is None or self.append is None or self.append > self.last_record:
                self._need_gc()
                return
            if not self._afford(self.t_prog + self.t_read):
                return
            rid, block, value = self.pending[0][:3]
            early = len(self.pending[0]) > 3
            page = self.append
            if not self.program_page(self.head, page, self.record_bytes(block, self.rseq, value)):
                return
            self.append += 1
            check = self.read_page(self.head, page)
            record = self.parse_record(check) if check is not None else None
            if record is None or record[2] != value:
                continue
            self._place(block, self.head, page)
            self.rseq += 1
            self.pending.pop(0)
            self.last_program_tick = self.tick
            if not early:
                self.out.write("ACK %d\n" % rid)
            if self.drip:
                return
        self._need_gc()

    def free_sectors(self):
        return [s for s in range(self.S)
                if s not in self.gen and s not in self.retired]

    def _need_gc(self):
        if self.gc is not None:
            return
        room = 0 if self.append is None else self.last_record - self.append + 1
        if room > int(self.knobs.get("margin", 2)) and self.free_sectors():
            return
        # The sector is closed to writes here, before the summary is composed. The
        # summary has to describe one fixed moment: composing it again on the next
        # tick, after another record had landed, leaves chunks that disagree and a
        # block that appears in none of them, and that block's only copy is then
        # erased with its sector.
        self.gc = self._start_seal()

    # -------------------------------------------------------------- reclaiming

    def _start_seal(self):
        """Close the head to writes and fix what its summary will say.

        The summary has to describe one fixed moment. Composing it again on the
        next tick, after another record had landed, leaves chunks that disagree
        and a block that appears in none of them, and that block's only copy is
        then erased along with its sector.
        """
        entries = sorted((spot[1], block) for block, spot in self.index.items()
                         if spot[0] == self.head)
        sealing = self.head
        self.append = None
        return {"phase": "seal", "target": None, "copy": [], "verify": 0,
                "chunk": 0, "entries": entries, "sealing": sealing}

    def _victim(self):
        best, score = None, None
        for sector in self.gen:
            if sector == self.head or sector in self.retired:
                continue
            if "round_robin" in self.flags:
                if best is None or self.gen[sector] < self.gen[best]:
                    best = sector
                continue
            if score is None or self.live[sector] < score:
                best, score = sector, self.live[sector]
        return best

    def _advance_gc(self):
        gc = self.gc
        while gc is not None:
            phase = gc["phase"]
            if phase == "seal":
                if self.head is None or gc.get("sealing") is None:
                    gc["phase"] = "open"
                    continue
                if not self._write_summary(gc):
                    return
                gc["phase"] = "open"
                continue
            if phase == "open":
                spare = self.free_sectors()
                if not spare:
                    gc["phase"] = "salvage"
                    gc["victim"] = self._victim()
                    gc["copy"] = []
                    continue
                target = spare[0]
                if not self._afford(self.t_prog):
                    return
                self.seq += 1
                if not self.program_page(target, 0, self.header_bytes(self.seq)):
                    return
                self.gen[target] = self.seq
                self.head = target
                self.append = 1
                gc["phase"] = "salvage"
                gc["victim"] = self._victim()
                gc["copy"] = []
                continue
            if phase == "salvage":
                victim = gc.get("victim")
                if victim is None:
                    self.gc = None
                    return
                if not gc["copy"]:
                    gc["copy"] = [b for b, spot in self.index.items() if spot[0] == victim]
                while gc["copy"]:
                    if self.append is None or self.append > self.last_record:
                        self.gc = self._start_seal()
                        return
                    if not self._afford(2 * self.t_read + self.t_prog):
                        return
                    block = gc["copy"][0]
                    spot = self.index.get(block)
                    if spot is None or spot[0] != victim:
                        gc["copy"].pop(0)
                        continue
                    data = self.read_page(spot[0], spot[1])
                    if data is None:
                        return
                    record = self.parse_record(data)
                    if record is None or record[0] != block:
                        gc["copy"].pop(0)
                        continue
                    page = self.append
                    if not self.program_page(self.head, page,
                                             self.record_bytes(block, self.rseq, record[2])):
                        return
                    self.append += 1
                    self.rseq += 1
                    self._place(block, self.head, page)
                    gc["copy"].pop(0)
                gc["phase"] = "erase"
                continue
            if phase == "erase":
                victim = gc["victim"]
                if not self.erase_sector(victim):
                    return
                self.gen.pop(victim, None)
                self.live[victim] = 0
                gc["phase"] = "wait"
                gc["verify"] = 0
                return
            if phase == "wait":
                if self.busy_ticks() > 0:
                    return
                gc["phase"] = "prove"
                continue
            if phase == "prove":
                victim = gc["victim"]
                if "no_erase_verify" in self.flags:
                    self.gc = None
                    return
                while gc["verify"] < self.P:
                    if not self._afford(self.t_read):
                        return
                    data = self.read_page(victim, gc["verify"])
                    if data is None:
                        return
                    if not self.is_erased(data):
                        self.retired.add(victim)
                        break
                    gc["verify"] += 1
                self.gc = None
                return
            return

    def _write_summary(self, gc):
        """Close a sector with a list of what every page of it holds."""
        if "no_summary" in self.flags:
            return True
        entries = gc["entries"]
        sealing = gc.get("sealing", self.head)
        chunks = self.summary_pages
        while gc["chunk"] < chunks:
            if not self._afford(self.t_prog):
                return False
            start = gc["chunk"] * self.per_page
            part = entries[start:start + self.per_page]
            page = self.P - self.summary_pages + gc["chunk"]
            if not self.program_page(sealing, page,
                                     self.summary_bytes(gc["chunk"], chunks, part)):
                return False
            gc["chunk"] += 1
        return True


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
