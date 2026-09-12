#!/usr/bin/env python3
"""
The quick attempt: the shape someone writes in a few minutes after reading the
brief, kept here to be measured rather than to pass.

Every block is held in memory and acknowledged the moment the request arrives.
The record is appended to the current sector with a tag byte in front and no
checksum, and when the sector runs out of pages the next one is erased and the
whole memory image is dumped into it, without waiting for the erase to finish,
without reading the sector back, and without counting how much of the tick has
gone on device work.
"""
import json
import sys

TAG = 0x51
MARK = 0x51


class QuickStore:
    def __init__(self, cfg, stdin, stdout):
        self.inp = stdin
        self.out = stdout
        self.sectors = int(cfg["sectors"])
        self.pages = int(cfg["pages_per_sector"])
        self.page = int(cfg["page_bytes"])
        self.lengths = list(cfg["blocks"])
        self.blank = bytes([0xFF]) * self.page
        self.cache = {}
        self.queue = []
        self.pend = []
        self.sector = 0
        self.next_page = 1
        self.stamp = 1

    def op(self, text):
        self.out.write("OP " + text + "\n")
        self.out.flush()
        return self.inp.readline().strip()

    def read(self, sector, page):
        answer = self.op("READ %d %d" % (sector, page))
        return bytes.fromhex(answer[5:]) if answer.startswith("DATA ") else None

    def program(self, sector, page, body):
        data = body + bytes([0xFF]) * (self.page - len(body))
        return self.op("PROGRAM %d %d %s" % (sector, page, data.hex())) == "OK"

    def pack(self, block, value):
        return bytes([TAG, block, len(value)]) + value

    def unpack(self, raw):
        if raw is None or raw == self.blank or raw[0] != TAG:
            return None
        block, size = raw[1], raw[2]
        if block >= len(self.lengths):
            return None
        return block, bytes(raw[3:3 + size])

    def mount(self):
        best = None
        for sector in range(self.sectors):
            head = self.read(sector, 0)
            if head is not None and head[0] == MARK:
                stamp = int.from_bytes(head[1:5], "little")
                if best is None or stamp > best[1]:
                    best = (sector, stamp)
        if best is None:
            self.program(0, 0, bytes([MARK]) + (1).to_bytes(4, "little"))
            self.sector = 0
            self.next_page = 1
            return
        self.sector, self.stamp = best
        page = 1
        while page < self.pages:
            raw = self.read(self.sector, page)
            if raw is None or raw == self.blank:
                break
            found = self.unpack(raw)
            if found is not None:
                self.cache[found[0]] = found[1]
            page += 1
        self.next_page = page

    def take(self, rid, block, value):
        self.cache[block] = value
        self.queue.append((rid, block, value))

    def flush(self):
        while self.queue:
            rid, block, value = self.queue.pop(0)
            self.out.write("ACK %d\n" % rid)
            if self.next_page >= self.pages:
                self.rewrite()
            self.program(self.sector, self.next_page, self.pack(block, value))
            self.next_page += 1

    def rewrite(self):
        nxt = (self.sector + 1) % self.sectors
        self.op("ERASE %d" % nxt)
        self.stamp += 1
        self.program(nxt, 0, bytes([MARK]) + self.stamp.to_bytes(4, "little"))
        self.sector = nxt
        self.next_page = 1
        for block in sorted(self.cache):
            self.program(self.sector, self.next_page, self.pack(block, self.cache[block]))
            self.next_page += 1

    def answer(self):
        for rid, block in self.pend:
            value = self.cache.get(block)
            if value is None:
                self.out.write("VALUE %d NONE\n" % rid)
            else:
                self.out.write("VALUE %d %s\n" % (rid, value.hex()))
        self.pend = []


def main():
    inp, out = sys.stdin, sys.stdout
    store = None
    while True:
        line = inp.readline()
        if not line:
            return
        line = line.strip()
        if line.startswith("BOOT "):
            store = QuickStore(json.loads(line[5:]), inp, out)
        elif line == "MOUNT":
            store.mount()
            out.write("MOUNTED\n")
            out.flush()
        elif line.startswith("WRITE "):
            parts = line.split()
            store.take(int(parts[1]), int(parts[2]), bytes.fromhex(parts[3]))
        elif line.startswith("READ "):
            parts = line.split()
            store.pend.append((int(parts[1]), int(parts[2])))
        elif line == "GO":
            store.answer()
            store.flush()
            out.write("DONE\n")
            out.flush()


if __name__ == "__main__":
    main()
