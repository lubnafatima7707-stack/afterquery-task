# ecu-nvm-store

The agent writes `/app/nvm_store.py`, the non volatile block store of an engine control unit. The
verifier owns the flash part, the clock and the power: it serves one device operation at a time over
a line protocol, kills the process at points the scenario fixes in advance, starts it again over the
same image, and reads blocks back to see what survived. Grading runs ten sealed scenarios on four
parts whose geometry the agent never sees.

## Difficulty

Between 490 and 700 blocks are live at once, about half of every page on the part and close to
three fifths of the pages a log can put records in once it holds sectors back to erase into, so
nothing here fits anywhere convenient. The store has to run the whole part as a log and reclaim
sectors out of it while the supply is being taken away, and five pieces of judgement have to be
right at once, four of them pulling against each other.

The first is what a record has to carry to be believed after a reset. A program interrupted part way
leaves a prefix of the page written and the rest erased, so a page can hold something that looks
like a record and is not one. Taking a page as a record on its tag alone gives a corrupt read and then an outright crash on a second scenario, because the length read out of a half written page is
not a length.

The second is what orders two copies of a block. A block is rewritten by appending its new version
somewhere else, so the part carries several versions of most blocks and a mount has to know which
one is current without reading everything. That means a generation number on each sector, applied in
order, and a per sector record of what each of its pages holds so the closed sectors do not have to
be read page by page. Applying the sectors in sector order rather than generation order costs 934 violations against a bar of zero, 805 of them a block coming back as a version it had
thousands of writes ago.

The third is that an erase is a request, not a fact. On some parts a sector starts keeping a few of
its pages from its second erase onwards while still reporting the erase as finished, so a sector has
to be read back before it is trusted. Trusting it costs 130 violations and stalls 965 writes. The
opposite mistake costs as much: a reset in the middle of an erase leaves a sector half wiped and
reading exactly like a worn one, so a store that gives a sector up the first time it reads back
written throws away sectors it needs, and 461 writes are never acknowledged.

The fourth is that an acknowledgement is a promise about the part and not about memory. Holding
everything in memory and acknowledging on arrival passes every measure until the supply goes, at
which point it loses 9207 blocks; acknowledging when the write is queued rather than when its page
is programmed costs 4 violations.

The fifth is the budgets, which is where both directions are punished. The store may spend 2.0 ms of
device time per tick, about five page programs, and an erase takes the device away for three or four
ticks. Doing all outstanding work in the tick it arrives in overruns 1963 times. Doing too little is
punished from the other end: every write has to be acknowledged within 35 ticks, and a store that
programs one record every eight ticks is at 2942 with 2845 writes never acknowledged. The mount is
bounded at 8.0 ms of device time, which is what the per sector summaries are for; rebuilding the
index from every page of every sector takes 26.400 ms. And endurance is measured rather than
assumed, at 5.0 erases per 100 acknowledged writes: with the part this full, a reclaim started while twenty
pages of the open sector are still free reaches 13.475, and holding six sectors blank instead of
three reaches 6.267, each of them failing nothing else.

Getting a store that merely works is not the end of it either. A log across a full part deadlocks in
ways a log across an empty one does not: a sector cannot be given up until its live records are
copied somewhere, the somewhere has to be blank, and a blank sector is made by giving one up. Worse, the count of blank sectors only ever falls: once nothing is free, opening one spends a blank
sector and reclaiming one makes a blank sector, so the two cancel, and a reclaim whose sector turns
out to be worn leaves the part one blank poorer for good. These parts wear out up to two sectors, so
the reference keeps three blank. The variant with one passes every other bar and strands 461 writes,
and the variant with two passes as the part stands but has nothing in hand: close the open sector
six pages early instead of two and the same two worn sectors end the run.

The data is synthetic and this is disclosed. A seeded generator
(`authoring/provenance/generate_scenarios.py`) writes the workload and the reset points before any
store runs, and the values grading compares against are the ones the workload asked for, so the
truth never comes from a solver. Reset points are fixed at a request ordinal and then at a kind of
operation, which is why two unrelated designs take their resets at the same points in the workload.

The difficulty is the design rather than hidden data, and the bundle is honest about that: the
device model, the driver and the metric code are all given to the agent, along with three
development scenarios and a skeleton that speaks the protocol. What the graded set varies is what a
development run cannot show by itself, which is four different geometries, between two and seven
resets, runs long enough to wear a sector out, and reset points aimed at the erase and at the first
programs after one.

