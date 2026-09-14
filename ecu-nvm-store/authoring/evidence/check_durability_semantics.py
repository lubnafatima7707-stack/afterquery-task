"""
Asserts the property the whole verdict now rests on.

    python authoring/evidence/check_durability_semantics.py

A value handed back after a reset is compared against the flash image as it stood
at the instant the supply went, not as it stands when the read is answered. That
is what stops a store which keeps the blocks somewhere else and then programs them
into blank pages while the read back is happening: by then the power is already
gone, and nothing written afterwards can be durable.

This checks the mechanism directly rather than through a solver, so it stays true
whatever a probe does.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import device  # noqa: E402
import harness  # noqa: E402

SPEC = {"sectors": 4, "pages_per_sector": 8, "page_bytes": 64,
        "t_read_ms": 0.02, "t_program_ms": 0.35, "erase_ticks": 3}
SCENARIO = {"name": "semantics", "device": SPEC, "blocks": [8, 8],
            "limits": {"tick_budget_ms": 2.0, "mount_budget_ms": 8.0,
                       "read_deadline_ticks": 8, "drain_ticks": 50},
            "requests": [], "cuts": []}


def main():
    runner = harness.Runner("/nonexistent", SCENARIO)
    before = b"\xaa" * 8
    after = b"\xbb" * 8

    # something the store put on the part before the supply went
    runner.dev.program(0, 0, 0, before + bytes([0xFF]) * (SPEC["page_bytes"] - 8))
    runner._seal_durable()

    # and something programmed afterwards, while the read back is going on
    runner.dev.program(0, 1, 0, after + bytes([0xFF]) * (SPEC["page_bytes"] - 8))

    live = runner._take_image()
    problems = []
    if before not in runner._durable:
        problems.append("a value written before the cut is missing from the frozen image")
    if after in runner._durable:
        problems.append("a value written after the cut appears in the frozen image, so a "
                        "store could materialise its blocks during the read back")
    if after not in live:
        problems.append("the live image does not contain the later write, so this test is "
                        "not measuring what it claims")
    if runner._durable == live:
        problems.append("the frozen image and the live image are the same object, so "
                        "freezing is doing nothing")

    for line in problems:
        print("FAIL  " + line)
    if not problems:
        print("pass  a value on the part before the cut is found in the frozen image")
        print("pass  a value programmed after the cut is not, so it cannot answer for "
              "durability")
        print("pass  the live image does contain it, which is what the old check compared "
              "against")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
