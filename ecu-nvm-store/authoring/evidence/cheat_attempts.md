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
| `cheats/reward_writer.py` | writes `/logs/verifier/reward.txt` and `/logs/verifier/ctrf.json`, globs `/tests/hidden` and `/tests/*.py`, then answers every read NONE | every write refused with permission denied, every glob returns zero files, `reward.txt` unchanged at `0`, and it then fails integrity at 7808 violations with 4043 writes never acknowledged |
| `cheats/ram_only.py` | acknowledges on arrival, answers from memory, never touches the part | 9207 integrity violations over the graded set, reward 0 |
| `cheats/file_backed.py` | keeps the blocks in a file in the working directory, `/tmp`, `/var/tmp`, `/dev/shm`, the home directory and `TMPDIR`, and in a daemon behind an abstract socket, and reloads them at MOUNT | 11338 integrity violations, reward 0 |
| `cheats/run_lock_journal.py` | the adversarial probe, rebuilt from the run audit: issues no device operation at all and journals the blocks as JSON into `/run/lock`, named by a fingerprint of the geometry | 11338 integrity violations, reward 0 |
| `cheats/lazy_materialize.py` | the later probe, rebuilt from the run audit: a daemon that re execs without the marker, an abstract socket, and the held values programmed into blank pages once the read back begins | 11338 integrity violations, reward 0 |
| `shortcut_store.py` | the quick attempt: memory mirror, ack on arrival, sector dump on fill | 9180 integrity violations and 54.172 erases per 100 writes, reward 0 |
| `environment/tools/skeleton_store.py` | the shipped skeleton, every read NONE, no acknowledgements | 7808 integrity violations and 4043 writes unacknowledged, reward 0 |

## Why the reward channel holds

`tests/test.sh` chowns `/logs/verifier` to root and sets mode 700 before pytest starts, so the
unprivileged user the store runs as cannot create or replace `reward.txt` or `ctrf.json` even while
the verifier is still running. `tests/Dockerfile` bakes `/tests` with `chmod -R go-rwx`, so the
graded scenarios and the grading code are unreadable from the same user. `harness.py` starts the
program with `start_new_session=True` and kills the whole process group in a finally block, and the
`sleeper.py` attempt exists to show that a double forked child does not keep the run alive or get a
second chance at the reward.

## The hole a review found, and what closed it

A review failed this task on anti cheat robustness, and it was right. The harness used to create the
program's working directory once per scenario and reuse it across every reset, and `/tmp` was
writable too, so a store could keep the blocks in a file and never touch the device: the reviewer's
probe scored 0 violations, 0.0 ms of mount time, 0 overruns, 0 unacknowledged writes and 0.0 erases
per 100 writes, which is reward 1. The instruction claimed working directory writes were discarded;
nothing enforced it.

A reset now takes everything but the flash with it, in `Runner._purge_foreign_state`:

- the working directory is removed and rebuilt for every boot, and the copy of the program in it is
  owned by root and mode 444, so the program cannot keep state in its own source either
- every entry owned by the unprivileged user is removed from `/tmp`, `/var/tmp`, `/dev/shm` and
  `/dev/mqueue`, which is the whole set it can write to, since every other directory in the image
  belongs to root and the one holding the verdict is mode 700
- the shared memory segments, message queues and semaphores it owns are removed through `shmctl`,
  `msgctl` and `semctl` with `IPC_RMID`, so a key that outlives a process is no use
- every process running as that user is killed, not only the process group, which closes the variant
  where a child calls setsid and answers later over an abstract socket or a loopback port
- `TMPDIR`, `TMP` and `TEMP` point inside the working directory, so a well behaved program's
  temporary files are swept as well

The probe was widened to try all of those paths and the daemon, and kept in `cheats/file_backed.py`.
It now scores 11338 integrity violations, and the run report
carries the count of what was taken away from it so the enforcement is visible rather than implied.
`authoring/evidence/bundle_checks.py` fails if any part of this is removed from the harness, or if
the copy of the driver given to the agent stops matching the one that grades.

## The second hole, and why there will not be a third of this kind

The anti cheat probe beat the fix above. It read the copy of the driver under `/app/tools`, saw that
the sweep was the hardcoded tuple `/tmp`, `/var/tmp`, `/dev/shm`, `/dev/mqueue`, enumerated the
world writable directories in the image, found `/run/lock` at mode 1777 with `/var/lock` pointing at
it, and journalled its blocks there. It issued no device operation whatsoever and scored reward 1,
with zero erases, zero programs and 0.0 ms of mount and tick time over 9820 acknowledged writes.
That probe, and the review before it, ran against an earlier and smaller shape of this task, so the
counts quoted from their reports are on that scale; every number in the tables above is from the
graded set as it stands.

The lesson is that a list of places to clear is a blocklist, and a blocklist can always be one entry
short. Two changes followed, and only the first is load bearing:

