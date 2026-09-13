# What was run before submitting

Docker was not available on the machine this bundle was built on, so `harbor run` and `harbor check`
could not be used. Everything below was run directly instead, and the commands that still need
Docker are listed at the end.

## From the submitted zip, in the container layout

The zip was extracted to a scratch directory and the two containers were emulated by hand:
`environment/data` and `environment/tools` copied to `/app`, the extracted `tests/` copied to
`/tests`, `/logs/verifier` created empty, then

    bash solution/solve.sh        # puts the reference at /app/nvm_store.py
    bash /tests/test.sh

wrote `1` to `/logs/verifier/reward.txt` with `6 passed in 7.62s`, and produced
`/logs/verifier/ctrf.json`, `/logs/verifier/metrics.json` and one empty stderr file per scenario.
Removing `/app/nvm_store.py` and running `/tests/test.sh` again wrote `0`, with
`test_every_scenario_ran` the failing test. The pinned `pytest==8.4.1` with
`pytest-json-ctrf==0.3.5` has to be first on `PATH` for the `--ctrf` option to exist; a second
pytest without the plugin on this machine produced `unrecognized arguments: --ctrf`, which is a
local packaging detail and not something the verifier image can hit, since that image installs only
the pinned pair.

## Determinism

The verifier was run three times over the reference output. All three gave `6 passed` and identical
numbers: 0 violations, 2.88 ms worst mount, 0 tick overruns, 11 ticks worst acknowledgement, 2.491
erases per 100 writes, 59 boots, 34848 ticks. Regenerating the scenarios with
`python authoring/provenance/generate_scenarios.py .` reproduces all 14 data files byte for byte,
compared by hash.

## Failure and hostile cases

Run through `tests/harness.py` over the ten graded scenarios, each scoring 0:

- no `/app/nvm_store.py` at all, and a program that prints lines that are not the protocol, both
  fail the completion test before any bar is measured
- a program that mounts and then stops answering, having double forked a child into its own session,
  is cut off at the wall clock limit and has its process group killed, leaving no process behind
- a program that writes `/logs/verifier/reward.txt` and globs `/tests` is refused on every path and
  sees zero files, with `reward.txt` unchanged
- the shipped skeleton, the quick attempt and a memory only store all fail on their own merits

Details and numbers are in `cheat_attempts.md`.

## Sizing

The suite takes 7.6 s on the reference, so `[verifier].timeout_sec` is set from the worst case
instead: ten scenarios at the 90 s per scenario wall limit is 900 s, hence 1200. The reference
spends about 0.75 s per scenario, and `[agent].timeout_sec` is 14400.

`numpy==2.0.2` is installed in both images although nothing in the bundle imports it, so that a
submitted store which reaches for it still runs under the verifier; the instruction says that numpy
and the standard library are what is there.

## Still to run where Docker is available

    harbor run -p . -a oracle -e docker
    harbor run -p . -a nop -e docker
    harbor check . -m anthropic/claude-opus-4-8

## Ablating the shipped solvers, not only the reference

A previous task of mine failed its review because a reviewer switched a piece off inside the
bundle's own independently written solver, watched it pass every bar, and concluded the advertised
hard part was not load bearing. So the same test was run here on the second correct store, with the
switches in its own `VARIANT` line, over the ten graded scenarios:

| piece removed from `independent_store.py` | integrity violations | bars failed |
|---|---|---|
| record checksum | 3, and it dies outright on one scenario | completion, integrity |
| index snapshot refreshed before a sector is reclaimed | 0 | none |
| reading the sector back after an erase | 2 | integrity |
| abandoning a head whose snapshot never landed | 118 | integrity |
| acknowledging only after the page is programmed | 6 | integrity |

Four of the five bite. The snapshot refresh does not, and that is reported rather than dressed up:
reclamation copies the live records into the head as ordinary records, and the mount applies every
record that follows the newest snapshot, so the index is repaired by the replay even when a stored
snapshot still names a page inside the sector that was then erased. The write is kept because it
bounds how much replay a mount has to do, but nothing in the difficulty explanation rests on it. The
equivalent piece in the reference, the seal that makes a compaction visible only once it is
complete, is load bearing at 429 violations.

## The one bar dodge worth testing

