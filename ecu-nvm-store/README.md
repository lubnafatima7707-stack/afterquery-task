# ecu-nvm-store

The agent writes `/app/nvm_store.py`, the non volatile block store of an engine control unit. The
verifier owns the flash part, the clock and the power: it serves one device operation at a time over
a line protocol, kills the process at points the scenario fixes in advance, starts it again over the
same image, and reads every block back to see what survived. Grading runs ten sealed scenarios on
four parts whose geometry the agent never sees.

## Difficulty

Five pieces of judgement have to be right at once, and four of them pull against each other, so no
single habit carries the task.

The first is what a record has to carry to be believed after a reset. A program interrupted part way
leaves a prefix of the page written and the rest erased, so a page can hold something that looks
like a record and is not one. Taking a page as a record on its tag alone costs a corrupt read and
then an outright crash on a second scenario, because the length it reads out of a half written page
is not a length.

The second is the order in which a compaction becomes visible. All live data has to move to a fresh
sector and the old one has to stay authoritative until the new one is complete, which means a
generation number plus a marker written after the copy rather than before it, and a mount that
prefers the newest sector that carries that marker rather than the newest sector. Nine of the forty
nine resets in the graded set are aimed at an erase and thirty at a program, many of them inside
that copy. Choosing by generation number alone produces 429 reads of stale data against a bar of
zero.

The third is that an erase is a request, not a fact. On some parts a sector starts keeping a few of
its pages from its second erase onwards while still reporting the erase as finished, so a sector has
to be read back before it is trusted and retired when it fails. The scenarios are long enough that
the rotation comes round to the worn sector two or three times. Trusting the erase costs 31
violations, and the damage is not where it is first expected: the copy lands on stale pages, the new
header is written over an old one and therefore reads as rubbish, and the next reset then recovers
the previous generation.

The fourth is that an acknowledgement is a promise about the part and not about memory. Holding
everything in memory and acknowledging on arrival passes every measure until the supply goes, at
which point it loses 636 blocks; acknowledging when the write is queued rather than when its page is
programmed costs 49.

The fifth is the budget, which is where the two sided pressure lives. The store may spend 2.0 ms of
device time per tick, which is about five page programs, and an erase takes the device away for
three or four ticks during which nothing else can be done. Doing all outstanding work in the tick it
arrives in overruns 222 times. Doing too little is punished from the other end: every write has to
be acknowledged within 35 ticks, and a store that programs one record every eight ticks is at 764
with 423 writes never acknowledged at all. The mount is bounded the same way. All live records sit
in one sector in the reference precisely so that the index can be rebuilt inside 8.0 ms of device
time; rebuilding it from every page of every sector takes 28.475 ms. And endurance is measured
rather than assumed: compacting while thirty pages are still free is harmless for every other
measure and takes the part to 9.558 erases per 100 writes against a bar of 6.0.

The data is synthetic and this is disclosed. A seeded generator
(`authoring/provenance/generate_scenarios.py`) writes the workload and the reset points before any
store runs, and the values grading compares against are the ones the workload asked for, so the
truth never comes from a solver. Reset points are fixed at a request ordinal and then at a kind of
operation, which is why two unrelated designs take their resets at the same points in the workload:
the reference and the independent store each see 30 resets inside a program, 9 inside an erase, 9
inside a read and 1 between operations.

The difficulty is the design rather than hidden data, and the bundle is honest about that: the
device model, the driver and the metric code are all given to the agent, along with three
development scenarios and a skeleton that speaks the protocol. What the graded set varies is what a
development run cannot show by itself, which is four different geometries, between two and seven
resets, runs long enough to wear a sector out, and reset points aimed at the erase and at the first
programs after one.

CPU only, `gpus = 0`. The work is a sequential tick loop of a few device operations over 24 blocks
of at most 32 bytes; there is nothing to batch and a device would sit idle.

## Reference solution

