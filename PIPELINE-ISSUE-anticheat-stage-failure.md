# Pipeline issue: anti cheat probe stage ended in UnknownApiError before it could be judged

## Summary

The anti cheat probe on `ecu-nvm-store` (job `wGXdhuRZboyxsEk58e2l`, trial
`task-cheat__o8wdDpZ`) ended after 2 minutes 37 seconds with status
`failed · UnknownApiError` and reward 0, and the stage then reported
"trajectory analysis missing or contains no unearned-credit judgment for the
adversarial trial". The page itself says "Validation failed. The AI evaluation
service could not complete this stage. This is not a verdict on your task."

I am reading this as an infra failure rather than a result, and would like a
rerun. The reasons are below, along with the one way it could have been my
bundle and what I did about that anyway.

## What the archive shows

`cheat/job.log` carries a traceback raised inside harbor itself:

```
Traceback (most recent call last):
  File "/usr/local/lib/python3.13/site-packages/harbor/environments/docker/docker.py",
    line 1052, in service_download_file
```

That is harbor's own docker environment layer failing to fetch a file from the
container. It is not the verifier: the verifier never ran, no reward was written
by it, and the trial produced 9.3k output tokens, so the agent had started work
and the run died underneath it.

The downstream stage then had no trajectory to analyse, which is exactly what its
message says. Easiness probe, difficulty probe and run audit are all still
pending behind it.

## Why I do not think the bundle caused it

The immediately preceding anti cheat probe on this same task ran to completion on
the same bundle shape: it built the environment in 25 seconds, ran the agent for
6 minutes 43 seconds, collected `/app/nvm_store.py` from the container, and the
verifier completed in 77 seconds. Nothing about artifact collection is unusual
here: one small text file at a path the verifier image creates with `mkdir -p`.

The task is CPU only (`gpus = 0`), so it is not the GPU mount path reported
separately in `PIPELINE-ISSUE-gpu-tasks.md`.

## The one way it could have been mine, now closed regardless

Between the two probe runs I added an unprivileged account to
`environment/Dockerfile` and a sweep to `tools/harness.py` that, after each
simulated power cut, killed processes and removed files belonging to that
account. That driver is also given to the agent to develop against, so it runs
inside the agent's container, where the platform's own machinery lives. If any
file or process there had belonged to the same uid, the sweep could have removed
it.

I have scoped the sweep so this cannot happen: it now takes a snapshot of the
processes and directory entries that exist before a scenario starts and only ever
removes what appeared afterwards. Verified by leaving a file and a running
process owned by that account in place before a run: both survive, while a probe
that journals its blocks outside the device still fails. The grading does not
depend on the sweep at all, since a value returned after a reset has to be
present in the flash image the verifier holds.

## What I am asking for

- A rerun of the anti cheat probe for `ecu-nvm-store`.
- If the rerun fails the same way, the `service_download_file` path in
  `harbor/environments/docker/docker.py` is worth a look, since the failure is
  raised there rather than in any task code.
