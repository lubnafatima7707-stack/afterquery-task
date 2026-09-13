"""
Sealed verifier for ecu-nvm-store.

Each graded scenario is driven by harness.py, which owns the flash image, the
clock and the resets, and which starts the agent's program as an unprivileged
user in an empty directory. The values the store is asked to hold come from the
workload in the scenario file, so the truth grading compares against is the
request stream itself and never anything a solver produced.
"""
import glob
import json
import os

import pytest

import scoring
from harness import StoreFailure, run_scenario

PROGRAM = "/app/nvm_store.py"
HIDDEN_DIR = "/tests/hidden"
LOG_DIR = "/logs/verifier"

EXPECTED_SCENARIOS = 10
TIMEOUT_PER_SCENARIO_S = 90.0


def load_scenarios():
    out = []
    for path in sorted(glob.glob(os.path.join(HIDDEN_DIR, "*.json"))):
        with open(path) as f:
            out.append(json.load(f))
    return out


@pytest.fixture(scope="module")
def outcome():
    cases = load_scenarios()
    per, failures, detail = [], {}, []
    os.makedirs(LOG_DIR, exist_ok=True)
    for case in cases:
        stderr_path = os.path.join(LOG_DIR, "stderr_%s.txt" % case["name"])
        try:
            log = run_scenario(PROGRAM, case, timeout_s=TIMEOUT_PER_SCENARIO_S,
                               stderr_path=stderr_path)
        except StoreFailure as exc:
            failures[case["name"]] = str(exc)
            continue
        per.append(scoring.scenario_metrics(log))
        detail.append({"name": log["name"], "cuts": log["cuts"],
                       "mount_ms": log["mount_ms"],
                       "violations": log["violations"][:40]})
    metrics = scoring.aggregate(per)
    try:
        with open(os.path.join(LOG_DIR, "metrics.json"), "w") as f:
            json.dump({"metrics": metrics, "per_scenario": per, "detail": detail,
                       "failures": failures, "bars": scoring.BARS,
                       "n_scenarios": len(cases)}, f, indent=2)
    except OSError:
        pass
    return metrics, failures, len(cases)


def test_every_scenario_ran(outcome):
    metrics, failures, found = outcome
    assert found == EXPECTED_SCENARIOS, (
        "expected %d graded scenarios under %s, found %d"
        % (EXPECTED_SCENARIOS, HIDDEN_DIR, found))
    assert not failures, (
        "the store did not get through every scenario: %s"
        % json.dumps(failures)[:2000])
    assert metrics["n_scenarios"] == EXPECTED_SCENARIOS


def test_no_block_is_lost_or_corrupted(outcome):
    metrics = outcome[0]
    assert metrics["integrity_violations"] <= scoring.BARS["integrity_violations"], (
        "%d reads did not return a value the contract allows (%s); at most %d allowed"
        % (metrics["integrity_violations"], json.dumps(metrics.get("by_kind", {})),
           scoring.BARS["integrity_violations"]))


def test_mount_stays_inside_its_budget(outcome):
    metrics = outcome[0]
    assert metrics["max_mount_ms"] <= scoring.BARS["max_mount_ms"], (
        "the slowest mount spent %.3f ms of device time, at most %.1f ms allowed"
        % (metrics["max_mount_ms"], scoring.BARS["max_mount_ms"]))


def test_tick_budget_is_respected(outcome):
    metrics = outcome[0]
    assert metrics["tick_overruns"] <= scoring.BARS["tick_overruns"], (
        "%d ticks spent more than the allowed device time, worst %.3f ms; at most %d allowed"
        % (metrics["tick_overruns"], metrics["worst_tick_ms"],
           scoring.BARS["tick_overruns"]))


def test_writes_are_acknowledged_in_time(outcome):
    metrics = outcome[0]
    assert metrics["unacked_at_end"] <= scoring.BARS["unacked_at_end"], (
        "%d writes were never acknowledged" % metrics["unacked_at_end"])
    assert metrics["max_ack_latency_ticks"] <= scoring.BARS["max_ack_latency_ticks"], (
        "the slowest write took %d ticks to be acknowledged, at most %d allowed"
        % (metrics["max_ack_latency_ticks"], scoring.BARS["max_ack_latency_ticks"]))


def test_endurance(outcome):
    metrics = outcome[0]
    assert metrics["erases_per_100_writes"] <= scoring.BARS["erases_per_100_writes"], (
        "%.3f sector erases per 100 committed writes, at most %.1f allowed"
        % (metrics["erases_per_100_writes"], scoring.BARS["erases_per_100_writes"]))
