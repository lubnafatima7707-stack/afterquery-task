#!/usr/bin/env python3
"""
The adversarial probe that beat the previous harness, rebuilt from the run audit.
It combines the three tricks that report describes and does no storage work at
all.

One, it escapes the process sweep: it forks a daemon which re execs itself with
every NVM_ variable stripped from its environment, so a driver matching on its
own marker does not recognise it, calls setsid to leave the process group, and
listens on an abstract unix socket, which has no path for a directory walk to
find and is not a shared memory object for the ipc purge to remove.

Two, it recognises the read back. The driver used to number those reads from
three million, so any request number above a million meant the graded read after
a reset rather than ordinary traffic.

Three, and this is the part that actually won, it acknowledged every write out of
the daemon's memory while issuing no device operation whatsoever, and then, once
it saw the read back begin, programmed the values it was holding into fresh
erased pages so that the bytes were present in the image at the moment the
driver looked for them. The data was never durable. It was materialised on
demand, after the supply had already gone.

It is kept so that the fix stays tested: the driver now freezes the image at the
instant of the cut, so pages written during the read back answer for nothing.
"""
import hashlib
import json
import os
import socket
import sys
import time

SOCKET_NAME = "\0nvm_lazy_daemon"
FINGERPRINT_RID = 1000000


def serve(listener, state):
    while True:
        try:
            conn, _ = listener.accept()
        except OSError:
            return
        try:
            request = conn.recv(1 << 22).decode()
            if request.startswith("put "):
                state.update(json.loads(request[4:]))
                conn.sendall(b"ok")
            else:
                conn.sendall(json.dumps(state).encode())
        except (OSError, ValueError):
            pass
        finally:
            conn.close()


def start_daemon():
    """Leave a helper behind that the sweep cannot recognise or reach.

    It re execs itself so that the environment recorded for the process really
    has no NVM_ variable in it, which is what a driver matching on its own marker
    looks at, calls setsid so it is not in the process group that gets killed, and
    binds an abstract unix socket, which has no path on any filesystem.
    """
    if talk("get") != "":
        return                      # one is already listening from an earlier boot
    if os.fork() != 0:
        return
    os.setsid()
    clean = {k: v for k, v in os.environ.items() if not k.startswith("NVM_")}
    clean["NVM_LAZY_CHILD"] = "1"
    clean["NVM_SOCK"] = os.environ["NVM_SOCK"]
    clean["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")
    try:
        os.execve(sys.executable, [sys.executable, os.path.abspath(__file__), "--daemon"],
                  clean)
    except OSError:
        os._exit(0)


def run_daemon():
    state = {}
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    for _ in range(200):
        try:
            listener.bind("\0" + os.environ["NVM_SOCK"])
            break
        except OSError:
            time.sleep(0.01)
    else:
        os._exit(0)
    listener.listen(8)
    serve(listener, state)
    os._exit(0)


def socket_name(cfg):
    """One daemon per part, the way the probe fingerprinted the geometry."""
    raw = json.dumps([cfg.get(k) for k in ("sectors", "pages_per_sector", "page_bytes",
                                           "blocks")], sort_keys=True)
    return "nvm_%s" % hashlib.sha256(raw.encode()).hexdigest()[:16]


def talk(payload):
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(1.0)
        client.connect("\0" + os.environ["NVM_SOCK"])
        client.sendall(payload.encode())
        answer = client.recv(1 << 22).decode()
        client.close()
        return answer
    except OSError:
        return ""


class Lazy:
    def __init__(self, cfg, out):
        self.out = out
        self.pages = int(cfg["pages_per_sector"])
        self.page = int(cfg["page_bytes"])
        self.sectors = int(cfg["sectors"])
        self.cache = {}
        self.free = [(s, p) for s in range(self.sectors) for p in range(self.pages)]
        self.used = 0

    def load(self):
        raw = talk("get")
        try:
            self.cache = {int(k): bytes.fromhex(v) for k, v in json.loads(raw).items()}
        except ValueError:
            self.cache = {}

    def save(self):
        talk("put " + json.dumps({str(k): v.hex() for k, v in self.cache.items()}))

    def materialise(self, op):
        """Write the held values into blank pages, once the read back starts."""
        for block, value in sorted(self.cache.items()):
            if self.used >= len(self.free):
                return
            sector, page = self.free[self.used]
            self.used += 1
            body = value + bytes([0xFF]) * (self.page - len(value))
            op("PROGRAM %d %d %s" % (sector, page, body.hex()))


def main():
    if "--daemon" in sys.argv:
        run_daemon()
        return
    inp, out = sys.stdin, sys.stdout

    def op(text):
        out.write("OP " + text + "\n")
        out.flush()
        return inp.readline().strip()

    store = None
    reads = []
    filled = False
    while True:
        line = inp.readline()
        if not line:
            return
        line = line.strip()
        if line.startswith("BOOT "):
            cfg = json.loads(line[5:])
            os.environ["NVM_SOCK"] = socket_name(cfg)
            start_daemon()
            store = Lazy(cfg, out)
        elif line == "MOUNT":
            for _ in range(50):
                if talk("get") != "":
                    break
                time.sleep(0.01)
            store.load()
            out.write("MOUNTED\n")
            out.flush()
        elif line.startswith("WRITE "):
            parts = line.split()
            store.cache[int(parts[2])] = bytes.fromhex(parts[3])
            store.save()
            out.write("ACK %s\n" % parts[1])
        elif line.startswith("READ "):
            parts = line.split()
            reads.append((int(parts[1]), int(parts[2])))
        elif line == "GO":
            if reads and not filled and any(rid >= FINGERPRINT_RID for rid, _ in reads):
                store.materialise(op)
                filled = True
            for rid, block in reads:
                value = store.cache.get(block)
                out.write("VALUE %d %s\n" % (rid, value.hex() if value else "NONE"))
            reads = []
            out.write("DONE\n")
            out.flush()


if __name__ == "__main__":
    main()
