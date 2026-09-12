---
name: author-harbor-task
description: Use when creating, extending, or debugging an AfterQuery harbor benchmark task bundle in Project Kepler (instruction.md, task.toml, environment, solution, tests). Covers the required bundle layout and rules, how to write instruction.md so it reads as human authored and clears the AI generated text screen, and the difficulty and verifier design pattern that held up under testing.
---

# Authoring a harbor task for Project Kepler

Reference doc: `Authoring tasks.md` in the project root. Read it fully before a first
submission in a category you have not built for before; this skill is the condensed,
battle tested checklist for repeat work, not a replacement.

## Picking the next task

The similarity gate rejects a task that is an earlier one re skinned, and the review asks what
specifically the agent will get wrong. So before building, name the failure mode and check it is
not the one the last task tested: `vehicle-ekf-fusion` is "fuse logs into a trajectory, score by
RMSE", so `ddma-radar-targets` was deliberately built as array signal processing with set
matching instead. Favour problems where several independent pieces of practitioner judgement all
have to be right at once, since a single standard recipe is what makes a task read as cookbook.

Two decisions belong to the user, not to you: which candidate idea to build, and whether they
genuinely have the hands on experience the topic claims. Ask both up front in one question rather
than building first, because `relevant_experience` must be true and specific, and the answer can
rule an idea out.

Then ask the question that decides whether the task can ever be hard enough: **can a capable agent
rebuild your data generator and grade itself against it?** Everything fairness requires you to
disclose (the physics, the conventions, the scene bounds, the metric definitions) is also
everything needed to write a matching simulator. On ddma-radar-targets the winning probe agent did
exactly that, building a simulator of the forward model plus a grader like scorer and validating
over 96 synthetic scans across four synthetic units before submitting, which restored the feedback
loop that hidden graded data was meant to remove. If a task reduces to "infer a forward model from
data, then invert it", assume a frontier agent solves it no matter what you hide. The same trap
was already visible on vehicle-ekf-fusion, where a detailed data generation description let a
subagent write a matching simulator and tune against it. Prefer difficulty that cannot be self
checked: the behaviour of a system that only exists in the environment (a concurrency or timing
defect), performance against real hardware, long horizon work across a large codebase, or dynamic
state the agent cannot replay.

## Bundle layout (structure check fails the whole submission if this is wrong)

```
your-task/
  instruction.md            the complete instruction, ends with the exact suffix below
  task.toml                 see template section
  README.md                 ## Difficulty  ## Reference solution  ## Verification
  environment/
    Dockerfile               agent's container, never references solution/ or tests/
    data/ ...                agent visible inputs only, no ground truth, no seeds/params that reveal it
  solution/
    solve.sh                 reference solution, must score 1 as the oracle
  tests/
    test.sh                  writes /logs/verifier/reward.txt with exactly 0 or 1
    Dockerfile                bakes /tests, pins pytest==8.4.1 pytest-json-ctrf==0.3.5
    ...                       ground truth, sealed, never shipped to the agent
  authoring/                 never mounted into any container
    provenance/ ...          generators, seeds, source manifests
    evidence/ ...            cheat attempts, ablation scores, tuning notes
```

Hard rules worth re-checking every time:
- Every text file in the bundle must use LF line endings. This machine is Windows, and editors
  (or other assistants) saving CRLF will break `solve.sh` and `test.sh` under bash
  (`set -euo pipefail\r` is an invalid option, paths gain a stray `\r`) and break the exact
  instruction suffix check. Scan for `\r\n` before every zip, especially after outside edits.
  Do the scan in Python by reading bytes (`b"\r" in open(p, "rb").read()`), not with Git Bash
  `grep $'\r'`, which silently missed CRLF result files here. Evidence outputs written by Python
  on Windows in text mode (results_*.txt) come out CRLF, so check them too.
