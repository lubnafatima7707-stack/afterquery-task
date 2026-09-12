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
    "unit_d": {"sectors": 16, "pages_per_sector": 128, "page_bytes": 128,
               "t_read_ms": 0.02, "t_program_ms": 0.35, "erase_ticks": 3},
}

LIMITS = {"tick_budget_ms": 2.0, "mount_budget_ms": 8.0,
          "read_deadline_ticks": 8, "drain_ticks": 200}

N_BLOCKS = 24
LENGTHS = [8, 12, 16, 20, 24, 28, 32]


def build_requests(rng, n_writes, read_share, burst_chance):
    lengths = [rng.choice(LENGTHS) for _ in range(N_BLOCKS)]
    requests = []
    at = 1
    rid = 1
    order = 0
    hot = rng.sample(range(N_BLOCKS), 3)
    recent = []
    counter = 1
    for block in range(N_BLOCKS):
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
            block = rng.choice(recent[-8:]) if rng.random() < 0.7 else rng.randrange(N_BLOCKS)
            requests.append({"at": at, "kind": "R", "rid": rid, "block": block})
            rid += 1
            continue
        block = rng.choice(hot) if rng.random() < 0.4 else rng.randrange(N_BLOCKS)
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
    lengths, requests = build_requests(rng, n_writes, read_share, burst_chance)
    dev = dict(device)
    if weak:
        dev["weak_pages"] = weak
        dev["weak_from"] = 1
    return {"name": name, "seed": seed, "device": dev, "limits": dict(LIMITS),
            "blocks": lengths, "requests": requests,
            "cuts": build_cuts(rng, len(requests), n_cuts)}


def dev_scenarios():
    return [
        make("dev_plain", 11001, DEV_DEVICE, 260, 2),
        make("dev_resets", 11002, DEV_DEVICE, 520, 5, burst_chance=0.09),
        make("dev_worn", 11003, DEV_DEVICE, 1400, 5,
             weak={"5": [0, 1, 2, 37, 38]}),
    ]


def hidden_scenarios():
    return [
        make("h01_a_quiet", 22001, UNITS["unit_a"], 520, 3),
        make("h02_a_bursts", 22002, UNITS["unit_a"], 760, 5, burst_chance=0.12),
        make("h03_a_worn", 22003, UNITS["unit_a"], 1600, 6,
             weak={"9": [0, 1, 2, 3, 41]}),
        make("h04_b_quiet", 22004, UNITS["unit_b"], 600, 2),
        make("h05_b_resets", 22005, UNITS["unit_b"], 980, 6, burst_chance=0.1),
        make("h06_c_wide", 22006, UNITS["unit_c"], 620, 4, read_share=0.3),
        make("h07_c_worn", 22007, UNITS["unit_c"], 1700, 6,
             weak={"3": [0, 1, 17], "14": [2, 3, 4, 5, 33, 34]}),
        make("h08_d_deep", 22008, UNITS["unit_d"], 900, 4, burst_chance=0.08),
        make("h09_d_reads", 22009, UNITS["unit_d"], 640, 6, read_share=0.34),
        make("h10_a_long", 22010, UNITS["unit_a"], 1500, 7, burst_chance=0.07,
             weak={"6": [1, 2, 19, 20, 55]}),
    ]


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
              "limits": LIMITS, "n_blocks": N_BLOCKS, "block_lengths": LENGTHS}
    for sc in dev_scenarios():
        write_json(os.path.join(dev_dir, sc["name"] + ".json"), sc)
        record["dev"].append({"name": sc["name"], "seed": sc["seed"],
                              "requests": len(sc["requests"]),
                              "cuts": len(sc["cuts"])})
    for sc in hidden_scenarios():
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