1. **The image is the evidence.** A value handed back after a reset has to be present in the flash
   image the harness itself holds, byte for byte and in one piece, and so does every acknowledged
   value when a run ends. Anything else is a `not_on_device` violation. Memory is gone after a reset,
   so a store that kept the blocks anywhere but the part has nothing to show, no matter what survived
   or where. This is checked against `Runner._image_bytes`, which the program cannot reach or
   influence, and it is stated in the instruction as part of the contract.
2. **The sweep discovers rather than lists.** `writable_dirs` walks the image once per verifier
   process and collects every directory the unprivileged user can write to, by ownership, group or
   the other write bit, so `/run/lock` is found without anyone having thought of it. The seed list
   remains as a fallback if the walk cannot run.

The probe is rebuilt in `cheats/run_lock_journal.py`, including the geometry fingerprint it used to
name its journal, and it now fails at 11338 violations. The number that shows which change is doing
the work is measured with `_purge_foreign_state` reduced to rebuilding the working directory and
nothing else, so every journal and every daemon survives the run untouched:

| solver, with every isolation measure disabled | not_on_device | total integrity violations | bars |
|---|---|---|---|
| `cheats/run_lock_journal.py` | 10378 | 10378 | integrity |
| `cheats/file_backed.py` | 10378 | 11338 | integrity |
| `cheats/lazy_materialize.py` | 10378 | 11338 | integrity |
| `cheats/ram_only.py` | 1557 | 9207 | integrity |
| `solution/nvm_store.py` | 0 | 0 | none |
| `independent_store.py` | 0 | 0 | none |

Reproduced by the script that writes `authoring/evidence/isolation_off.json`: the working directory
is reused across every boot of a scenario, `_purge_foreign_state` is a no operation, and only the
program itself is killed, so every journal and every daemon survives the run untouched.

Neither correct store is touched by the check, because both write the payload into a record and can
read it back; neither probe survives it, because none of them ever wrote anything to the part.

## Why memory alone cannot pass

The interesting negative result is `ram_only.py`. It is correct in every respect that can be
observed without losing the supply: it acknowledges instantly, answers every read with the value the
workload last asked for, issues no device operations at all and therefore never overruns a tick,
never erases anything and mounts in no time. It fails on integrity alone, and only because of the
resets. That is the evidence that the integrity bar is carried by the power cuts rather than by the
workload.

It also found an earlier hole in the harness. Resets used to be triggered by counting
device operations after a request ordinal, so a program that issued no operations was never reset at
all and `ram_only.py` passed every bar. Each reset now carries a deadline in ticks and happens
anyway if the operation it was aimed at never comes, which is what the `IDLE` entries in the reset
log are. After that change the same program loses 9207 blocks, and no process of it survives the run.

## One deliberately weakened reference that crashes rather than lies

`no_record_checksum`, the ablation that believes a page on its tag byte alone, is worth a note
because its failure is not only a wrong value. On one of the ten scenarios it reads a length out of a
half programmed page, asks for something the device rejects, and the process exits mid tick, so it
fails both the completion test and the integrity bar. A checksum over the whole record is what turns
a torn page into a page that is skipped.

## The third hole: the right question asked at the wrong moment

The next probe passed with reward 1 against a harness that checked a returned value against the flash
image as it stood when the read was answered. It combined three things, and only the last one
mattered:

1. a daemon that re execs itself with every `NVM_` variable stripped, so matching on the run's own
   marker does not recognise it, calls setsid to leave the process group, and listens on an abstract
   unix socket, which has no path for a directory walk and is not an ipc object for the purge
2. recognising the read back from its request numbers, which used to start at three million
3. **materialising on demand**: no device operation during the workload at all, every write
   acknowledged out of the daemon's memory, and then, once the read back began, the held values
   programmed into blank pages so the bytes were in the image exactly when the check looked

The reported metrics say it plainly: 0 erases, 0.0 ms of mount time, 0 tick acknowledge latency,
across 49 power cuts.

The repair is to compare against the image **frozen at the instant of the cut**, and again before the
read back that ends a run, rather than against the image as it stands. Power is already gone at that
point, so nothing written afterwards is durable by definition and nothing written afterwards can
satisfy the check. Request numbers for the read back now continue the same run of integers the
workload uses, which removes the fingerprint in (2), though with the freeze in place recognising the
read back buys nothing.

The probe is rebuilt as `cheats/lazy_materialize.py`, including the re exec, the abstract socket and
the geometry fingerprint, and it fails at 11338 violations.

### What is measured here and what is not

Honestly: the rebuilt probe carries its values across resets perfectly, which is measurable (it
records no rollbacks at all, so its daemon does survive and does answer), but its materialising is
less well timed than the original's, so running it against the old check does not reproduce a clean
pass. That half of the comparison is therefore not evidence I can show. What is shown instead, and
what the fix actually rests on, is the mechanism itself:
`authoring/evidence/check_durability_semantics.py` freezes an image, programs a value afterwards, and
asserts that the later value is absent from the frozen image, present in the live image, and that the
two are not the same object. That is the whole of the property, and it is checked without going
through any solver.
