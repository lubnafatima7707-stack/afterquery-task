"""
Builds the development and graded scenarios.

Every scenario is a workload of block writes and reads plus a list of resets,
and nothing in it depends on any solver: the values are drawn from the seed, the
reset points are fixed at a request ordinal and an operation count so that two
different designs are cut at the same point in the workload, and the device
geometry comes from the variant table. The ground truth the verifier grades
against is the sequence of values the workload itself wrote.

    python generate_scenarios.py <bundle_root>
"""
import json
import os
import random
import sys

DEV_DEVICE = {"sectors": 16, "pages_per_sector": 64, "page_bytes": 128,
              "t_read_ms": 0.02, "t_program_ms": 0.35, "erase_ticks": 3}

UNITS = {
    "unit_a": {"sectors": 16, "pages_per_sector": 64, "page_bytes": 64,
               "t_read_ms": 0.02, "t_program_ms": 0.35, "erase_ticks": 3},
    "unit_b": {"sectors": 12, "pages_per_sector": 96, "page_bytes": 128,
               "t_read_ms": 0.02, "t_program_ms": 0.4, "erase_ticks": 3},
    "unit_c": {"sectors": 20, "pages_per_sector": 64, "page_bytes": 256,
               "t_read_ms": 0.025, "t_program_ms": 0.35, "erase_ticks": 4},
    "unit_d": {"sectors": 16, "pages_per_sector": 80, "page_bytes": 128,
               "t_read_ms": 0.02, "t_program_ms": 0.35, "erase_ticks": 3},
}

# The live set is sized to fill this much of the room a part really has: the
# pages of it that can hold a record, less the sectors a log has to keep blank to
# erase into. That works out at about half of every page on the part, and it is
# what puts the erase budget in play: the fuller the part, the more of a sector a
# reclaim has to copy out before it can free it.
TARGET_FILL = 0.70
# Four sectors are held out of that sum. Two are the blank pool a log structured
# part cannot run without: one to roll onto when the open sector fills and one
# left over for the case where the sector it just reclaimed turns out to be worn.
# The other two are the allowance for sectors that are given up over a run, so a
# part that loses one is still inside the band the bars were calibrated for.
SPARE_SECTORS = 4
# Reading every block back after every reset would dominate a run, so a sample
# fixed by the generator is checked at each reset and the whole set at the end.
VERIFY_SAMPLE = 96


