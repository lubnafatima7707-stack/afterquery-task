# Hardening in progress: do not submit the tree, submit the zip

The easiness screen solved `ecu-nvm-store` three times out of three in 12 to 17
minutes of a four hour budget, with every bar cleared by a factor of three or
more, so the task is being made harder. That work is part done and the source
tree is **not** in a submittable state.

## What to submit today

**Not the zip at the repository root.** It has now been rebuilt from this tree, so
it carries the half finished work: the oracle scores **0** on it, with 67 integrity
violations over the ten graded scenarios (18 rollbacks, 13 stale reads, 36 reads
that never got a value). The other four bars are met on that run, mount 2.73 of
8.0, no tick overrun, worst acknowledge 7 of 35, 4.936 erases per 100 writes of
6.0, but two of the six tests fail and the reward is 0.

The last bundle that passed is the one validated at commit `5ca972b`: oracle 1 on
three consecutive runs, every probe 0, nop 0, every number in README and task.toml
re derived from `results.json`. Recover it with

    git show 5ca972b:ecu-nvm-store.zip > ecu-nvm-store-5ca972b.zip

and submit or rerun against that until the work below lands.

## What is in the tree and what is wrong with it

The scale of the task has been raised so that the live set no longer fits in one
sector and a mount cannot rebuild by scanning:

- the generator sizes the live set to about seven tenths of each part, 694 to 868
  blocks instead of 24, with a fifth of the blocks taking four writes in five, and
  2200 to 5200 writes per scenario, which turns the part over two to five times
- the driver reads back a fixed sample of 96 blocks after each reset and the whole
  set at the end, and tracks blocks a reset left unchecked as uncertain
- the reference is rewritten as a segment summary log: a summary written when a
  sector is closed, a mount of headers plus summaries plus the one open sector
  (1.9 to 2.6 ms against 20 to 32 ms for reading the whole part), reclaim of the
  sector holding the fewest live records

**The reference is not correct yet.** Over four graded scenarios it records 3
stale reads and 10 unanswered reads. One real bug was found and fixed on the way,
worth keeping in mind because it is exactly the kind of mistake the new crux is
meant to catch: the summary was composed again on every tick it spanned, so a
record that landed mid seal left chunks that disagreed, a block appeared in none
of them, and its only copy was erased with its sector.

## The finding that changes the design

Choosing the sector with the fewest live records performs no better than taking
them in rotation, 5.77 against 4.54 erases per 100 writes. That is not a bug. At
seven tenths full, with reclaimed copies and new writes sharing one open sector,
every sector ends up equally live and a victim picker has nothing to choose
between. What separates a good design from a poor one is keeping copied cold data
and freshly written hot data in different open sectors. That is the judgement the
task was missing, and it is the next thing to build.

## Remaining

Fix the stale and unanswered reads, add the hot and cold separation, rewrite the
independent store at the new scale, rebuild every ablation against the new design,
recalibrate all five bars from measurements, rerun the three cheats and the
durability semantics test, then redo README, task.toml and the evidence files and
revalidate end to end.