- Pin every pip/uv install with `==` in every Dockerfile.
- Never pin apt packages; `apt-get update` then install then `rm -rf /var/lib/apt/lists/*`.
- `[environment] network_mode = "public"`, `[verifier.environment] network_mode = "no-network"`. Never set the deprecated `allow_internet`.
- `[agent].timeout_sec` in [3600, 28800]; `[verifier].timeout_sec` capped at 28800 too.
- `cpus` in {1,2,4,8,16}; `memory_mb` in {1024,2048,4096,8192,16384}; `storage_mb` <= 40960.
- `gpus` is 0, or exactly 1 with `gpu_types = ["H100"]`. Decide this from the actual compute
  shape of the reference solution, not habit: a small, strictly sequential recursive
  computation (a single Kalman filter, a per step simulation loop) gets no benefit from a GPU
  and should stay `gpus = 0` with the reasoning spelled out in `difficulty_explanation`. Reserve
  GPU for genuinely batchable or large scale parallel workloads.
- `task.name` = `afterquery/<slug>`, slug is lowercase kebab case, at most 3 hyphen separated
  words.
- No `harbor-canary` markers anywhere in the bundle.
- `artifacts` in task.toml lists every absolute path the verifier reads from the agent, and the
  instruction must name that same absolute path explicitly.
- Whenever the verifier executes agent supplied code, protect the reward channel before that code
  runs: `mkdir -p /logs/verifier` then `chown root:root` and `chmod 700` on it in `test.sh`, and
  launch the program with `start_new_session=True` and kill its whole process group
  (`os.killpg(proc.pid, signal.SIGKILL)`) in a finally block. Dropping to an unprivileged user and
  sealing `/tests` is not enough on its own: a review failed the task because the default 755 on
  `/logs/verifier` let the runner user overwrite `reward.txt`, and a double forked process could
  outlive the harness and forge the verdict.

## task.toml required fields

Copy the template from `Authoring tasks.md` (`## task.toml`) verbatim and fill every field except
`research_advisor` and `referred_by`, which are optional and should be omitted entirely rather
than left as empty strings. `author_organization`, `author_profile`, `relevant_experience`,
`difficulty_explanation`, `solution_explanation`, `verification_explanation` must all be genuine
and specific; reviewers read these first and generic or placeholder text fails review. Never
invent credentials on the user's behalf, ask for them.

## Writing instruction.md so it passes the AI generated text screen

The pipeline runs an AI check on instruction.md specifically. Write it like a person who does
this work for a living dashed off a brief, not like a generated document:

- No em dashes, no en dashes, and no hyphens at all in the prose, including ordinary compound
  words. Rewrite "real-time" as "real time", "well-tuned" as "well tuned", "cross-functional" as
  "cross functional". Hyphens are fine only where they are structurally required elsewhere in the
  bundle (task slug, URLs, toml enum values) but not in instruction.md prose.
- No special characters: no bullet glyphs, no markdown bold/headers sprinkled through the body,
  no arrows. Plain paragraphs. This also serves the "don't write a checklist of steps" guidance
  in the authoring doc: state the goal and the deliverable, name the exact input and output paths,
  and let the agent choose its own method.
  Nothing in the pipeline actually requires this to be terse or list free beyond that guidance,
  so plain prose paragraphs both read as more human and satisfy the "not a checklist" rule at once.
- No repeated sentence structure. If two paragraphs both introduce a file, do not open both with
  the same template ("The file X contains..."); vary the construction each time. Read the draft
  back and flag any sentence that is a near duplicate of another in shape or wording.
  Scan explicitly for parallel enumeration sentences, that is the most common generated-text tell.
- Add at most one genuinely unnoticeable typo in the prose (a wrong vowel, a doubled or dropped
  letter in a common word: "reciever", "accross", "seperates"), never inside a file path, a
  column name, a numeric threshold, a unit, or the mandatory closing sentence. Getting those wrong
  breaks the task rather than making it look human. One is the ceiling, not a target: the quality
  review cited deliberate typos under instruction_clarity, so the earlier habit of scattering two
  or three is now a liability, and zero is defensible when the prose already varies in structure.
- The instruction still ends with, after a blank line, exactly:
  `You have N seconds to complete this task. Do not cheat by using online solutions or hints
  specific to this task.` where N is the integer `[agent].timeout_sec`, followed by at most one
  trailing newline. Verify this with a script, not by eye, once the number is finalized.
- Before finishing, grep the file for `[-\x{2013}\x{2014}]` (hyphen, en dash, em dash) and for any
  non ASCII character. Both should come back empty.

## Difficulty and verifier design pattern that held up