CPU only, `gpus = 0`. The work is a sequential tick loop of a few device operations over blocks of
at most 32 bytes; there is nothing to batch and a device would sit idle.

## Reference solution

`solution/nvm_store.py`. Page 0 of a sector holds a header with the generation it was opened at.
Records are appended one to a page from page 1 upwards, each carrying its block, its length, a
record sequence number and a checksum over all of it, so a half programmed page fails its checksum
and is skipped, and the append point is the first page that is wholly erased, so such a page is
never written over. The last few pages of a sector are kept for a summary, written when the sector
is closed, listing the block held in every page of it. Mount reads the sector headers, the summary
of each closed sector in generation order, and the pages of the one sector still open, so a summary
a reset spoiled costs a scan of that sector alone.

Reclaim is the whole game with the part this full. The store keeps a live count per sector and takes
the one holding the fewest live records, so a sector whose blocks have mostly been rewritten costs
almost no copying. Copies are ordinary appends, so a reset in the middle of one leaves both the old
record and the partial copy and the newer generation wins; the victim is erased only once its last
live record is out of it, and the erase is read back page by page before the sector is used again
and retried once before the sector is given up. Three sectors are kept blank, because a sector is only
given up after a second erase of it reads back written, and by then its live records are already in
the open sector with no room there to reclaim another one, so that reclaim comes back empty handed
and the pool is one poorer for good; these parts wear out up to two sectors. Writes stop short of the end of the open sector by what the next
reclaim will need, but only while nothing is blank. Work is metered against the tick budget with
reads answered first, so a read is never held up behind a reclaim, and the erase verify is split
across ticks.

The `VARIANT` string at the top of the file is the authoring switch used to measure the ablations.
It is empty as shipped and every value it accepts only removes a piece of the design.

## Verification

`tests/harness.py` keeps the flash image, the clock, the resets and every counter in the verifier
process, so the program under test can reach none of them: it is started as an unprivileged user in
an empty directory, in its own session, and its process group is killed in a finally block.

What a reset takes with it used to be the whole argument, and twice that was wrong. A review first
defeated a harness that reused one working directory across resets; the reply was a sweep of `/tmp`,
`/var/tmp`, `/dev/shm` and `/dev/mqueue`, and an adversarial probe then beat that too, by journalling
into `/run/lock`, which is mode 1777 in the base image with `/var/lock` pointing at it and was simply
not on the list. A list of places to clear can always be one entry short, so the grading no longer
rests on one.

What decides a run is the image itself. A value handed back after a reset has to be present in the
flash image the harness holds, byte for byte and in one piece, and so does every acknowledged value
at the end of a run; anything else is a `not_on_device` violation. A store that kept the blocks in
memory, in a file, or in a daemon has nothing to show there, whatever survived. The sweep is still
there as defence in depth, and it now discovers what to clear by walking the image for directories
that user can write to rather than by naming them, which finds `/run/lock` without having been told
about it.

A third probe then showed that asking the right question at the wrong moment is no better. It kept
the blocks in a daemon that re execs itself with the marker stripped from its environment, calls
setsid and listens on an abstract socket that has no path to find, issued no device operation during
the workload at all, and then programmed the values it was holding into blank pages while the read
back was happening, so that the bytes were in the image exactly when the check looked. The data was
never durable; it was materialised on demand, after the supply had gone.

So the comparison is no longer against the image as it stands. It is against the image frozen at the
instant of the cut, and again before the read back that ends a run. Nothing a store writes after the
power is gone can answer for durability, which is true by construction rather than by enumeration.
The read back also no longer numbers its requests in a range of its own, so it cannot be recognised
from the request number, though that is hygiene: recognising it buys nothing now.