`solution/nvm_store.py`. Page 0 of each sector holds a header with a generation number, page 1 holds
a seal that is programmed only once the sector holds a complete copy of every live block, and
records are appended one to a page from page 2 upwards. A record carries its block, its length, a
record sequence number and a checksum over all of it, so a half programmed page fails its checksum
and is skipped, and the append point is the first page that is wholly erased, which means such a
page is never written over. Mount reads the sector headers, one seal and the pages of the active
sector; because compaction copies everything forward, all live records are in that one sector.

When the active sector fills, compaction erases the next sector in rotation, reads back every page
of it to prove the erase took, retires it if it did not, writes the new header, copies the newest
record of each live block, and writes the seal last. A reset anywhere in that sequence leaves the old
sector sealed and authoritative and the new one unsealed and ignored, so the cost is the work being
done again. Each write is read back after its page is programmed and acknowledged only then. Work is
metered against the tick budget, with reads answered first so a read is never held up by compaction,
and the erase verify is split across ticks since on the deepest part it is 2.56 ms of reads.

The `VARIANT` string at the top of the file is the authoring switch used to measure the ablations.
It is empty as shipped and every value it accepts only removes a piece of the design.

## Verification

`tests/harness.py` keeps the flash image, the clock, the resets and every counter in the verifier
process, so the program under test can reach none of them: it is started as an unprivileged user in
an empty directory, in its own session, and its process group is killed in a finally block.
`tests/test.sh` makes `/logs/verifier` root owned and mode 700 before pytest starts, and `/tests` is
baked with `chmod -R go-rwx`, so neither the program nor anything it forks can touch the reward or
read the graded scenarios. A cheat that writes to `/logs/verifier/reward.txt` and globs `/tests`
records permission denied on every path and then fails on its own merits.

Five bars, measured over the ten scenarios together, all from `tests/scoring.py`: zero integrity
violations, no mount above 8.0 ms of device time, no tick over its 2.0 ms budget, every write
acknowledged within 35 ticks with none outstanding at the end, and at most 6.0 erases per 100
acknowledged writes. The reference scores 0, 2.880 ms, 0, 11 ticks and 2.491. A second correct store
written to a different design, a circular log over the whole part with index snapshots and
reclamation of the oldest sector rather than compaction forward, scores 0, 2.900 ms, 0, 12 ticks and
1.894. Five perturbations of the reference's own constants all pass, the worst at 17 ticks and 3.207
erases per 100 writes, so the pass does not depend on one exact tuning.

Each bar is the sole reason some variant fails. Dropping the record checksum, the seal, the erase
verify or the late acknowledgement fails integrity alone, at 1 (plus a crash), 429, 31 and 49
violations. Doing every job immediately fails the tick budget alone at 222 overruns. Scanning every
sector at mount fails the mount bar alone at 28.475 ms. Compacting thirty pages early fails
endurance alone at 9.558. Programming one record every two or every eight ticks fails the
acknowledgement bar alone, at 54 and 764 ticks. The quick attempt of the kind written in a few
minutes, a memory mirror that acknowledges on arrival and dumps itself into the next sector when one
fills, loses 1096 blocks. The shipped skeleton, which answers every read NONE, fails integrity and
acknowledgement. A store that keeps everything in memory and never touches the part fails integrity
at 636, which is what shows the resets carry that bar rather than the workload.

`numpy==2.0.2` is installed in both images although nothing here imports it, so that a submitted
store which reaches for it still runs; the instruction says what is available.

Maximum read latency, worst tick time, lost writes and per sector erase counts are all measured and
written to `/logs/verifier/metrics.json` but not graded. Read latency is bounded by the contract
already, since a read that is answered BUSY for more than eight ticks counts as a violation, and per
sector wear is even by construction in both correct designs, so grading either would only add a way
for a correct store to fail. `authoring/evidence/results.md` carries every number above and
`python authoring/evidence/evaluate.py` reproduces them; `authoring/evidence/cheat_attempts.md`
records the hostile programs and what the verifier did with each.
