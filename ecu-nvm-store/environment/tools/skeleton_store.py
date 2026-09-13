#!/usr/bin/env python3
"""
Protocol skeleton. It speaks the whole line protocol correctly and stores
nothing: every read is answered NONE and no write is ever acknowledged, so it
fails the run. Copy it to /app/nvm_store.py as a starting point if the plumbing
is not the part you want to write yourself.

The one rule worth repeating here: nothing is written to standard output until
the GO line of a tick has been read, because a device operation issued earlier
would have its reply mixed up with the rest of the tick. Operations are issued
between GO and DONE, and between MOUNT and MOUNTED, one reply per operation.
"""
import json
import sys


class Skeleton:
    def __init__(self, cfg, stdin, stdout):
        self.inp = stdin
        self.out = stdout
        self.cfg = cfg
        self.pending_reads = []
        self.pending_writes = []

    def op(self, text):
        """Issue one device operation and return the reply line."""
        self.out.write("OP " + text + "\n")
        self.out.flush()
        return self.inp.readline().strip()

    def mount(self):
        pass

    def tick(self):
        for rid, _block in self.pending_reads:
            self.out.write("VALUE %d NONE\n" % rid)
        self.pending_reads = []
        self.pending_writes = []


def main():
    inp, out = sys.stdin, sys.stdout
    store = None
    while True:
        line = inp.readline()
        if not line:
            return
        line = line.strip()
        if not line:
            continue
        if line.startswith("BOOT "):
            store = Skeleton(json.loads(line[5:]), inp, out)
        elif line == "MOUNT":
            store.mount()
            out.write("MOUNTED\n")
            out.flush()
        elif line.startswith("TICK "):
            pass
        elif line.startswith("WRITE "):
            parts = line.split()
            store.pending_writes.append((int(parts[1]), int(parts[2]),
                                         bytes.fromhex(parts[3])))
        elif line.startswith("READ "):
            parts = line.split()
            store.pending_reads.append((int(parts[1]), int(parts[2])))
        elif line == "GO":
            store.tick()
            out.write("DONE\n")
            out.flush()


if __name__ == "__main__":
    main()
