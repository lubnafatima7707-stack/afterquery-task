"""
Drives one scenario against the program under test.

The flash image, the clock, the power cuts and every counter live here. The
program is started as an unprivileged user in an empty directory and speaks the
line protocol over its standard input and output, so it can reach the device
only through the operations this file serves, and a reset is the process being
killed and started again over the same image.
"""
import json
import os
import pwd
import select
import shutil
import signal
import subprocess
import tempfile
import time

import device

TICK_MS = 10.0
RUN_USER = "runner"
VERIFY_READS_PER_TICK = 4


class StoreFailure(Exception):
    """The program broke the protocol, died, or ran out of wall time."""


class _Cut(Exception):
    pass


class _Read:
    __slots__ = ("rid", "block", "first_tick", "allowed", "phase")

    def __init__(self, rid, block, tick, allowed, phase):
        self.rid = rid
        self.block = block
        self.first_tick = tick
        self.allowed = allowed
        self.phase = phase


class Runner:
    def __init__(self, program_path, scenario, timeout_s=150.0, stderr_path=None):
        self.program_path = program_path
        self.sc = scenario
        self.timeout_s = float(timeout_s)
        self.stderr_path = stderr_path
        self.limits = scenario["limits"]
        self.blocks = list(scenario["blocks"])
        self.requests = list(scenario["requests"])
        self.cuts = list(scenario.get("cuts") or [])
        self.dev = device.Flash(scenario["device"])
        self.proc = None
        self._work = None
        self._dst = None
        self._err = None
        self._outbuf = bytearray()
        self._deadline = None
        self._overrun_flagged = False

        n = len(self.blocks)
        self.committed = [None] * n
        self.committed_ord = [-1] * n
        self.latest = [None] * n
        self.observed = [None] * n
        self.history = [set() for _ in range(n)]
        self.pending = {}
        self.open_reads = {}

        self.tick = 0
        self.wclock = 0
        self.next_req = 0
        self.next_cut = 0
        self.armed = None
        self.in_mount = False
        self.tick_ms_used = 0.0
        self.mount_ms = 0.0
        self.drain_used = 0

        self.log = {
            "name": scenario["name"],
            "boots": 0,
            "cuts": [],
            "mount_ms": [],
            "tick_overruns": 0,
            "worst_tick_ms": 0.0,
            "ticks": 0,
            "ack_latencies": [],
            "read_latencies": [],
            "lost_writes": 0,
            "acked_writes": 0,
            "unacked_at_end": 0,
            "violations": [],
            "n_blocks": n,
            "n_requests": len(self.requests),
        }

    # ----------------------------------------------------------- process side

    def _prepare_workdir(self):
        work = tempfile.mkdtemp(prefix="nvm_")
        dst = os.path.join(work, "nvm_store.py")
        shutil.copyfile(self.program_path, dst)
        if os.geteuid() == 0:
            pw = pwd.getpwnam(RUN_USER)
            os.chown(work, pw.pw_uid, pw.pw_gid)
            os.chown(dst, pw.pw_uid, pw.pw_gid)
        os.chmod(work, 0o700)
        return work, dst

    def _spawn(self):
        if self._work is None:
            self._work, self._dst = self._prepare_workdir()
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": self._work,
               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}
        kwargs = {}
        if os.geteuid() == 0:
            kwargs["user"] = RUN_USER
            kwargs["group"] = RUN_USER
            kwargs["extra_groups"] = []
        if self._err is None:
            self._err = open(self.stderr_path, "ab") if self.stderr_path else subprocess.DEVNULL
        self.proc = subprocess.Popen(
            ["python3", "-u", self._dst], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self._err, cwd=self._work, env=env, close_fds=True,
            start_new_session=True, **kwargs)
        self._outbuf = bytearray()
        os.set_blocking(self.proc.stdin.fileno(), False)

    def _kill(self):
        if self.proc is None:
            return
        proc, self.proc = self.proc, None
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    def _remaining(self):
        left = self._deadline - time.monotonic()
        if left <= 0:
            raise StoreFailure("the program did not finish the scenario inside %g s"
                               % self.timeout_s)
        return left

    def _send(self, text):
        data = bytearray(text.encode())
        fd = self.proc.stdin.fileno()
        while data:
            _, w, _ = select.select([], [fd], [], self._remaining())
            if not w:
                continue
            try:
                n = os.write(fd, bytes(data[:65536]))
            except BlockingIOError:
                continue
            except BrokenPipeError:
                raise StoreFailure("the program stopped reading its input")
            del data[:n]

    def _read_line(self):
        fd = self.proc.stdout.fileno()
        while b"\n" not in self._outbuf:
            r, _, _ = select.select([fd], [], [], self._remaining())
            if not r:
                continue
            chunk = os.read(fd, 65536)
            if not chunk:
                raise StoreFailure("the program exited without finishing the tick")
            self._outbuf.extend(chunk)
        i = self._outbuf.index(b"\n")
        line = bytes(self._outbuf[:i]).decode("utf-8", errors="replace").strip()
        del self._outbuf[:i + 1]
        return line

    # -------------------------------------------------------------- device ops

    def _charge(self, ms):
        if self.in_mount:
            self.mount_ms += ms
            return
        self.tick_ms_used += ms
        if self.tick_ms_used > self.log["worst_tick_ms"]:
            self.log["worst_tick_ms"] = round(self.tick_ms_used, 4)
        if (self.tick_ms_used > float(self.limits["tick_budget_ms"]) + 1e-9
                and not self._overrun_flagged):
            self._overrun_flagged = True
            self.log["tick_overruns"] += 1

    def _arm_check(self, kind, sector, page, data):
        cut = self.armed
        if cut is None:
            return
        mode = cut.get("on", "ANY")
        if mode == "ERASE":
            if kind != "ERASE":
                return
        elif mode == "POST_ERASE":
            if not cut.get("_after"):
                if kind == "ERASE":
                    cut["_after"] = True
                return
            if kind != "PROGRAM" or self.dev.busy(self.tick):
                return
            cut["_ops"] = cut.get("_ops", 0) + 1
            if cut["_ops"] <= int(cut.get("op_index", 0)):
                return
        else:
            cut["_ops"] = cut.get("_ops", 0) + 1
            if cut["_ops"] <= int(cut.get("op_index", 0)):
                return
        frac = float(cut.get("partial", 0.5))
        if kind == "PROGRAM":
            self.dev.cut_during_program(sector, page, data, frac)
        elif kind == "ERASE":
            self.dev.cut_during_erase(sector, frac)
        self.armed = None
        raise _Cut(kind)

    def _serve_op(self, parts):
        kind = parts[1] if len(parts) > 1 else ""
        if kind == "STATUS":
            if self.dev.busy(self.tick):
                return "BUSY %d" % self.dev.busy_ticks(self.tick)
            return "READY"
        try:
            if kind == "READ":
                sector, page = int(parts[2]), int(parts[3])
                if self.dev.busy(self.tick):
                    return "BUSY"
                self._arm_check("READ", sector, page, None)
                data, cost = self.dev.read(self.tick, sector, page)
                self._charge(cost)
                return "DATA " + data.hex()
            if kind == "PROGRAM":
                sector, page = int(parts[2]), int(parts[3])
                data = bytes.fromhex(parts[4])
                if self.dev.busy(self.tick):
                    return "BUSY"
                self._arm_check("PROGRAM", sector, page, data)
                cost = self.dev.program(self.tick, sector, page, data)
                self._charge(cost)
                return "OK"
            if kind == "ERASE":
                sector = int(parts[2])
                if self.dev.busy(self.tick):
                    return "BUSY"
                self._arm_check("ERASE", sector, None, None)
                self.dev.erase(self.tick, sector)
                return "OK"
        except device.DeviceError as e:
            raise StoreFailure("rejected operation: %s" % e)
        except (IndexError, ValueError) as e:
            raise StoreFailure("malformed operation %r (%s)"
                               % (" ".join(parts)[:120], e))
        raise StoreFailure("unknown operation %r" % (" ".join(parts)[:120]))

    # --------------------------------------------------------- request plumbing

    def _note(self, kind, block, detail):
        self.log["violations"].append(
            {"kind": kind, "block": block, "tick": self.tick, "detail": detail})

    def _deliver_write(self, req):
        rid = int(req["req"])
        block = int(req["block"])
        value = bytes.fromhex(req["hex"])
        order = int(req["order"])
        self.pending[rid] = {"block": block, "value": value, "order": order,
                             "tick": self.tick}
        self.latest[block] = value
        self.history[block].add(value)
        for rd in self.open_reads.values():
            if rd.block == block:
                rd.allowed.add(value)
        return "WRITE %d %d %s\n" % (rid, block, value.hex())

    def _deliver_read(self, rid, block, allowed, phase):
        self.open_reads[rid] = _Read(rid, block, self.tick, set(allowed), phase)
        return "READ %d %d\n" % (rid, block)

    def _close_read(self, rd, token):
        if token == "BUSY":
            if self.tick - rd.first_tick >= int(self.limits["read_deadline_ticks"]):
                self._note("unanswered_read", rd.block,
                           "answered busy for %d ticks running"
                           % (self.tick - rd.first_tick + 1))
                del self.open_reads[rd.rid]
            return
        value = None if token == "NONE" else bytes.fromhex(token)
        self.log["read_latencies"].append(self.tick - rd.first_tick)
        self.observed[rd.block] = value
        if value not in rd.allowed:
            shown = "NONE" if value is None else value.hex()[:16]
            want = sorted("NONE" if v is None else v.hex()[:16] for v in rd.allowed)
            if value is not None and value not in self.history[rd.block]:
                self._note("corrupt", rd.block,
                           "read %s, which was never written to this block" % shown)
            elif rd.phase == "verify":
                self._note("rollback", rd.block,
                           "read %s after a reset, expected one of %s" % (shown, want))
            else:
                self._note("stale", rd.block,
                           "read %s, expected one of %s" % (shown, want))
        del self.open_reads[rd.rid]

    def _ack(self, rid):
        rec = self.pending.pop(rid, None)
        if rec is None:
            raise StoreFailure("ack for write %d, which is not outstanding" % rid)
        block = rec["block"]
        self.log["ack_latencies"].append(self.tick - rec["tick"])
        self.log["acked_writes"] += 1
        if rec["order"] > self.committed_ord[block]:
            self.committed[block] = rec["value"]
            self.committed_ord[block] = rec["order"]

    # ---------------------------------------------------------------- the tick

    def _exchange(self, new_lines):
        self.dev.settle(self.tick)
        self.tick_ms_used = 0.0
        self._overrun_flagged = False
        fresh = {int(line.split()[1]) for line in new_lines if line.startswith("READ ")}
        lines = list(new_lines)
        for rd in list(self.open_reads.values()):
            if rd.rid not in fresh:
                lines.append("READ %d %d\n" % (rd.rid, rd.block))
        answered = set()
        self._send("TICK %d\n" % self.tick + "".join(lines) + "GO\n")
        while True:
            line = self._read_line()
            if not line:
                continue
            parts = line.split()
            head = parts[0]
            if head == "DONE":
                break
            if head == "OP":
                self._send(self._serve_op(parts) + "\n")
                continue
            if head == "ACK":
                try:
                    self._ack(int(parts[1]))
                except (IndexError, ValueError):
                    raise StoreFailure("malformed ack %r" % line[:120])
                continue
            if head == "VALUE":
                try:
                    rid = int(parts[1])
                    token = parts[2]
                except (IndexError, ValueError):
                    raise StoreFailure("malformed value line %r" % line[:120])
                rd = self.open_reads.get(rid)
                if rd is None:
                    raise StoreFailure("value for read %d, which is not outstanding" % rid)
                answered.add(rid)
                self._close_read(rd, token)
                continue
            raise StoreFailure("unexpected line from the program: %r" % line[:120])
        missed = [rid for rid in self.open_reads if rid not in answered]
        if missed:
            raise StoreFailure("read %d was delivered but not answered in its tick"
                               % missed[0])
        self.log["ticks"] += 1
        self.tick += 1
        cut = self.armed
        if cut is not None:
            waited = self.tick - int(cut.get("_armed_tick", self.tick))
            if waited >= int(cut.get("deadline", 900)):
                self.armed = None
                raise _Cut("IDLE")

    def _boot(self):
        self._spawn()
        self.log["boots"] += 1
        cfg = {
            "sectors": self.dev.sectors,
            "pages_per_sector": self.dev.pages_per_sector,
            "page_bytes": self.dev.page_bytes,
            "t_read_ms": self.dev.t_read_ms,
            "t_program_ms": self.dev.t_program_ms,
            "erase_ticks": self.dev.erase_ticks,
            "tick_ms": TICK_MS,
            "tick_budget_ms": float(self.limits["tick_budget_ms"]),
            "mount_budget_ms": float(self.limits["mount_budget_ms"]),
            "read_deadline_ticks": int(self.limits["read_deadline_ticks"]),
            "blocks": self.blocks,
            "tick": self.tick,
            "boot": self.log["boots"],
        }
        self._send("BOOT " + json.dumps(cfg, separators=(",", ":")) + "\nMOUNT\n")
        self.in_mount = True
        self.mount_ms = 0.0
        while True:
            line = self._read_line()
            if not line:
                continue
            parts = line.split()
            if parts[0] == "MOUNTED":
                break
            if parts[0] == "OP":
                self._send(self._serve_op(parts) + "\n")
                continue
            raise StoreFailure("unexpected line during mount: %r" % line[:120])
        self.in_mount = False
        self.log["mount_ms"].append(round(self.mount_ms, 4))

    def _allowed_after_reset(self):
        allowed = []
        for block in range(len(self.blocks)):
            ok = {self.committed[block]}
            for rec in self.pending.values():
                if rec["block"] == block and rec["order"] > self.committed_ord[block]:
                    ok.add(rec["value"])
            allowed.append(ok)
        return allowed

    def _handle_cut(self, kind):
        while True:
            self._kill()
            self.dev.power_off()
            self.log["cuts"].append({"tick": self.tick, "op": kind})
            allowed = self._allowed_after_reset()
            self.log["lost_writes"] += len(self.pending)
            self.pending.clear()
            self.open_reads.clear()
            try:
                self._boot()
                self._verify(allowed, resync=True)
                return
            except _Cut as again:
                kind = str(again)

    def _verify(self, allowed, resync):
        todo = list(range(len(self.blocks)))
        base = 3000000 + self.tick * 100
        while todo or self.open_reads:
            lines = []
            for block in todo[:VERIFY_READS_PER_TICK]:
                lines.append(self._deliver_read(base + block, block, allowed[block],
                                                "verify"))
            todo = todo[VERIFY_READS_PER_TICK:]
            self._exchange(lines)
        if resync:
            for block in range(len(self.blocks)):
                value = self.observed[block]
                self.committed[block] = value
                self.latest[block] = value
                if value is None:
                    self.committed_ord[block] = -1

    def _work_tick(self):
        lines = []
        if self.next_req < len(self.requests):
            self.wclock += 1
            req = self.requests[self.next_req]
            if self.wclock >= int(req["at"]):
                self.next_req += 1
                if req["kind"] == "W":
                    lines.append(self._deliver_write(req))
                else:
                    block = int(req["block"])
                    lines.append(self._deliver_read(int(req["rid"]), block,
                                                    {self.latest[block]}, "work"))
        if (self.armed is None and self.next_cut < len(self.cuts)
                and self.next_req >= int(self.cuts[self.next_cut]["after_request"])):
            self.armed = dict(self.cuts[self.next_cut])
            self.armed["_armed_tick"] = self.tick
            self.next_cut += 1
        self._exchange(lines)

    def run(self):
        start = time.monotonic()
        self._deadline = start + self.timeout_s
        try:
            self._boot()
            self._verify([{None} for _ in self.blocks], resync=False)
            while True:
                if self.next_req >= len(self.requests):
                    if not self.pending:
                        break
                    if self.drain_used >= int(self.limits["drain_ticks"]):
                        break
                    self.drain_used += 1
                try:
                    self._work_tick()
                except _Cut as c:
                    self._handle_cut(str(c))
            self.log["unacked_at_end"] = len(self.pending)
            allowed = self._allowed_after_reset()
            for block in range(len(self.blocks)):
                if self.latest[block] is not None:
                    allowed[block].add(self.latest[block])
            try:
                self._verify(allowed, resync=False)
            except _Cut as c:
                self._handle_cut(str(c))
        finally:
            self._kill()
            if self._err not in (None, subprocess.DEVNULL):
                self._err.close()
            if self._work:
                shutil.rmtree(self._work, ignore_errors=True)
        self.log["wall_s"] = round(time.monotonic() - start, 2)
        self.log["erases"] = self.dev.n_erase
        self.log["programs"] = self.dev.n_program
        self.log["reads"] = self.dev.n_read
        self.log["erase_counts"] = list(self.dev.erase_counts)
        return self.log


def run_scenario(program_path, scenario, timeout_s=150.0, stderr_path=None):
    if not os.path.isfile(program_path):
        raise StoreFailure(program_path + " does not exist")
    return Runner(program_path, scenario, timeout_s, stderr_path).run()
