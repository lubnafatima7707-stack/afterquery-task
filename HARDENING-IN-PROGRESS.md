# State of ecu-nvm-store

## What is in the zip now

`ecu-nvm-store.zip` is the bundle validated at commit `5ca972b`, restored, plus
three changes taken from `ddma-radar-targets`, the task that came closest to
acceptance. Checked from the extracted zip through the real `tests/test.sh`:
oracle 1 on three consecutive runs with the report written each time, nop 0, the
independent store 1, and every cheat probe 0.

The three changes:

1. `tests/test.sh` runs `python -m pytest -q -p no:cacheprovider` instead of a
   bare `pytest`. A `pytest` on the path that is not the one carrying
   `pytest-json-ctrf` rejects `--ctrf` and exits in well under a second, which is
   a reward of 0 with a verifier time of zero and no test ever running. That is
   the shape the reference verification stage reported. `no:cacheprovider` also
   keeps pytest from writing a cache into `/tests`, which is sealed.
2. Both Dockerfiles create the unprivileged account with
   `id -u runner || useradd ...`, so the build cannot fail on an image that
   already has it. The agent image needs the account because the driver shipped
   under `/app/tools` drops to it.
3. `[verifier.environment]` carries only `network_mode`, as the documented
   template and `ddma` do.

## What is not in the zip

The work to make the task harder. The easiness screen solved it three times out
of three in 12 to 17 minutes with every bar cleared by a factor of three or more,
so the live set was being scaled from 24 blocks to about seven tenths of each
part, with the reference rewritten as a segment summary log. That work is
committed at `a4063ba` and is **not finished**: its reference records 67 integrity
violations over the ten graded scenarios, which is why reference verification
failed on it.

Resume it with

    git checkout a4063ba -- ecu-nvm-store/

and the remaining work is: fix the stale and unanswered reads, keep copied cold
data and freshly written hot data in separate open sectors so that choosing the
sector with the fewest live records actually beats taking them in rotation (5.77
against 4.54 erases per 100 writes when they share one, which is no separation at
all), rewrite the independent store at the new scale, rebuild every ablation,
recalibrate the five bars, and redo the documents.

## The open question

This bundle passes every gate that has run except the easiness screen, which it
fails by being solved too often. Submitting it again will reach that screen again.
