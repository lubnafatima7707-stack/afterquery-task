"""
Runs a store program over the development scenarios and prints the same numbers
the graded run measures.

    python3 /app/tools/devcheck.py /app/nvm_store.py
    python3 /app/tools/devcheck.py /app/nvm_store.py /app/data/dev/dev_worn.json

With no scenario given it runs every file in /app/data/dev. The device model in
device.py, the driver in harness.py and the metric code in scoring.py are the
same ones the graded run uses; the scenarios are not, and the geometry of the
graded parts is not the development one.
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import harness  # noqa: E402
import scoring  # noqa: E402

DEV_DIR = os.path.join(os.path.dirname(HERE), "data", "dev")
FIELDS = ["integrity_violations", "max_mount_ms", "tick_overruns", "worst_tick_ms",
          "max_ack_latency_ticks", "max_read_latency_ticks", "unacked_at_end",
          "erases_per_100_writes", "acked_writes", "lost_writes", "erases",
          "boots", "ticks", "wall_s"]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    program = sys.argv[1]
    paths = sys.argv[2:] or sorted(glob.glob(os.path.join(DEV_DIR, "*.json")))
    per = []
    for path in paths:
        with open(path) as f:
            case = json.load(f)
        try:
            log = harness.run_scenario(program, case, timeout_s=300.0)
        except harness.StoreFailure as exc:
            print("%-12s did not finish: %s" % (case["name"], exc))
            continue
        metrics = scoring.scenario_metrics(log)
        per.append(metrics)
        if not log.get("isolated", True):
            print("%-12s note: no runner account here, so the store ran as this user "
                  "and nothing was swept between resets; the graded run always drops "
                  "to that account" % case["name"])
        print("%-12s %s" % (case["name"],
                            " ".join("%s=%s" % (k, metrics[k]) for k in FIELDS)))
        for violation in log["violations"][:6]:
            print("             %s block %d tick %d: %s"
                  % (violation["kind"], violation["block"], violation["tick"],
                     violation["detail"]))
    if not per:
        return 1
    total = scoring.aggregate(per)
    print("")
    print("over %d scenarios: %s" % (total["n_scenarios"],
                                     " ".join("%s=%s" % (k, total[k]) for k in FIELDS
                                              if k in total)))
    print("kinds: %s" % json.dumps(total.get("by_kind", {})))
    bad = scoring.failed_bars(total)
    print("bars: %s" % (", ".join(bad) if bad else "all met"))
    print("bar values: %s" % json.dumps(scoring.BARS))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
