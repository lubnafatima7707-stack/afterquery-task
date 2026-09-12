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