The mount bar could in principle be sidestepped by spending nothing between MOUNT and MOUNTED and
scanning the part from inside the ticks instead, answering reads BUSY until the scan is done, since
a read may be answered BUSY for up to eight ticks and eight ticks of budget is 16 ms, twice the
8.0 ms mount bar. That was built as `deferred_full_scan` and measured: it records 0.000 ms of mount
time and then fails anyway, with 1161 integrity violations from reads that never got a value and 2
tick overruns, because a whole part is 20.5 to 41.0 ms of reads and does not fit in eight ticks of a
2.0 ms budget either. The bar is not dodgeable by moving the work, only by not doing it.

## The adversarial probe, and the check that replaced the isolation argument

The anti cheat probe passed with reward 1 by journalling its blocks into `/run/lock`, a directory at
mode 1777 in the base image that the sweep's hardcoded list did not name, while issuing no device
operation at all. The repair is not a longer list. A value handed back after a reset now has to be
present in the flash image the harness holds, byte for byte and in one piece, and so does every
acknowledged value at the end of a run; the sweep stays as defence in depth and discovers what to
clear by walking the image rather than by naming directories.

The measurement that shows which half does the work runs every solver with `_purge_foreign_state`
cut down to rebuilding the working directory, so nothing is swept, no process is killed and no ipc
object is removed, over all ten graded scenarios:

| solver, isolation disabled | not_on_device | total violations | bars failed |
|---|---|---|---|
| `cheats/run_lock_journal.py` | 1104 | 1104 | integrity |
| `cheats/file_backed.py` | 1104 | 1320 | integrity |
| `cheats/ram_only.py` | 227 | 863 | integrity |
| `solution/nvm_store.py` | 0 | 0 | none |
| `authoring/evidence/independent_store.py` | 0 | 0 | none |

With the harness as shipped all three probes land on 863 violations, and the run report records the
132, 176 and 0 files and the 46, 0 and 0 processes taken away from them. The walk itself costs a
fraction of a second per verifier process and is cached; it found `/run/lock` on the first run
without being told about it.

The instruction was corrected at the same time. It used to promise that "every temporary directory
the user can write to is emptied", which the driver did not actually do, and the run audit was right
to record that as a verifier defect. It now says what is true: the sweep is best effort, and what
grading rests on is that a block has to be on the part.

## The account the agent image was missing

A quality review found that `environment/Dockerfile` never created the `runner` account, while the
copy of the driver shipped to the agent calls `pwd.getpwnam("runner")` whenever it is started by
root. The command the instruction gives, `python3 /app/tools/devcheck.py /app/nvm_store.py`, would
therefore have raised `KeyError` for a root agent in that image. My own validation hid it: this
machine had the account created by hand for the harness tests, so the path a fresh image takes was
never exercised.

Both halves are fixed. `environment/Dockerfile` now creates the same account with the same uid as
`tests/Dockerfile`, so a development run drops privileges exactly as the graded run does. And the
driver degrades instead of raising when the account is absent: it runs the store as the user it is
itself running as, records `isolated: false` in the run log, and `devcheck.py` prints a line saying
so, which keeps a development run from being mistaken for a graded one.

Both paths were then run. With the stdlib `pwd` module shadowed by a stub whose `getpwnam` always
raises, standing in for an image without the account, `devcheck.py` completes and the reference
reports all bars met; the journal probe run the same way still fails, at 69 rollbacks and 24
`not_on_device` violations, which is the point of grading on the image rather than on isolation. With
the account present the same commands give the same numbers as before.

`authoring/evidence/bundle_checks.py` now fails if either Dockerfile stops creating the account the
driver names, or if the driver stops degrading when it is missing.

## The sweep only removes what the run created

The driver ships to the agent as well as grading with it, so it runs inside a container that is not
the verifier's, next to whatever the platform keeps there. Removing files and killing processes by
uid alone was too blunt for that: anything already present that happened to belong to the same
account was fair game.

A snapshot of the processes and the directory entries that exist before a scenario starts is now
taken once, and the sweep only ever removes what appeared afterwards. Tested by leaving a file owned
by that account in `/run/lock` and a process running as it before a run: both survive, while the
journal probe run in the same conditions still fails, at 169 rollbacks and 71 `not_on_device`
violations over three scenarios. Every number in `results.md` is identical before and after the
change, which is the point: the sweep is defence in depth and the grading rests on the image.

A cheat could now overwrite a file that was already there rather than create one, and keep its blocks
inside it. That still fails, because what decides a run is whether the value is in the flash image,
not whether the file survived.
