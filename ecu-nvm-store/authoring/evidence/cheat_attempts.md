# Attempts to pass without doing the work

Every program named here lives in `cheats/` and was run through `tests/harness.py` against the
graded scenarios, with `/logs/verifier` made root owned and mode 700 and `/tests` made unreadable by
the `runner` user, exactly as the verifier image and `tests/test.sh` leave them. None of them is ever
executed by the verifier.

| attempt | what it does | outcome |
|---|---|---|
| no program | `/app/nvm_store.py` absent | every scenario fails to start, `test_every_scenario_ran` fails, reward 0 |
| `cheats/garbage.py` | prints lines that are not the protocol | rejected at mount with `unexpected line during mount`, reward 0 |
| `cheats/sleeper.py` | mounts, then stops answering, and double forks a child into its own session | each scenario ends at the wall clock limit after 20.0 s, the process group is killed, reward 0 |
| `cheats/reward_writer.py` | writes `/logs/verifier/reward.txt` and `/logs/verifier/ctrf.json`, globs `/tests/hidden` and `/tests/*.py`, then answers every read NONE | every write refused with permission denied, every glob returns zero files, `reward.txt` unchanged at `0`, and it then fails integrity at 2854 violations with 1113 writes never acknowledged |
| `cheats/ram_only.py` | acknowledges on arrival, answers from memory, never touches the part | 636 integrity violations over the graded set, all of them stale reads after a reset, reward 0 |
| `shortcut_store.py` | the quick attempt: memory mirror, ack on arrival, sector dump on fill | 1096 integrity violations, reward 0 |
| `environment/tools/skeleton_store.py` | the shipped skeleton, every read NONE, no acknowledgements | 2854 integrity violations and 1113 writes unacknowledged, reward 0 |

## Why the reward channel holds

`tests/test.sh` chowns `/logs/verifier` to root and sets mode 700 before pytest starts, so the
unprivileged user the store runs as cannot create or replace `reward.txt` or `ctrf.json` even while
the verifier is still running. `tests/Dockerfile` bakes `/tests` with `chmod -R go-rwx`, so the
graded scenarios and the grading code are unreadable from the same user. `harness.py` starts the
program with `start_new_session=True` and kills the whole process group in a finally block, and the
`sleeper.py` attempt exists to show that a double forked child does not keep the run alive or get a
second chance at the reward.

## Why memory alone cannot pass

The interesting negative result is `ram_only.py`. It is correct in every respect that can be
observed without losing the supply: it acknowledges instantly, answers every read with the value the
workload last asked for, issues no device operations at all and therefore never overruns a tick,
never erases anything and mounts in no time. It fails on integrity alone, and only because of the
resets. That is the evidence that the integrity bar is carried by the power cuts rather than by the
workload.

It also found a hole in an earlier version of the harness. Resets used to be triggered by counting
device operations after a request ordinal, so a program that issued no operations was never reset at
all and `ram_only.py` passed every bar. Each reset now carries a deadline in ticks and happens
anyway if the operation it was aimed at never comes, which is what the `IDLE` entries in the reset
log are. After that change the same program loses 636 blocks, and no process of it survives the run.

## One deliberately weakened reference that crashes rather than lies

`no_record_checksum`, the ablation that believes a page on its tag byte alone, is worth a note
because its failure is not only a wrong value. On one of the ten scenarios it reads a length out of a
half programmed page, asks for something the device rejects, and the process exits mid tick, so it
fails both the completion test and the integrity bar. A checksum over the whole record is what turns
a torn page into a page that is skipped.
