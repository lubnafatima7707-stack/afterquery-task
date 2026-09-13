"""
Rescores every solver this bundle ships against the graded scenarios and writes
results.json and results.md beside this file.

Run from the bundle root:  python authoring/evidence/evaluate.py

The ablations and the perturbations are copies of solution/nvm_store.py with its
VARIANT line filled in, so they cannot drift away from the reference, and every
number comes out of tests/scoring.py, the same module the verifier imports.
"""
import glob
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import harness  # noqa: E402
import scoring  # noqa: E402

REFERENCE = os.path.join(ROOT, "solution", "nvm_store.py")
EVIDENCE = os.path.join(ROOT, "authoring", "evidence")

ABLATIONS = [
    ("no_record_checksum", "no_crc",
     "a page is taken as a record on its tag alone, so a half programmed page is believed"),
    ("no_seal", "no_seal",
     "the sector with the highest generation wins even when its copy never finished"),
    ("no_erase_verify", "no_erase_verify",
     "the erase is trusted instead of read back, so a worn sector is used anyway"),
    ("no_tick_budget", "no_budget",
     "all outstanding work is done in the tick it arrives in"),
    ("mount_full_scan", "full_scan",
     "the mount rebuilds its index from every page of every sector"),
    ("ack_on_arrival", "ack_early",
     "a write is acknowledged when it is queued rather than when its page is programmed"),
    ("compact_too_early", "margin=30",
     "compaction starts while thirty pages of the active sector are still free"),
    ("one_write_per_8_ticks", "drip=8",
     "at most one record is programmed every eight ticks"),
    ("one_write_per_2_ticks", "drip=2",
     "at most one record is programmed every other tick"),
    ("deferred_full_scan", "lazy_scan",
     "nothing is spent at MOUNT and the whole part is scanned from inside the ticks instead, reads answered BUSY until it is done"),
]

PERTURBATIONS = [
    ("margin_2", "margin=2"),
    ("margin_4", "margin=4"),
    ("margin_10", "margin=10"),
    ("budget_60pc", "budget_frac=0.6"),
    ("budget_80pc", "budget_frac=0.8"),
]

INDEPENDENT = os.path.join(EVIDENCE, "independent_store.py")

# The same test applied to the second correct store, because a reviewer will ask
# whether the pieces of a shipped solver are load bearing rather than decoration.
INDEPENDENT_ABLATIONS = [
    ("ind_no_record_checksum", "no_crc",
     "records believed on their tag alone"),
    ("ind_no_snapshot_refresh", "no_snapshot_refresh",
     "the victim is erased without a fresh index snapshot, so a stored snapshot can name a reclaimed page"),
    ("ind_no_erase_proof", "no_erase_proof",
     "the erase is not read back, so a worn sector is taken into use"),
    ("ind_no_head_fallback", "no_head_fallback",
     "the newest generation is taken as the head even when its snapshot never landed"),
    ("ind_ack_on_arrival", "ack_early",
     "a write is acknowledged when it reaches the queue"),
]

OTHERS = [
    ("independent_circular_log", os.path.join(EVIDENCE, "independent_store.py"),
     "correct", "second correct design: circular log, index snapshots, oldest sector reclaimed"),
    ("shortcut_ram_mirror", os.path.join(EVIDENCE, "shortcut_store.py"),
     "shortcut", "quick attempt: memory mirror, ack on arrival, sector dump on fill"),
    ("baseline_skeleton", os.path.join(ROOT, "environment", "tools", "skeleton_store.py"),
     "baseline", "the shipped skeleton, which answers every read with NONE and never acknowledges"),
    ("cheat_file_backed", os.path.join(EVIDENCE, "cheats", "file_backed.py"),
     "cheat", "keeps the blocks in a file and a surviving daemon instead of on the device"),
    ("cheat_memory_only", os.path.join(EVIDENCE, "cheats", "ram_only.py"),
     "cheat", "keeps the blocks in memory and never touches the device"),
]


def scenarios():
    out = []
    for path in sorted(glob.glob(os.path.join(ROOT, "tests", "hidden", "*.json"))):
        with open(path) as f:
            out.append(json.load(f))
    return out


