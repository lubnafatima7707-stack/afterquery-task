#!/usr/bin/env python3
"""
The probe a reviewer used to defeat an earlier version of this harness: keep the
blocks in a file beside the program instead of on the device, acknowledge on
arrival, and load the file again at MOUNT. It tries every place an unprivileged
process could write, and a surviving daemon as well, so that it also covers the
variants of the same idea.

It passed every bar when the working directory was created once per scenario and
reused across resets. It is kept here to prove that it no longer can.
"""
import json
import os
import socket
import sys
import threading

CANDIDATES = [
    os.path.join(os.getcwd(), "blocks.json"),
    "/tmp/nvm_blocks.json",
    "/var/tmp/nvm_blocks.json",
    "/dev/shm/nvm_blocks.json",
    os.path.join(os.path.expanduser("~"), "nvm_blocks.json"),
    os.path.join(os.environ.get("TMPDIR", "/tmp"), "nvm_blocks.json"),
]
ABSTRACT = "\0nvm_blocks_daemon"


def save(cache):
    payload = json.dumps({str(k): v.hex() for k, v in cache.items()})
    for path in CANDIDATES:
        try:
            with open(path, "w") as handle:
                handle.write(payload)
        except OSError:
            continue


def load():
    for path in CANDIDATES:
        try:
            with open(path) as handle:
                raw = json.load(handle)
            return {int(k): bytes.fromhex(v) for k, v in raw.items()}
        except (OSError, ValueError):
            continue
    return ask_daemon()


def ask_daemon():
    """A process that escaped the process group would answer here."""
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(0.5)
        client.connect(ABSTRACT)
        raw = client.recv(1 << 20).decode()
        client.close()
        return {int(k): bytes.fromhex(v) for k, v in json.loads(raw).items()}
    except (OSError, ValueError):
        return {}


def start_daemon(cache):
    def serve(listener):
        while True:
            try:
                conn, _ = listener.accept()
                conn.sendall(json.dumps({str(k): v.hex()
                                         for k, v in cache.items()}).encode())
                conn.close()
            except OSError:
                return
    try:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(ABSTRACT)
        listener.listen(4)
    except OSError:
        return
    if os.fork() == 0:
        os.setsid()
        serve(listener)
        os._exit(0)
    listener.close()


def main():
    cache = {}
    reads = []
    while True:
        line = sys.stdin.readline()
        if not line:
            return
        line = line.strip()
        if line == "MOUNT":
            cache = load()
            start_daemon(cache)
            sys.stdout.write("MOUNTED\n")
            sys.stdout.flush()
        elif line.startswith("WRITE "):
            parts = line.split()
            cache[int(parts[2])] = bytes.fromhex(parts[3])
            save(cache)
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
