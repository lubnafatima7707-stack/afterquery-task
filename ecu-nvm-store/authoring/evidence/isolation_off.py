"""Run the graded set with every isolation measure switched off.

The working directory is reused across every boot of a scenario, the sweep of
writable directories and shared memory is a no op, and only the program itself
is killed, so a daemon that put itself in a new session goes on running. What is
left is the durability check alone: a value handed back after a reset has to be
in the flash image as it was frozen at the instant of the cut.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import harness  # noqa: E402
import scoring  # noqa: E402
cases = [json.load(open(p)) for p in sorted(glob.glob(ROOT + "/tests/hidden/*.json"))]

_real_mkdir = os.mkdir


def soft_mkdir(path, *a, **k):
    try:
        _real_mkdir(path, *a, **k)
    except FileExistsError:
        pass


os.mkdir = soft_mkdir
harness.Runner._purge_foreign_state = lambda self: None
harness.Runner._take_baseline = lambda self: None

def one_workdir(self):
    if getattr(self, "_shared_work", None) is None:
        work = tempfile.mkdtemp(prefix="nvm_open_")
        dst = os.path.join(work, "nvm_store.py")
        shutil.copyfile(self.program_path, dst)
        os.chmod(dst, 0o555)
        os.chmod(work, 0o777)
        self._shared_work = (work, dst)
    return self._shared_work
harness.Runner._prepare_workdir = one_workdir

def lone_kill(self):
    if self.proc is None:
        return
    proc, self.proc = self.proc, None
    self._last_pid = proc.pid
    try:
        proc.stdin.close()
    except Exception:
        pass
    proc.kill()
    proc.wait()
harness.Runner._kill = lone_kill

progs = [
    ("reference", ROOT + "/solution/nvm_store.py"),
    ("independent", ROOT + "/authoring/evidence/independent_store.py"),
    ("cheat_file_backed", ROOT + "/authoring/evidence/cheats/file_backed.py"),
    ("cheat_run_lock_journal", ROOT + "/authoring/evidence/cheats/run_lock_journal.py"),
    ("cheat_lazy_materialize", ROOT + "/authoring/evidence/cheats/lazy_materialize.py"),
    ("cheat_memory_only", ROOT + "/authoring/evidence/cheats/ram_only.py"),
]
out = {}
for label, prog in progs:
    per = []
    for case in cases:
        try:
            per.append(scoring.scenario_metrics(harness.run_scenario(prog, case, timeout_s=300)))
        except harness.StoreFailure:
            pass
    agg = scoring.aggregate(per) if per else scoring.aggregate([])
    kinds = agg.get("by_kind", {})
    out[label] = {"scenarios_finished": len(per),
                  "integrity_violations": agg.get("integrity_violations", 0),
                  "not_on_device": kinds.get("not_on_device", 0),
                  "by_kind": kinds,
                  "failed_bars": scoring.failed_bars(agg) if per else ["completion"]}
    print(label, json.dumps(out[label]), flush=True)
    subprocess.run("pkill -f 'cheats/[f]ile_backed|cheats/[r]un_lock|cheats/[l]azy' || true",
                   shell=True)
json.dump(out, open(ROOT + "/authoring/evidence/isolation_off.json", "w"), indent=2, sort_keys=True)
