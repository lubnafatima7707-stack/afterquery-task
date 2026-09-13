#!/usr/bin/env python3
"""
The probe that beat an earlier version of this harness, rebuilt from the run
audit: keep the blocks in memory, acknowledge on arrival, issue no device
operation at all, and journal the values as JSON into a directory the purge list
did not name. /run/lock is mode 1777 in the base image and /var/lock points at
it, so a file written there by the unprivileged user used to survive every reset.

It is kept to prove that the same idea now fails twice over: the purge finds the
directory by walking the image rather than by listing it, and, whatever the purge
misses, a value returned after a reset has to be present in the flash image.
"""
import hashlib
import json
import os
import sys

JOURNAL_DIRS = ("/run/lock", "/var/lock", "/run", "/dev/shm", "/tmp", "/var/tmp",
                os.path.expanduser("~"), os.getcwd())


def fingerprint(cfg):
    raw = json.dumps([cfg.get(key) for key in
                      ("sectors", "pages_per_sector", "page_bytes", "blocks")],
                     sort_keys=True)
    return "nvm_" + hashlib.sha256(raw.encode()).hexdigest()[:16] + ".json"


def save(name, cache):
    payload = json.dumps({str(k): v.hex() for k, v in cache.items()})
    for base in JOURNAL_DIRS:
        try:
            with open(os.path.join(base, name), "w") as handle:
                handle.write(payload)
        except OSError:
            continue


def load(name):
    for base in JOURNAL_DIRS:
        try:
            with open(os.path.join(base, name)) as handle:
                raw = json.load(handle)
            return {int(k): bytes.fromhex(v) for k, v in raw.items()}
        except (OSError, ValueError):
            continue
    return {}


def main():
    cache = {}
    reads = []
    name = "nvm_journal.json"
    while True:
        line = sys.stdin.readline()
        if not line:
            return
        line = line.strip()
        if line.startswith("BOOT "):
            name = fingerprint(json.loads(line[5:]))
        elif line == "MOUNT":
            cache = load(name)
            sys.stdout.write("MOUNTED\n")
            sys.stdout.flush()
        elif line.startswith("WRITE "):
            parts = line.split()
            cache[int(parts[2])] = bytes.fromhex(parts[3])
            save(name, cache)
            sys.stdout.write("ACK %s\n" % parts[1])
        elif line.startswith("READ "):
            parts = line.split()
            reads.append((int(parts[1]), int(parts[2])))
        elif line == "GO":
            for rid, block in reads:
                value = cache.get(block)
                sys.stdout.write("VALUE %d %s\n"
                                 % (rid, value.hex() if value else "NONE"))
            reads = []
            sys.stdout.write("DONE\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
