# What was run before submitting

The Docker daemon was not reachable on the machine this bundle was built on, so `harbor run` and
`harbor check` could not be used. Everything below was run directly instead, and the commands that
still need Docker are listed at the end.

## From the submitted zip, in the container layout

The zip was extracted to a scratch directory and the two containers were emulated by hand:
`environment/data` and `environment/tools` copied to `/app`, the extracted `tests/` copied to
`/tests` and made unreadable by the `runner` user with `chmod -R go-rwx`, `/logs/verifier` created
empty, then

    bash solution/solve.sh        # puts the reference at /app/nvm_store.py
    bash /tests/test.sh

wrote `1` to `/logs/verifier/reward.txt` with `6 passed in 21.34s`, and produced
`/logs/verifier/ctrf.json`, `/logs/verifier/metrics.json` and one empty stderr file per scenario.
Removing `/app/nvm_store.py` and running `/tests/test.sh` again wrote `0`, with
`test_every_scenario_ran` the failing test and the other five still passing, which is what that
script is meant to do: it reports the verdict rather than crashing. The pinned `pytest==8.4.1` with
`pytest-json-ctrf==0.3.5` has to be first on `PATH` for the `--ctrf` option to exist; the verifier
image installs only that pinned pair.

`python3 /app/tools/devcheck.py /app/nvm_store.py`, the command the instruction gives the agent,
runs the three development scenarios and prints the same measurements, and reports `bars: all met`.

## Determinism

The verifier was run three times over the reference output. All three gave `6 passed` and identical
numbers: 0 violations, 2.540 ms worst mount, 0 tick overruns, 4 ticks worst acknowledgement, 0
writes left unacknowledged, 2.686 erases per 100 writes, 59 boots. Regenerating the scenarios with
`python authoring/provenance/generate_scenarios.py .` reproduces all 13 data files byte for byte,
compared by hash.

## Failure and hostile cases

Run through `tests/harness.py` over the ten graded scenarios, each scoring 0. The full table is in
`results.md` and `authoring/evidence/cheat_attempts.md` says what the verifier did with each hostile
program:

- no `/app/nvm_store.py` at all, and a program that prints lines that are not the protocol, both
  fail the completion test before any bar is measured
- a program that mounts and then stops answering, having double forked a child into its own session,
  is cut off at the wall clock limit and has its process group killed, leaving no process behind
- a program that writes the reward file and globs the sealed tests is refused on every path
- the three probes that keep the blocks somewhere other than the part fail at 11338 violations each,
  and a store that never leaves memory at 9207
- the quick attempt fails integrity at 9180 and endurance at 54.172 erases per 100 writes
- the shipped skeleton fails integrity at 7808 with 4043 writes never acknowledged

`python authoring/evidence/isolation_off.py` reruns the same set with the working directory reused
across every boot, `_purge_foreign_state` reduced to nothing and only the program itself killed, so
that every journal and every daemon survives untouched. The three probes and the memory store still
fail on the same counts and both correct stores still score 0; the output is
`authoring/evidence/isolation_off.json`. That is the number that shows the bars rest on the
durability check rather than on the sweep.

## The bars against the spread of correct implementations

`python authoring/evidence/evaluate.py` rescores everything this bundle ships and writes
`results.json` and `results.md`. Over the ten graded scenarios:

| | integrity | mount ms | overruns | ack ticks | unacked | erases/100 |
|---|---|---|---|---|---|---|
| bars | 0 | 8.0 | 0 | 35 | 0 | 5.0 |
| `solution/nvm_store.py` | 0 | 2.540 | 0 | 4 | 0 | 2.686 |
| `independent_store.py` | 0 | 3.600 | 0 | 5 | 0 | 3.594 |
| worst passing perturbation | 0 | 2.540 | 0 | 35 | 0 | 3.991 |
| nearest failing variant | 1 | 25.400 | 1963 | 461 unacked | | 6.267 |

