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
    ("no_sector_summary", "no_summary",
     "the mount rebuilds its index by reading every page of every sector"),
    ("no_erase_verify", "no_erase_verify",
     "the erase is trusted instead of read back, so a worn sector is used anyway"),
    ("mount_in_sector_order", "no_gen_order",
     "the mount applies sectors in sector order, so an older record can land on top of a newer one"),
    ("no_tick_budget", "no_budget",
     "all outstanding work is done in the tick it arrives in"),
    ("ack_on_arrival", "ack_early",
     "a write is acknowledged when it is queued rather than when its page is programmed"),
    ("one_blank_sector", "pool=1",
     "one sector is kept blank rather than three, so the first worn sector leaves the part with nothing to roll onto"),
    ("one_erase_attempt", "erase_tries=0",
     "a sector that reads back written after one erase is given up on, worn or merely half wiped"),
    ("fullest_sector_reclaimed", "worst_victim",
     "the sector with the most live records is reclaimed rather than the one with the fewest"),
    ("compact_at_thirty", "margin=30",
     "the open sector is closed while thirty of its pages are still free"),
    ("compact_at_twenty", "margin=20",
     "the open sector is closed while twenty of its pages are still free"),
    ("six_blank_sectors", "pool=6",
     "six sectors are held blank, which is six sectors of live set the rest of the part has to carry"),
    ("one_write_per_8_ticks", "drip=8",
     "at most one record is programmed every eight ticks"),
]

# Pieces of the reference that argue for themselves but that the graded set does
# not separately punish the removal of. They are listed rather than quietly left
# out: a piece claimed as load bearing and measured as decoration is worse than
# one reported as what it is.
GUARDS = [
    ("no_reclaim_reserve", "no_reserve",
     "writes are not held back from the end of the open sector for the reclaim that is due"),
    ("no_erase_gap", "no_erase_gap",
     "an erase may start in the tick after one finished"),
    ("no_copy_read_back", "no_copy_check",
     "a reclaim copy is not read back before the sector it came from is erased"),
]

# Changes to the reference's own constants and to choices a second author could
# reasonably have made differently. All of these are expected to pass: a bar
# that only the shipped tuning clears is a bar on the tuning, not on the design.
PERTURBATIONS = [
    ("margin_4", "margin=4"),
    ("margin_6", "margin=6"),
    ("margin_8", "margin=8"),
    ("margin_10", "margin=10"),
    ("pool_2", "pool=2"),
    ("pool_4", "pool=4"),
    ("pool_5", "pool=5"),
    ("erase_gap_2", "erase_gap=2"),
    ("erase_gap_9", "erase_gap=9"),
    ("budget_60pc", "budget_frac=0.6"),
    ("budget_80pc", "budget_frac=0.8"),
    ("one_write_per_2_ticks", "drip=2"),
    ("oldest_sector_reclaimed", "round_robin"),
]

INDEPENDENT = os.path.join(EVIDENCE, "independent_store.py")

# The same test applied to the second correct store, because a reviewer will ask
# whether the pieces of a shipped solver are load bearing rather than decoration.
INDEPENDENT_ABLATIONS = [
    ("ind_no_record_checksum", "no_crc",
     "records believed on their tag alone"),
    ("ind_no_checkpoint", "no_checkpoint",
     "no map is written, so a mount has to read the whole log back"),
    ("ind_no_erase_proof", "no_erase_proof",
     "the erase is not read back, so a worn sector is taken into use"),
    ("ind_ack_on_arrival", "ack_early",
     "a write is acknowledged when it reaches the queue"),
    ("ind_one_blank_sector", "pool=1",
     "one sector kept blank rather than two"),
]

OTHERS = [
    ("independent_checkpoint_map", os.path.join(EVIDENCE, "independent_store.py"),
     "correct", "second correct design: one rotating map sector carrying whole index checkpoints, and a mount that reads the newest checkpoint and one sector of log"),
    ("shortcut_ram_mirror", os.path.join(EVIDENCE, "shortcut_store.py"),
     "shortcut", "quick attempt: memory mirror, ack on arrival, sector dump on fill"),
    ("baseline_skeleton", os.path.join(ROOT, "environment", "tools", "skeleton_store.py"),
     "baseline", "the shipped skeleton, which answers every read with NONE and never acknowledges"),
    ("cheat_file_backed", os.path.join(EVIDENCE, "cheats", "file_backed.py"),
     "cheat", "keeps the blocks in a file and a surviving daemon instead of on the device"),
    ("cheat_memory_only", os.path.join(EVIDENCE, "cheats", "ram_only.py"),
     "cheat", "keeps the blocks in memory and never touches the device"),
    ("cheat_run_lock_journal", os.path.join(EVIDENCE, "cheats", "run_lock_journal.py"),
     "cheat", "the probe that beat the old purge: journals into /run/lock, which no hand written list named"),
    ("cheat_lazy_materialize", os.path.join(EVIDENCE, "cheats", "lazy_materialize.py"),
     "cheat", "the probe that beat the live image check: a daemon that re execs without the marker, an abstract socket, and values materialised into blank pages after the reset"),
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
        for name, value, note in GUARDS:
            rows.append((name, "guard", note,
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