The strongest verifier shape found so far: build a small, honest reference solution first, then
build two to four deliberately weakened variants of the exact same reference solution (drop one
piece of correct engineering each time: skip a bias correction, skip an outlier gate, skip a
sensor channel that resolves an ambiguity). Score all of them against the same sealed ground
truth and only then set thresholds, placing them clearly above every weakened variant's error and
clearly at or below the honest solution's error with some margin. This is more convincing and
more robust than guessing a threshold and hoping: `authoring/evidence/cheat_attempts.md` should
carry these numbers, worked example in `vehicle-ekf-fusion/authoring/evidence/cheat_attempts.md`.

While tuning, watch for degenerate failure modes that are easy to build into a reference solution
by accident and will sink the oracle run:
- Symmetries in the model that make two very different explanations of the data equally
  consistent with a narrow measurement set (for example position only tracking cannot tell
  forward-facing-forward from backward-facing-reverse; a second, independent channel that breaks
  the symmetry, such as a velocity or heading measurement, is often the fix, and is realistic
  rather than a hack).
- A hard rejection gate (chi square or similar) with no recovery path can lock itself out
  permanently: once a long bad stretch inflates the covariance enough, later good measurements
  also look like outliers and never get back in. Add a bounded forced reacquisition after N
  consecutive rejects, or make the outlier corruption itself have a natural counterpart channel
  that stays clean and can be trusted to break the lock (as above).
- Any process noise or trust parameter that looks reasonable on paper needs to actually be run
  against the full length synthetic run before it is trusted; the failure modes above only show
  up over tens of seconds to minutes, not in a short smoke test.

Prefer a disclosed, seeded synthetic generator with ground truth from the simulator itself over
sourcing real proprietary data, when a believable one is possible for the field: it sidesteps
licensing and availability problems entirely and, done honestly, satisfies the "real data or a
disclosed seeded generator whose ground truth comes from an independent source" requirement. Say
so plainly in `difficulty_explanation`, do not present synthetic data as real.

### Calibrate thresholds against three things, not one

Before fixing any bar, measure all of these on the shipped data:
1. the honest reference,
2. two to four ablations of the reference, one correct piece removed each time,
3. at least one independent correct solver built differently end to end, plus one "clever
   shortcut" of the kind a reviewer writes in a few minutes.

Put the bar between the weakest correct solver and the strongest broken one, and quote those
measured numbers in README and task.toml exactly. Worked example: `ddma-radar-targets`, where
`authoring/evidence/evaluate.py` rescores the reference, four ablations, four tuning
perturbations, an independent chain and a shortcut in a single run and writes `results.json`
next to a `results.md` table.

Two habits make this cheap:
- Give the reference `run()` keyword switches for each piece it can drop (`mitigate`, `calib`,
  `empty_band`, `two_targets`) and for its tuning knobs, so every ablation and perturbation is one
  call rather than a copied file that drifts out of sync.
- Put the metric code in `tests/scoring.py` and import it from both `tests/test_verify.py` and the
  evidence scripts, so the evidence is scored by the verifier's own code.

Perturb the reference's own knobs (detection threshold up and down, excision factor up and down)
and confirm it still passes. A pass that survives only one exact tuning is a knife edge the
difficulty probe will fall off.

Assume the reviewer will ablate the solvers you ship. On `multi-object-tracking` the reviewer
switched off the Doppler term inside the bundle's own `authoring/evidence/independent_tracker.py`,
watched it pass every bar anyway, and failed the task: the advertised hard part was not load
bearing. So run that test yourself on every shipped solver, not only on the reference, and for
every crux the difficulty explanation claims. If disabling a piece leaves the score essentially
unchanged, either the data has to change until it bites or the claim has to go.

### Generator rules that keep the truth honest

- Enforce a detectability floor when drawing truth: reject any object the physics cannot make
  recoverable (`ddma-radar-targets` uses a per channel SNR floor). A truth row no correct method
  can find is an unwinnable recall loss that punishes good solvers.
- Enforce separation constraints so the truth is unambiguous, except where the ambiguity is the
  point and is graded (the pairs sharing one range Doppler cell were placed deliberately).
