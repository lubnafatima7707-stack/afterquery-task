"""
Metric code shared by the verifier and by the authoring evidence scripts, so
every number quoted about this task comes out of the same functions.
"""

INTEGRITY_KINDS = ("corrupt", "rollback", "stale", "unanswered_read")

BARS = {
    "integrity_violations": 0,
    "max_mount_ms": 8.0,
    "tick_overruns": 0,
    "max_ack_latency_ticks": 35,
    "unacked_at_end": 0,
    "erases_per_100_writes": 6.0,
}


def scenario_metrics(log):
    kinds = {k: 0 for k in INTEGRITY_KINDS}
    for v in log["violations"]:
        kinds[v["kind"]] = kinds.get(v["kind"], 0) + 1
    acked = int(log["acked_writes"])
    erases = int(log["erases"])
    return {
        "name": log["name"],
        "integrity_violations": sum(kinds.get(k, 0) for k in INTEGRITY_KINDS),
        "by_kind": kinds,
        "max_mount_ms": max(log["mount_ms"]) if log["mount_ms"] else 0.0,
        "tick_overruns": int(log["tick_overruns"]),
        "worst_tick_ms": float(log["worst_tick_ms"]),
        "max_ack_latency_ticks": max(log["ack_latencies"]) if log["ack_latencies"] else 0,
        "max_read_latency_ticks": max(log["read_latencies"]) if log["read_latencies"] else 0,
        "unacked_at_end": int(log["unacked_at_end"]),
        "acked_writes": acked,
        "lost_writes": int(log["lost_writes"]),
        "erases": erases,
        "max_sector_erases": max(log["erase_counts"]) if log["erase_counts"] else 0,
        "erases_per_100_writes": round(100.0 * erases / acked, 3) if acked else 0.0,
        "boots": int(log["boots"]),
        "ticks": int(log["ticks"]),
        "wall_s": log.get("wall_s", 0.0),
    }


def aggregate(per_scenario):
    if not per_scenario:
        return {"n_scenarios": 0, "integrity_violations": 0, "max_mount_ms": 0.0,
                "tick_overruns": 0, "max_ack_latency_ticks": 0,
                "max_read_latency_ticks": 0, "unacked_at_end": 0,
                "erases_per_100_writes": 0.0, "acked_writes": 0, "erases": 0,
                "max_sector_erases": 0, "worst_tick_ms": 0.0}
    acked = sum(m["acked_writes"] for m in per_scenario)
    erases = sum(m["erases"] for m in per_scenario)
    kinds = {}
    for m in per_scenario:
        for k, v in m["by_kind"].items():
            kinds[k] = kinds.get(k, 0) + v
    return {
        "n_scenarios": len(per_scenario),
        "integrity_violations": sum(m["integrity_violations"] for m in per_scenario),
        "by_kind": kinds,
        "max_mount_ms": round(max(m["max_mount_ms"] for m in per_scenario), 4),
        "tick_overruns": sum(m["tick_overruns"] for m in per_scenario),
        "worst_tick_ms": round(max(m["worst_tick_ms"] for m in per_scenario), 4),
        "max_ack_latency_ticks": max(m["max_ack_latency_ticks"] for m in per_scenario),
        "max_read_latency_ticks": max(m["max_read_latency_ticks"] for m in per_scenario),
        "unacked_at_end": sum(m["unacked_at_end"] for m in per_scenario),
        "acked_writes": acked,
        "lost_writes": sum(m["lost_writes"] for m in per_scenario),
        "erases": erases,
        "max_sector_erases": max(m["max_sector_erases"] for m in per_scenario),
        "erases_per_100_writes": round(100.0 * erases / acked, 3) if acked else 0.0,
        "boots": sum(m["boots"] for m in per_scenario),
        "ticks": sum(m["ticks"] for m in per_scenario),
    }


def failed_bars(metrics):
    bad = []
    if metrics["integrity_violations"] > BARS["integrity_violations"]:
        bad.append("integrity_violations")
    if metrics["max_mount_ms"] > BARS["max_mount_ms"]:
        bad.append("max_mount_ms")
    if metrics["tick_overruns"] > BARS["tick_overruns"]:
        bad.append("tick_overruns")
    if (metrics["max_ack_latency_ticks"] > BARS["max_ack_latency_ticks"]
            or metrics["unacked_at_end"] > BARS["unacked_at_end"]):
        bad.append("ack_latency")
    if metrics["erases_per_100_writes"] > BARS["erases_per_100_writes"]:
        bad.append("erases_per_100_writes")
    return bad
