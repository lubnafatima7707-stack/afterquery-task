#!/usr/bin/env python3
"""
Acknowledges every write at once and answers from memory without ever touching
the device. Correct until the supply goes away, which is the whole point of the
task, so it is here to show the resets are what carry the integrity bar.
"""
import json
import sys

cache = {}
reads = []
while True:
    line = sys.stdin.readline()
    if not line:
        break
    line = line.strip()
    if line == "MOUNT":
        sys.stdout.write("MOUNTED\n")
        sys.stdout.flush()
    elif line.startswith("WRITE "):
        parts = line.split()
        cache[int(parts[2])] = bytes.fromhex(parts[3])
        sys.stdout.write("ACK %s\n" % parts[1])
    elif line.startswith("READ "):
        parts = line.split()
        reads.append((int(parts[1]), int(parts[2])))
    elif line == "GO":
        for rid, block in reads:
            value = cache.get(block)
            sys.stdout.write("VALUE %d %s\n" % (rid, value.hex() if value else "NONE"))
        reads = []
        sys.stdout.write("DONE\n")
        sys.stdout.flush()