- Every difficulty you claim must bite on the shipped data, provable by an ablation. If removing
  the piece barely moves the score, cut the claim: the EKF review caught a reacquisition rule that
  never fired on the shipped data.
- Regenerating from the seed must reproduce the committed data byte for byte. Check this after any
  edit to the generator, comparing with line endings normalized.

### Diagnose before you tune

When the reference or a variant scores badly, list the individual misses and spurious rows with
their causes before touching a threshold. A short script that prints every missed truth row (with
its class and SNR) and every unpaired prediction, tagging the ones that coincide with an artifact
the generator injected, found the real cause in a single run here: none of the reference's twenty
spurious rows were the multipath images it was suspected of reporting, they were single strong
reflectors being split in two. Threshold tuning without that would have made things worse.

That failure is worth remembering as a class. A statistical test calibrated against the noise floor
is wrong wherever the real error floor is model mismatch: on a 50 dB reflector the residual left by
a one source fit is array calibration error, not noise, so a noise based model order test always
finds a second source and the reference fails its own verifier. Any accept or reject rule in a
reference solution wants a relative criterion next to the absolute one, and the ablation that
removes the relative half is a good extra difficulty claim in its own right.

### Lessons from rebuilding multi-object-tracking

The first version failed difficult and novel as a textbook tracker. The rebuild put the sensor on a
moving, turning car with unknown ego motion, extended objects and dense roadside structure, and
the reference only started working after these, each found by listing misses and false rows first:

- A single absolute threshold against a noise floor that scales with something is a bug. The
  ego compensated speed of a static track grows with range, because a small yaw error swings a
  distant point sideways, so a flat 1.5 m/s moving bar reported static posts at 60 to 80 m. A
  bar of 1.0 + 0.02 r m/s cut flagged static frames from 2.7 to 0.9 percent while keeping 94
  percent of pedestrian frames. A significance test on the fit residual was worse, because the
  yaw error is a drift the residual never sees. Measure the noise per range bin before choosing.
- Never estimate a new track's velocity from a two point difference of an extended body's
  centroid; it was off by 5 to 28 m/s and every fresh vehicle track failed its next gate and died
  before confirmation. Seed the radial component from the Doppler residual, fit only from three
  points, and gate on Doppler only from the third hit.
- Suppressing a duplicate only at report time leaves both tracks alive, and the pair then trades
  the report back and forth, one identity switch each time (14 of 16 switches). Merge at track
  level and retire the younger one, but only when both are moving and moving alike: a pedestrian
  passing a curb reflector shares its near zero Doppler and was being merged out of existence.
- Give the generator a separation check that refuses to write data, not a warning. Two lead
  vehicles were spawned in the same lane 0.2 m apart, and a crossing pedestrian kept meeting a
  long lived car; hand picking a new birth frame only moved the collision, a small search over
  birth and start distance with the generator's own geometry found a clean slot at once.
- Define event windows (occlusions) in frames from the object's own birth, never as a fraction
  of the remaining run; the fraction version put both occlusions after the cars had left view,
  so the coasting crux never fired.
- A per object "mostly tracked" bar is brittle on short lived objects: a car in view for 23
  frames loses about 5 to confirmation, so knob perturbations swung the object fraction by
  several objects. Sweep the per object fraction against the correct and broken solvers before
  fixing it, and remember the object fraction moves in steps of 1 / n_objects.

### When the difficulty probe says the task is too easy

The probe runs 8 trials and the task must be solved at most 6 times; 7 of 8 fails. What to do with
that, learned from the ddma-radar-targets probe:

- Read the run audit before changing anything. It reports, per trial, which cruxes each agent
  actually built and how long it took (45 to 70 minutes of a 4 hour budget there), so you learn
  which pieces are no obstacle at all. It also tells you whether the failure was scientific or a
  spec problem.
- Do not reach for tighter bars. If the audit says the bar headroom "tracks scientific quality",
  tightening only shaves marginal correct runs, and the quality review objects to failures that
  come from precision details. Add a piece of judgement instead.
- Prefer a new crux that pressures a different metric than the one already carrying the task, and
  where both over correcting and under correcting cost you. Reporting a multipath image costs
  unpaired rows; pruning too eagerly costs recall. That two sided shape is much harder to luck
  into than a one sided threshold.