The two correct stores are written to different designs. The reference keeps a summary in the last
pages of each sector and reads one per closed sector at mount; the independent store keeps no
summary inside a log sector at all and instead rotates a single map sector through the blank pool,
writing a whole index checkpoint into it each time a log sector is opened, so its mount reads the
newest checkpoint and the one sector of log that checkpoint does not describe. It gives up a sector
of the part and writes the map again on every sector change, and gets back the pages the reference
spends on summaries; the two land 0.9 erases per 100 writes apart, and every bar sits between the
weaker of them and the nearest variant that fails.

## What each bar is the sole reason for

- integrity: believing a page on its tag alone (1 violation and a crash), applying the sectors at
  mount in sector order rather than generation order (934), acknowledging on arrival (4)
- mount: dropping the per sector summaries (26.400 ms), and in the independent store dropping the
  checkpoint (25.400 ms)
- tick budget: doing every job in the tick it arrives in (1963 overruns)
- acknowledgement: keeping one blank sector rather than three (461 writes stranded), giving a sector
  up after a single erase (461), reclaiming the fullest sector rather than the emptiest (4043)
- endurance: closing the open sector twenty pages early (13.475 erases per 100 writes), holding six
  sectors blank rather than three (6.267)

The same ablation test was applied to the independently written store and not only to the reference,
because a reviewer of an earlier task of mine switched a piece off inside a shipped solver and
watched it pass. All five of its pieces bite: 3 violations and a crash without the record checksum,
25.400 ms of mount without the checkpoint, 162 violations with 461 writes stranded without the erase
proof, 1 violation acknowledging on arrival, and 1 violation with 1106 writes stranded with one
blank sector instead of three.

## How many sectors have to be kept blank, and why it is three

Once nothing on the part is free, opening a sector spends a blank one and reclaiming a sector makes
one, so the two cancel and the count only moves when a reclaim comes back empty handed: the sector
it erased read back written twice and was given up, and by then its live records were already copied
into the open sector, which no longer had room to reclaim a second one. Each sector given up costs
the part one blank sector for good, and these parts wear out up to two.

| sectors kept blank | result |
|---|---|
| one | 461 writes stranded, every other bar met |
| two | passes as the graded set stands, at 2.384 erases per 100 writes |
| two, closing the open sector six pages early | 461 writes stranded |
| three, closing the open sector six pages early | passes, at 3.127 |
| three, ten pages early | passes, at 3.991 |
| three (shipped) | passes, at 2.686 |
| four | passes, at 3.049 |
| five | passes, at 3.872 |
| six | 6.267, endurance alone |

Two is enough for these ten scenarios and nothing more. Three is what makes the tuning around it
stop mattering, which is the property worth having in a reference.

## Three switches reported as guards rather than claimed as ablations

Removing any of these leaves every number on the graded set unchanged, and saying so is better than
claiming a crux that does not measure:

- the reclaim reserve, which stops writes short of the end of the open sector by what the next
  reclaim will need while nothing is blank. It prevents a state the other invariants already keep
  the store out of on this set: the copies drain within a tick or two of being owed, so the reserve
  is never the thing that saves the run.
- the gap between erases, which stops two erases starting back to back so a read is not refused
  through both windows. With the reference at 2.686 erases per 100 writes the erases are far enough
  apart that the gap never binds.
- the read back of a reclaim copy before the sector it came from is erased. It guards against a copy
  landing on a page that has stopped taking programs, which none of the worn sectors in the graded
  set happen to be the destination of.

One design choice is also reported rather than claimed: reclaiming the oldest sector instead of the
one with the fewest live records passes, at 2.917 erases per 100 writes against the reference's
2.686. That is a property of this workload rather than a gap in the bar. Fresh writes and reclaimed
records go into the same log, so every sector ages alike and the oldest sector is also the most
decayed; a rotation and a choice land in the same place. Separating the two into their own open
sectors was built and measured, and on a part this full it was worse on every count, so the simpler
design is what ships. What the erase bar does separate is how much of a sector is thrown away per
erase: closing the open sector twenty pages early reaches 13.475, and holding six sectors blank
reaches 6.267.

## Still needs Docker

- `harbor run` and `harbor check` against the built images
- confirming `pip install` of the pinned versions inside `python:3.11-slim` for both images
- confirming that the `runner` account created in both Dockerfiles is the one the harness finds