def summary_pages(device):
    """Pages at the end of a sector a per sector summary needs, as the store sizes it."""
    per_page = max(1, (device["page_bytes"] - 12) // 3)
    pages = 1
    while pages * per_page < device["pages_per_sector"] - 1 - pages:
        pages += 1
    return pages


def record_pages(device):
    """Pages of a sector a record can go in: not the header, not the summary."""
    return device["pages_per_sector"] - 1 - summary_pages(device)


def usable_pages(device, held_back=SPARE_SECTORS):
    return (device["sectors"] - held_back) * record_pages(device)


def block_count(device):
    return int(TARGET_FILL * usable_pages(device))

LIMITS = {"tick_budget_ms": 2.0, "mount_budget_ms": 8.0,
          "read_deadline_ticks": 8, "drain_ticks": 200}

LENGTHS = [8, 12, 16, 20, 24, 28, 32]
# a fifth of the blocks take four writes in five, so a sector left alone goes
# mostly dead while a sector full of hot blocks stays mostly live
HOT_SHARE = 0.20
HOT_WRITES = 0.80


def build_requests(rng, n_writes, read_share, burst_chance, n_blocks):
    lengths = [rng.choice(LENGTHS) for _ in range(n_blocks)]
    requests = []
    at = 1
    rid = 1
    order = 0
    hot = rng.sample(range(n_blocks), max(1, int(HOT_SHARE * n_blocks)))
    recent = []
    counter = 1
    for block in range(n_blocks):
        value = counter.to_bytes(4, "big") + bytes(rng.randrange(256)
                                                   for _ in range(lengths[block] - 4))
        counter += 1
        requests.append({"at": at, "kind": "W", "req": rid, "block": block,
                         "hex": value.hex(), "order": order})
        rid += 1
        order += 1
        at += rng.choice([1, 2, 2, 3])
    burst = 0
    while order < n_writes:
        if burst == 0 and rng.random() < burst_chance:
            burst = rng.randrange(6, 13)
        gap = 1 if burst else rng.choice([2, 2, 3, 3, 4, 5, 7])
        if burst:
            burst -= 1
        at += gap
        if recent and rng.random() < read_share:
            block = (rng.choice(recent[-8:]) if rng.random() < 0.7
                     else rng.randrange(n_blocks))
            requests.append({"at": at, "kind": "R", "rid": rid, "block": block})
            rid += 1
            continue
        block = (rng.choice(hot) if rng.random() < HOT_WRITES
                 else rng.randrange(n_blocks))
        value = counter.to_bytes(4, "big") + bytes(rng.randrange(256)
                                                  for _ in range(lengths[block] - 4))
        counter += 1
        requests.append({"at": at, "kind": "W", "req": rid, "block": block,
                         "hex": value.hex(), "order": order})
        recent.append(block)
        rid += 1
        order += 1
    return lengths, requests


MODES = ["ANY", "ANY", "ERASE", "POST_ERASE", "POST_ERASE"]


def build_cuts(rng, n_requests, n_cuts, first_at=0.08):
    cuts = []
    if n_cuts <= 0:
        return cuts
    span = 1.0 - first_at - 0.04
    for i in range(n_cuts):
        frac = first_at + span * (i + rng.random() * 0.6) / max(1, n_cuts)
        mode = MODES[rng.randrange(len(MODES))]
        cut = {"after_request": int(frac * n_requests),
               "on": mode,
               "partial": round(rng.uniform(0.02, 0.96), 3),
               "deadline": 6 if mode == "ANY" else 900}
        if mode == "POST_ERASE":
            cut["op_index"] = rng.randrange(0, 7)
        elif mode == "ANY":
            cut["op_index"] = rng.randrange(0, 6)
        cuts.append(cut)
    cuts.sort(key=lambda c: c["after_request"])
    return cuts


def make(name, seed, device, n_writes, n_cuts, read_share=0.22,
         burst_chance=0.05, weak=None):
    rng = random.Random(seed)
    n_blocks = block_count(device)
    lengths, requests = build_requests(rng, n_writes, read_share, burst_chance, n_blocks)
    dev = dict(device)
    if weak:
        dev["weak_pages"] = weak
        dev["weak_from"] = 1
    first_at = max(0.08, 1.25 * n_blocks / len(requests))
    cuts = build_cuts(rng, len(requests), n_cuts, first_at)
    sample = min(VERIFY_SAMPLE, n_blocks)
    for cut in cuts:
        cut["verify"] = sorted(rng.sample(range(n_blocks), sample))
    return {"name": name, "seed": seed, "device": dev, "limits": dict(LIMITS),
            "blocks": lengths, "requests": requests, "cuts": cuts,
            "first_verify": sorted(rng.sample(range(n_blocks), sample))}


def dev_scenarios():
    return [
        make("dev_plain", 11001, DEV_DEVICE, 2200, 2),
        make("dev_resets", 11002, DEV_DEVICE, 3200, 5, burst_chance=0.09),
        make("dev_worn", 11003, DEV_DEVICE, 4200, 5,
             weak={"5": [0, 1, 2, 37, 38]}),
    ]


def hidden_scenarios():
    return [
        make("h01_a_quiet", 22001, UNITS["unit_a"], 2600, 3),
        make("h02_a_bursts", 22002, UNITS["unit_a"], 3400, 5, burst_chance=0.12),
        make("h03_a_worn", 22003, UNITS["unit_a"], 4600, 6,
             weak={"9": [0, 1, 2, 3, 41]}),
        make("h04_b_quiet", 22004, UNITS["unit_b"], 2800, 2),
        make("h05_b_resets", 22005, UNITS["unit_b"], 4200, 6, burst_chance=0.1),
        make("h06_c_wide", 22006, UNITS["unit_c"], 3000, 4, read_share=0.3),
        make("h07_c_worn", 22007, UNITS["unit_c"], 4800, 6,
             weak={"3": [0, 1, 17], "14": [2, 3, 4, 5, 33, 34]}),
        make("h08_d_deep", 22008, UNITS["unit_d"], 3600, 4, burst_chance=0.08),
        make("h09_d_reads", 22009, UNITS["unit_d"], 3000, 6, read_share=0.34),
        make("h10_a_long", 22010, UNITS["unit_a"], 5200, 7, burst_chance=0.07,
             weak={"6": [1, 2, 19, 20, 55]}),
    ]


def check_feasible(sc):
    """Refuse to write a scenario the bars could not be met on.

    Each of these is a way the scenario could be unwinnable or degenerate rather
    than hard, so it raises instead of warning.
    """
    dev = sc["device"]
    sectors = dev["sectors"]
    pages = dev["pages_per_sector"]
    page_bytes = dev["page_bytes"]
    t_read = dev["t_read_ms"]
    t_prog = dev["t_program_ms"]
    limits = sc["limits"]
    budget = limits["tick_budget_ms"]
    mount_bar = limits["mount_budget_ms"]
    blocks = sc["blocks"]
    weak = {int(k) for k in (dev.get("weak_pages") or {})}
    name = sc["name"]
    writes = sum(1 for r in sc["requests"] if r["kind"] == "W")

    def need(ok, why):
        if not ok:
            raise SystemExit("%s is not winnable as generated: %s" % (name, why))

    need(max(blocks) + 12 <= page_bytes,
         "a %d byte block does not fit a %d byte page" % (max(blocks), page_bytes))

    # what the part is worth to the store once the header, the summary and the
    # two sectors it has to keep blank are taken off it, with any worn sector
    # counted as already gone
    usable = usable_pages(dev, len(weak) + 2)
    fill = len(blocks) / float(usable)
    need(0.55 <= fill <= 0.80,
         "the live set fills %.2f of the part, which is outside the band the bars "
         "were calibrated for" % fill)

    # a sector picked well is mostly dead, so copying out of it has to be
    # affordable: with the part this full, each new record costs about
    # fill / (1 - fill) copies, and that plus the write itself has to fit the tick
    copies = fill / (1.0 - fill)
    ops_per_tick = (writes / float(max(1, writes * 3))) * (1.0 + copies)
    need(ops_per_tick * t_prog <= 0.5 * budget,
         "keeping up would need %.2f ms of the %.1f ms tick" % (ops_per_tick * t_prog, budget))

    # the mount has to be reachable with a checkpoint and a bounded tail, and out
    # of reach of reading the whole part, or it measures nothing
    directory = len(blocks) * 2.0 / page_bytes          # pages of block to page map
    reachable = (sectors + directory + 96) * t_read
    whole_part = sectors * pages * t_read
    need(reachable <= 0.7 * mount_bar,
         "a checkpoint and a short tail already cost %.2f ms of the %.1f ms mount"
         % (reachable, mount_bar))
    need(whole_part > 2.0 * mount_bar,
         "reading the whole part costs only %.2f ms, so the mount bar measures nothing"
         % whole_part)

    need(budget / t_prog >= 4.0,
         "a tick only carries %.1f page programs" % (budget / t_prog))

    first_cut = min((c["after_request"] for c in sc["cuts"]), default=10 ** 9)
    need(first_cut > len(blocks),
         "the first reset lands at request %d, before every one of the %d blocks has "
         "been written" % (first_cut, len(blocks)))

    turns = writes / float(usable)
    need(turns >= 2.0,
         "%d writes only turn the part over %.1f times, so reclaim hardly runs" % (writes, turns))
    if weak:
        need(turns >= 3.0,
             "%.1f turnovers do not bring the rotation back to a worn sector" % turns)
    return {"name": name, "blocks": len(blocks), "writes": writes,
            "fill": round(fill, 3), "turnovers": round(turns, 1),
            "copies_per_write": round(copies, 2),
            "reachable_mount_ms": round(reachable, 3),
            "whole_part_mount_ms": round(whole_part, 3),
            "good_sectors": sectors - len(weak)}


def write_json(path, obj):
    with open(path, "w", newline="\n") as f:
        json.dump(obj, f, sort_keys=True, separators=(",", ":"))
        f.write("\n")


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    dev_dir = os.path.join(root, "environment", "data", "dev")
    hid_dir = os.path.join(root, "tests", "hidden")
    os.makedirs(dev_dir, exist_ok=True)
    os.makedirs(hid_dir, exist_ok=True)
    record = {"dev": [], "hidden": [], "units": UNITS, "dev_device": DEV_DEVICE,
              "limits": LIMITS, "target_fill": TARGET_FILL,
              "spare_sectors": SPARE_SECTORS,
              "verify_sample": VERIFY_SAMPLE, "block_lengths": LENGTHS}
    record["feasibility"] = []
    for sc in dev_scenarios():
        record["feasibility"].append(check_feasible(sc))
        write_json(os.path.join(dev_dir, sc["name"] + ".json"), sc)
        record["dev"].append({"name": sc["name"], "seed": sc["seed"],
                              "requests": len(sc["requests"]),
                              "cuts": len(sc["cuts"])})
    for sc in hidden_scenarios():
        record["feasibility"].append(check_feasible(sc))
        write_json(os.path.join(hid_dir, sc["name"] + ".json"), sc)
        record["hidden"].append({"name": sc["name"], "seed": sc["seed"],
                                 "requests": len(sc["requests"]),
                                 "cuts": len(sc["cuts"]),
                                 "device": sc["device"]})
    write_json(os.path.join(root, "authoring", "provenance", "provenance_record.json"),
               record)
    print("wrote %d development and %d graded scenarios"
          % (len(record["dev"]), len(record["hidden"])))


if __name__ == "__main__":
    main()