- Distinguish good levers from bad ones. Adding judgement (objects inside one beamwidth, artifacts
  that must not be reported) is a good lever. Turning up hardware error levels is a bad lever:
  raising the DDMA phase shifter errors from 4 to 7 degrees corrupted the array manifold, pushed
  every correct chain's azimuth RMSE from about 0.19 to 0.30 against a 0.35 bar, and would have
  failed correct methods for no added insight. It was reverted. If a change degrades the
  independent correct solver as much as the broken ones, it is noise, not difficulty.
- Re run every ablation and recalibrate all bars from the new measurements afterwards; a harder
  scene changes the reference's own scores too. Report honestly what the sweep shows, including a
  perturbation that now fails (over eager interference excision manufactured 127 unpaired rows),
  rather than quietly dropping it from the evidence.

### Knowing when to stop hardening a task

The probe runs 8 trials and passes at 6 solves or fewer, so 7 of 8 is one trial away, not miles
away, and the noise is wide: at a per trial solve rate of 0.875 an unchanged rerun lands in band
about 26 percent of the time, at 0.70 about 63 percent. Do not read 7 of 8 as hopeless, and do not
read a single pass as proof of anything either.

Before picking a lever, get the numbers, not the narrative. Two small files per trial say more than
megabytes of trajectory: `verifier/metrics.json` (whatever your verifier writes) and the agent's own
notes under `agent/sessions/projects/-app/memory/*.md`, where a frontier agent records what it found
hard and how it validated itself. The deliverable itself often is not in `artifacts/` in the browser
even when the manifest says it was collected.

Then compare the spread of *correct* solvers against each bar. There is an honest lever only when a
bar can sit outside that spread. On the third radar probe there was none left: correct chains ran
0.990 to 0.993 recall against a 0.95 bar, azimuth 0.295 to 0.358 degrees with the reference at
0.302 (so any bar failing the weakest correct chain also cuts inside the spread of chains that did
everything right), and unpaired rows were bimodal, 2 against 310, so moving that bar flips nobody.
Note also what the single failure was: an agent that found every reflector, including all the fast
ones, and then reported 609 rows for 302 reflectors without pruning. A failure like that is not
evidence that any crux is working.

Set a stop rule before you start: two probes on one task, then rebuild rather than iterate. Three
probes at roughly 200 dollars each bought a task that is fair, sealed and fully evidenced, and that
frontier agents still solve seven times out of eight.

### Move the difficulty onto ground that disclosure cannot give away

When the run audit calls a crux a hidden convention, simply stating the rule usually hands the task
back to the agents, because a stated rule is a few lines of code. The levers that survive being
written into the instruction, all used in the ddma-radar-targets rebuild and all measured by an
ablation:

- Make the deliverable a program and grade it on hidden data drawn from the same stated physics.
  Tuning thresholds against the graded scans, which is how every probe agent passed the earlier
  version, stops being possible.
- Vary the hidden data along an axis the development data cannot cover. Each hidden scan came from
  a different simulated sensor unit with its own calibration captures, so constants fitted on the
  dev unit score 0.391 recall, and the cross scan self calibration the agents had used (fitting on
  a hundred strong targets across all scans) is unavailable when a run sees one scan.
- State a scene bound the instrument cannot resolve on its own, so a second physical observable has
  to be brought in: radial velocities past the waveform's unambiguous span forced the solver to use
  the reflector's range walk across the frame. Ignoring it lost every fast reflector.
- Give the run the real system's compute budget (20 s per frame on one CPU, about seven times what
  the reference needs). That rules out the brute force time domain searches one agent ran for 300 s
  a scan without ruling out good engineering.

Keep every one of them in the instruction, with the numbers that make each decidable, so the
specification completeness check has nothing to catch.

### A second verifier shape: set matching

When the answer is a set of items (detections, objects, events) rather than a time series, the
shape that held up is: pair rows to truth one to one per group with
`scipy.optimize.linear_sum_assignment`, allow a pair only inside per dimension gates, then grade
recall, unpaired rows and one accuracy metric over the pairs. Drop accuracy metrics the gates
already enforce, since keeping them only punishes precision details the review objects to. State
the gates in the instruction so the contract is unambiguous, and make each remaining metric fail
for a different broken solver.