Seven hostile programs are kept under `authoring/evidence/cheats`, two of them rebuilt from the run
audits including the geometry fingerprint and the environment stripping they used. Three of them, an
absent program, one that prints lines that are not the protocol and one that mounts and then stops
answering, are stopped before a bar is reached at all. The three that keep the blocks somewhere other
than the part fail at 11338 violations each over the graded set, of which 10378 are values that were
not on the part when the supply went, and a store that never leaves memory fails at 9207. With every isolation measure switched off,
so that one working directory is reused across every boot, the sweep is a no operation and only the
program itself is killed, all four still fail at the same counts while the reference and the
independent store stay at 0; `authoring/evidence/isolation_off.json` carries those numbers, and they
are what shows the bars rest on the durability check rather than on the sweep.
`authoring/evidence/check_durability_semantics.py` asserts the property itself: a value written
before a cut is in the frozen image, a value written after it is not, and the live image does contain
the later write, which is what the old check compared against.
`tests/test.sh` makes `/logs/verifier` root owned and mode 700 before pytest starts, and `/tests` is
baked with `chmod -R go-rwx`, so neither the program nor anything it forks can touch the reward or
read the graded scenarios. A cheat that writes to `/logs/verifier/reward.txt` and globs `/tests`
records permission denied on every path and then fails on its own merits.

Five bars, measured over the ten scenarios together, all from `tests/scoring.py`: zero integrity
violations, no mount above 8.0 ms of device time, no tick over its 2.0 ms budget, every write
acknowledged within 35 ticks with none outstanding at the end, and at most 5.0 erases per 100
acknowledged writes. The reference scores 0, 2.540 ms, 0, 4 ticks and 2.686. A second correct store
written to a different design, a single map sector rotated through the blank pool carrying a whole
index checkpoint written each time a log sector is opened, with no summary kept inside a log sector
and a mount that reads the newest checkpoint and the one sector of log it does not describe, scores
0, 3.600 ms, 0, 5 ticks and 3.594. Thirteen perturbations of the reference's own constants and of
choices a second author could reasonably have made differently all pass, the worst at 35 ticks and
3.991 erases per 100 writes, so the pass does not depend on one exact tuning, and each bar sits
between the weaker of the two correct stores and the nearest variant that fails.

Each of the five bars is the sole reason some variant fails. Dropping the record checksum, applying
the sectors at mount in sector order, or acknowledging on arrival fails integrity alone, at 1
violation plus a crash, 934 and 4. Dropping the per sector summaries fails the mount bar alone at
26.400 ms. Doing every job in the tick it arrives in fails the tick budget alone at 1963 overruns.
Keeping one blank sector rather than three, giving a sector up after a single erase, or reclaiming
the fullest sector rather than the emptiest, fails the acknowledgement bar alone, at 461, 461 and
4043 writes stranded. Closing the open sector twenty pages early, or holding six sectors blank,
fails the endurance bar alone at 13.475 and 6.267. The same ablation test was run on the independently written store rather than only
on the reference, because a reviewer of an earlier task of mine switched a piece off inside a
shipped solver and watched it pass: all five of its pieces bite, at 3 violations plus a crash for
the record checksum, 25.400 ms of mount for the checkpoint, 162 violations with 461 writes stranded
for the erase proof, 1 violation for acknowledging on arrival, and 1 violation with 1106 writes
stranded for keeping one blank sector rather than three.

Three switches are reported as guards rather than claimed as ablations. Holding pages back at the
end of the open sector for a reclaim that is due, leaving a gap between erases so a read is not
stuck behind two of them, and reading a reclaim copy back before erasing the sector it came from all
argue for themselves, and removing any of them leaves every number on the graded set unchanged.
`authoring/evidence/validation.md` says so rather than claiming a crux that does not measure.

The quick attempt of the kind written in a few minutes, a memory mirror that acknowledges on arrival
and dumps itself into the next sector when one fills, loses 9180 blocks and fails endurance as well.
The shipped skeleton, which answers every read NONE, fails integrity and acknowledgement. A store
that keeps everything in memory and never touches the part fails integrity at 9207, which is what
shows the resets carry that bar rather than the workload.

`numpy==2.0.2` is installed in both images although nothing here imports it, so that a submitted
store which reaches for it still runs; the instruction says what is available.

Maximum read latency, worst tick time, lost writes and per sector erase counts are all measured and
written to `/logs/verifier/metrics.json` but not graded. Read latency is bounded by the contract
already, since a read that is answered BUSY for more than eight ticks counts as a violation, and per
sector wear is even by construction in both correct designs, so grading either would only add a way
for a correct store to fail. `authoring/evidence/results.md` carries every number above and
`python authoring/evidence/evaluate.py` reproduces them; `authoring/evidence/cheat_attempts.md`
records the hostile programs and what the verifier did with each.