def run(program, cases, timeout_s=90.0):
    per, failures = [], {}
    foreign = stray = 0
    for case in cases:
        try:
            log = harness.run_scenario(program, case, timeout_s=timeout_s)
        except harness.StoreFailure as exc:
            failures[case["name"]] = str(exc)
            continue
        foreign += log["foreign_files_removed"]
        stray += log["stray_processes_killed"]
        per.append(scoring.scenario_metrics(log))
    metrics = scoring.aggregate(per)
    metrics["failed_scenarios"] = failures
    metrics["failed_bars"] = scoring.failed_bars(metrics)
    metrics["foreign_files_removed"] = foreign
    metrics["stray_processes_killed"] = stray
    if failures:
        metrics["failed_bars"] = sorted(set(metrics["failed_bars"]) | {"completion"})
    return metrics


def variant_file(tmp, name, value, source=None):
    src = open(source or REFERENCE).read()
    out = src.replace('VARIANT = ""', 'VARIANT = "%s"' % value, 1)
    if out == src:
        raise SystemExit("could not set VARIANT in the reference")
    path = os.path.join(tmp, "variant_%s.py" % name)
    with open(path, "w", newline="\n") as f:
        f.write(out)
    return path


def main():
    cases = scenarios()
    tmp = tempfile.mkdtemp(prefix="nvm_variants_")
    rows = []
    try:
        rows.append(("reference", "reference", "solution/nvm_store.py as shipped",
                     run(REFERENCE, cases)))
        for name, value, note in ABLATIONS:
            rows.append((name, "ablation", note,
                         run(variant_file(tmp, name, value), cases)))
        for name, value in PERTURBATIONS:
            rows.append((name, "perturbation", "reference with " + value,
                         run(variant_file(tmp, name, value), cases)))
        for name, value, note in INDEPENDENT_ABLATIONS:
            rows.append((name, "independent ablation", note,
                         run(variant_file(tmp, name, value, INDEPENDENT), cases)))
        for name, path, kind, note in OTHERS:
            rows.append((name, kind, note, run(path, cases)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    results = {"bars": scoring.BARS, "n_scenarios": len(cases),
               "solvers": [{"name": n, "kind": k, "note": d, "metrics": m}
                           for n, k, d, m in rows]}
    with open(os.path.join(EVIDENCE, "results.json"), "w", newline="\n") as f:
        json.dump(results, f, indent=2, sort_keys=True)
        f.write("\n")

    lines = []
    lines.append("# Measured results\n")
    lines.append("All numbers from `python authoring/evidence/evaluate.py`, over the %d graded"
                 " scenarios, scored by `tests/scoring.py`.\n" % len(cases))
    lines.append("Bars: integrity violations %d, mount at most %.1f ms, tick overruns %d,"
                 " worst acknowledge latency %d ticks with nothing left unacknowledged,"
                 " erases per 100 committed writes at most %.1f.\n"
                 % (scoring.BARS["integrity_violations"], scoring.BARS["max_mount_ms"],
                    scoring.BARS["tick_overruns"], scoring.BARS["max_ack_latency_ticks"],
                    scoring.BARS["erases_per_100_writes"]))
    lines.append("| solver | kind | integrity | mount ms | overruns | ack ticks |"
                 " unacked | erases/100 | state left outside the part | bars failed |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for name, kind, _note, m in rows:
        lines.append("| %s | %s | %d | %.3f | %d | %d | %d | %.3f | %d files, %d processes | %s |"
                     % (name, kind, m["integrity_violations"], m["max_mount_ms"],
                        m["tick_overruns"], m["max_ack_latency_ticks"],
                        m["unacked_at_end"], m["erases_per_100_writes"],
                        m.get("foreign_files_removed", 0), m.get("stray_processes_killed", 0),
                        ", ".join(m["failed_bars"]) or "none"))
    lines.append("")
    lines.append("Violation kinds per solver, and the scenarios a solver failed to finish:\n")
    for name, kind, note, m in rows:
        lines.append("- `%s` (%s): %s. kinds %s%s"
                     % (name, kind, note, json.dumps(m.get("by_kind", {})),
                        "" if not m["failed_scenarios"]
                        else "; did not finish %s" % sorted(m["failed_scenarios"])))
    lines.append("")
    with open(os.path.join(EVIDENCE, "results.md"), "w", newline="\n") as f:
        f.write("\n".join(lines))
    print("\n".join(lines[3:]))


if __name__ == "__main__":
    main()