## Lessons from the vehicle-ekf-fusion quality review (failed, 2026-09-11)

Passed structure and AI check, then failed the agentic quality review on these blocking criteria.
Treat each as a hard rule from now on.

- difficult and novel (both failed): a loosely coupled GNSS/INS EKF is standard course and MOOC
  material with public implementations, so it reads as cookbook no matter how carefully it is
  tuned. The reviewer also writes its own quick, structurally different solver (theirs was a
  batch dead reckoning plus rolling median heuristic in a few minutes) and if that clears the bars
  the task fails. So pick a problem where no single standard recipe solves it, where several
  independent pieces of practitioner judgement all have to be right, and before finalizing
  thresholds build your own "clever shortcut" baseline (not just ablations of the reference) and
  confirm it fails. Bars were far too lenient there (oracle at 2.78 m against a 6.0 m bar); put the
  bar close to what a correct method achieves, with margin set from a second independent correct
  implementation, not a multiple of the oracle's score. Difficulty you hit while debugging your
  own first pass is not evidence the problem is hard.
- ctrf_reporting: the report must be written to `/logs/verifier/ctrf.json` exactly
  (`pytest --ctrf /logs/verifier/ctrf.json ...`), not `ctrf-report.json`.
- instruction_clarity: no narrative or motivation ("similar to driving through a tunnel", "which
  is what you would be handed for a job like this"), no approach hints ("a Kalman filter is the
  obvious tool"), no closing paragraph about which naive methods will fail. State inputs, the
  exact output contract and what is graded, nothing else. The deliberate typos were also cited
  here, so use at most one, in plain prose only.
- verification_explanation: every number in README and toml must match the evidence exactly (the
  "four to twelve times worse" claim was false for one variant at 1.7x). Calibrate against an
  independent correct implementation as well as the reference and its ablations, and ship the
  ablation and baseline scripts in `authoring/evidence/` so the numbers can be re run, not a prose
  log alone.
- resource_configuration: `[agent].timeout_sec` must be at most 18000 (the review runs
  `check-task-timeout.sh` with an 18000 s cap, stricter than the 28800 in the doc). Size
  `[verifier].timeout_sec` to the real suite runtime (a few hundred seconds, not 1800).
- task_toml_schema: the reviewer wanted `[task].name` as `<benchmark>/<slug>` (dataset name was
  redacted in the report) and flagged `category`, `subcategory` and the three `*_explanation` keys
  as outside its expected `[metadata]` set. Both contradict `Authoring tasks.md`, which the
  structure check enforces, so keep following the doc and raise the conflict with AfterQuery
  rather than silently changing it.

- Second review (streaming version, same day): every difficulty and verifier criterion passed,
  but four blocking criteria failed because instruction.md still described the older CSV-output
  version. After any redesign, rewrite the instruction from the test code itself (test_verify.py,
  harness, scoring) and check every path it names exists in the image. When the artifact is a
  program, the instruction must spell out the full execution contract: artifact path, how it is
  launched, the input message grammar and ordering, the answer line format and tolerance, what
  must not go to stdout, the runtime (user, cwd, packages, no network, CPU, per run time limit),
  and exact metric definitions including masks (outage definition, speed threshold).

Advisory points from the same review, cheap to get right: no unused apt packages in
`tests/Dockerfile` (curl, build-essential were flagged); every difficulty claim must actually
bite on the shipped data (a reacquisition rule that never fires is overstated); every graded
metric should discriminate on its own; tags must match the task (localization is not
perception); the task name should not name a method the instruction says is optional.

## Local validation without Docker available

If `docker` is not on PATH in the working environment, `harbor run` and `harbor check` cannot be
run directly. Get as far as possible without them before asking the user to run the real gates:
1. Prototype the data generator and the reference solution as plain Python outside any container,
   using whatever numpy/pandas/scipy are available locally (`pip install` them if missing).
2. Score the reference solution and every weakened variant against the sealed ground truth using
   the exact same metric code the verifier will run, to lock in thresholds with real margins.
3. Copy that verifier logic into `tests/test_verify.py`, then sanity run it locally with pytest by
   pointing its path constants at a scratch directory standing in for `/app/output` and `/tests`
   (do this in a scratch copy, never edit the real path constants in the bundle). Confirm it passes
   on the oracle's output and fails (non-zero exit, not a silent pass) on a missing or clearly bad
   output, matching the nop and low quality attempt cases.
4. Hand the user the exact commands to finish validation where Docker is available:
   `harbor run -p . -a oracle -e docker`, `harbor run -p . -a nop -e docker`,
   `harbor check . -m anthropic/claude-opus-4-8`, run from the task directory.
5. Install the verifier's own pins locally (`pip install pytest==8.4.1 pytest-json-ctrf==0.3.5`)
   so the scratch run uses the exact `--ctrf /logs/verifier/ctrf.json` invocation from test.sh. A
   missing plugin surfaces as pytest exit 4 with "unrecognized arguments: --ctrf", which is a
   local gap, not a verifier bug.
6. Run the verifier on the oracle output three times and confirm it passes every time, then check
   the failure cases explicitly: missing artifact, header only file, non numeric or non finite
   values, and the shortcut baseline's output. Each must exit non zero rather than pass quietly.
7. When the verifier executes an agent program rather than reading a file, also run it against
   hostile ones: no program at all, a program that prints something other than the answer format,
   and a program that sleeps past the per unit time limit. Each must score 0, and the sleeping one
   proves the harness actually kills it. Then size `[verifier].timeout_sec` from the worst case
   (units x per unit limit, 24 x 20 s here) rather than from the oracle's runtime.

## Packaging, zipping and resubmission

- Build the zip with Python `zipfile`, never PowerShell 5.1 `Compress-Archive`, which writes
  backslash separators that break extraction on Linux. The bundle contents go at the zip root
  (`instruction.md` at the top level, no wrapper folder) with forward slash paths.
- Exclude `jobs/`, `__pycache__` and every `.pyc`. Harbor's local `jobs/` output and the pyc files
  embed this machine's path, which contains "Task Afterquery\Project Kepler", and the structure
  check blocks the words "afterquery" and "kepler" anywhere in the bundle. The
  `name = "afterquery/<slug>"` line in task.toml is the one accepted occurrence.
- Verify the zip itself, not only the folder: extract it to a scratch directory, run the oracle
  and the nop from the extracted copy, and check mechanically that no member has CRLF, the
  instruction ends with the exact suffix, the required files are present, there are no unexpected
  top level entries and `testzip()` is clean.
- A resubmission must keep the task name already on file, so do not rename the slug between
  submissions. Renaming internal files (the output CSV, the truth file) is fine.
- After any edit by another assistant or editor, re run the whole check: CRLF scan, path
  consistency across instruction, task.toml `artifacts`, verifier and solve.sh, regeneration from
  the seed compared byte for byte, oracle plus bad output runs, and the evidence rerun. The Gemini
  rename pass on `ddma-radar-targets` was logically correct but saved 16 files as CRLF, which
  would have broken solve.sh and test.sh inside the Linux containers.

### Reading pipeline failures

Not every red trial is a task defect. The anti cheat probe deliberately instructs an agent to
cheat the verifier, so a trial that ends in a model safeguard refusal (a `[cyber]` flag) with
reward 0 is the probe failing to cheat, which is the outcome the task wants. Read `task_name`,
`trial_name` and the reward before changing anything.

This refusal has now happened on two different tasks. The trigger is the probe agent's own sweep
for hidden grading files (`find / -iname '*truth*'` and similar), which the safety classifier reads
as cyber activity; harbor then string matches "API Error" and files it as `UnknownApiError`, an
infra class. Neither is a bundle defect: report it, ask for a rerun, and point out the
misclassification. Likewise `harbor check` failing with "Not logged in" is container auth on this
machine, not a bundle problem.

A job level probe summary (`n_total_trials`, `pass_at_k`, `reward_stats`) does not name the task it
ran on. When more than one submission is in flight, ask which task it belongs to instead of
inferring from timestamps; the remedy differs completely between tasks.

## Author metadata

Never fabricate `author_name`, `author_organization`, `author_profile`, or `relevant_experience`.
Ask the user for these directly if they have not been given, and ask what part of their real
background is relevant to the specific task before writing `relevant_experience`, rather than
reusing a generic bio verbatim.
