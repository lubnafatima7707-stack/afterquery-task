# State of ecu-nvm-store

The hardening the easiness screen asked for is finished and is in the zip.

## What changed

The live set went from 24 blocks, which fitted in one sector, to between 490 and
700 blocks filling about half of every page on each part, and close to three
fifths of what a log can put records in. That is what the screen was
really measuring: with everything in one sector the task is a careful append log
and three agents out of three wrote one in under twenty minutes. With the part
this full the store has to run the whole part as a log and reclaim
sectors out of it while the supply is being taken away, which is a different
problem and deadlocks in ways the small one cannot.

The reference is rewritten to match: a header with a generation on page 0 of each
sector, records appended one to a page, a summary in the last pages of a sector
written when it is closed so the mount does not read every page of every sector,
a reclaim that takes the sector with the fewest live records, an erase that is
read back before the sector is trusted and tried twice before it is given up, and
two sectors kept blank so a reclaim that turns up a worn sector still has
somewhere to go.

The independent store is rewritten to a design that scales differently: no
summary inside a log sector at all, and instead one map sector rotated through
the blank pool carrying a whole index checkpoint written each time a log sector
is opened.

## Where it stands

From the rebuilt zip, through the real `tests/test.sh` in the container layout:
reward 1 with `6 passed in 19.70s`, reward 0 with the artifact removed, and three
consecutive verifier runs over the reference giving identical numbers.

| | integrity | mount ms | overruns | ack ticks | unacked | erases/100 |
|---|---|---|---|---|---|---|
| bars | 0 | 8.0 | 0 | 35 | 0 | 5.0 |
| reference | 0 | 2.380 | 0 | 4 | 0 | 2.384 |
| independent store | 0 | 4.020 | 0 | 7 | 0 | 3.110 |

Fourteen ablations fail, nine perturbations pass, and every one of the five bars
is the sole reason some variant fails. Three switches are reported as guards
rather than claimed as ablations because removing them changes no number on the
graded set. `ecu-nvm-store/authoring/evidence/results.md` has the whole table and
`validation.md` says what was run.

## Two things that did not work and are recorded rather than buried

Keeping freshly written records and reclaimed records in separate open sectors,
which is the standard way to make choosing the emptiest sector beat taking them
in rotation, was built and measured. On a part this full it was worse on every
count: 3.007 erases per 100 writes against 2.384, a slower mount, and round robin
still within eight percent of it. It is not in the shipped design.

Round robin reclaim passes the erase bar, at 2.562 against the reference's 2.384.
That is a property of this workload rather than a gap in the bar, and
`validation.md` says so instead of claiming victim selection as a crux the bar
does not test. What the erase bar does separate is how much of a sector is thrown
away per erase.
