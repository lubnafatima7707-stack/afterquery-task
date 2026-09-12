# Pipeline issue: GPU tasks fail at Modal mount upload before any task code runs

## Summary

Both of my GPU tasks (`gpus = 1`, `gpu_types = ["H100"]`) fail 100 percent of trials
with `modal.exception.ExecutionError: <path> was modified during build process`,
raised inside Modal's mount upload while the agent environment is being created.
All three of my CPU tasks (`gpus = 0`) have run through the pipeline normally.

The failure happens before the agent starts, before `solution/solve.sh` runs and
before the verifier runs, and it also kills the no-change (nop) baseline, which
executes nothing at all. I do not believe this is a defect in either bundle, and I
would like a rerun once the GPU path is looked at.

## Affected tasks

| task | gpus | pipeline outcome |
|---|---|---|
| `ddma-radar-targets` | 0 | ran normally (3 difficulty probes completed) |
| `vehicle-ekf-fusion` | 0 | ran normally (full quality review completed) |
| `multi-object-tracking` | 0 | ran normally (reviewed, rebuilt, reviewed again) |
| `realtime-fusion-node` | 1 (H100) | every trial fails at mount upload |
| `gpu-batched-nms` | 1 (H100) | every trial fails at mount upload |

## The error

```
Traceback (most recent call last):
  File "/usr/local/lib/python3.13/site-packages/harbor/trial/trial.py", line 375, in run
    await self._prepare()
  File "/usr/local/lib/python3.13/site-packages/harbor/trial/trial.py", line 409, in _prepare
    await self._setup_agent_environment()
  File "/usr/local/lib/python3.13/site-packages/harbor/trial/trial.py", line 1210, in _setup_agent_environment
    await self._start_agent_environment()
  File "/usr/local/lib/python3.13/site-packages/harbor/environments/modal.py", line 1448, in start
    return await self._strategy.start(force_build)
  File "/usr/local/lib/python3.13/site-packages/harbor/environments/modal.py", line 298, in start
    env._sandbox = await env._create_sandbox(
  ...
  File "/usr/local/lib/python3.13/site-packages/modal/mount.py", line 570, in _put_file
    raise modal.exception.ExecutionError(msg)
modal.exception.ExecutionError: /work/task/environment/data/app/workloads/dev_light_truth.npz was modified during build process.
```

The log line `Selected strategy: _ModalDirect` appears at the top of every run, so
GPU tasks are taking a different environment strategy from the CPU tasks that work.

## Why this is not a task defect

1. **The nop baseline fails identically.** The no-change agent runs nothing and
   cannot modify a file, yet 3 of 3 nop trials died at the same mount step on both
   tasks. On `gpu-batched-nms` the reported result was "3 of 3 reference-solution
   runs produced no reward; 3 of 3 no-change runs produced no reward".

2. **The flagged file differs per trial, and includes files nothing writes to.**
   From the `realtime-fusion-node` probe logs, six trials flagged four different
   files:

   | job | trial | file flagged as modified |
   |---|---|---|
   | oracle | `task__jm4qRxX` | `environment/data/app/workloads/dev_light_truth.npz` |
   | oracle | `task__fRwn5cW` | `environment/data/app/tools/score_dev.py` |
   | oracle | `task__CR7rbMe` | `environment/data/app/tools/score_dev.py` |
   | nop | `task__URQbBSd` | `environment/data/app/src/pipeline.h` |
   | nop | `task__YKhmwie` | `environment/data/app/CMakeLists.txt` |
   | nop | `task__kRUzdM8` | `environment/data/app/tools/score_dev.py` |

   `CMakeLists.txt` and `pipeline.h` are static source files that nothing in the
   task ever opens for writing. On `gpu-batched-nms` the two files flagged were
   `environment/nms_kernel.py` and `environment/data/dev_busy.npz`.

3. **It is deterministic, not a flaky race.** Each trial retried (12 occurrences of
   the error across 3 trials per job, so roughly 4 attempts each) and failed every
   attempt.

4. **It does not track mount size or file count.** If anything the correlation runs
   backwards:

   | task | `environment/` files | `environment/` bytes | outcome |
   |---|---|---|---|
   | `ddma-radar-targets` | 11 | 4,199,479 | works |
   | `vehicle-ekf-fusion` | 13 | 1,829,020 | works |
   | `multi-object-tracking` | 3 | 840,467 | works |
   | `realtime-fusion-node` | 19 | 98,900 | fails |
   | `gpu-batched-nms` | 4 | 30,533 | fails |

   `gpu-batched-nms` ships a 30 KB environment of four files and still fails every
   time. There is no plausible window in which those files could be modified during
   an upload that size.

5. **Local checks on the bundle are clean.** No file in the bundle has a future
   dated or otherwise anomalous mtime, there are no symlinks, no `__pycache__`, no
   CRLF, and the zip passes `testzip()` with forward slash paths and no wrapper
   directory. The oracle solution passes accuracy on all eight dev and hidden
   workloads on a local GPU, and has additionally been run from a freshly extracted
   copy of the submitted zip through the verifier's own harness, where it passes
   both the accuracy and the timing check.

## Two questions I could not answer from the authoring doc

1. **Is `validate_env` now required when `gpus = 1`?** Two consecutive quality
   reviews of `gpu-batched-nms` flagged, as advisory, that "validate_env is not set
   even though gpus = 1 makes it required for CI validation off the GPU-less
   runner". The string `validate_env` does not appear anywhere in `Authoring
   tasks.md` (the copy I have is dated 11 Sep), and the `[environment]` template
   there documents only `gpus` and `gpu_types` for GPU tasks. If this key is now
   required, could the doc be updated with its expected shape? I would rather set it
   correctly than guess.

2. **How should a GPU be requested for a `separate` verifier environment?** The
   documented `[verifier.environment]` block lists only `network_mode`.
   `gpu-batched-nms` needs a GPU in the verifier as well as the agent environment,
   because the deadline check times the submitted CUDA kernel against a sealed
   reference kernel live on the grading hardware rather than against a fixed
   constant. I have currently set `gpus = 1` and `gpu_types = ["H100"]` under
   `[verifier.environment]` on that basis. If that is not the supported way to do
   it, please tell me what is; I have left it in place rather than removing it,
   since dropping it would leave the verifier without the GPU it needs. Note this
   is not the cause of the failure above, since `realtime-fusion-node` does not set
   it and fails in exactly the same way.

## What I am asking for

- A look at the `_ModalDirect` GPU environment path for this mount check.
- A rerun of `realtime-fusion-node` and `gpu-batched-nms` once it is addressed.
- Confirmation on the two configuration questions above.

Full probe logs for `realtime-fusion-node` (`job_oracle.log`, `job_nop.log`) are
available on request, and I can attach the `gpu-batched-nms` run log if the
pipeline retains it.
