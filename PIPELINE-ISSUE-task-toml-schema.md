# Pipeline issue: task.toml schema review contradicts the authoring documentation

## Summary

Two quality reviews, on two different tasks, have now failed the
`task_toml_schema` criterion (advisory in the second case) for following
`Authoring tasks.md` exactly. I would rather be told which document wins than
keep guessing, because the structure check at submit time and the agentic review
afterwards appear to want different files.

## What the reviews said

`vehicle-ekf-fusion` (10 Sep) and `ecu-nvm-store` (13 Sep, twice) were flagged for:

1. **`[task].name`.** The review wants `<benchmark>/<slug>`, with the benchmark
   name redacted in the report I receive, and reads `afterquery/<slug>` as wrong.
   `Authoring tasks.md` says, in two places, that `[task].name` must be
   `afterquery/<your-task-slug>` where the slug equals the task name submitted,
   and the structure check at submit time accepts exactly that. The blocked words
   rule in the same document also names `afterquery` in `task.toml` as the one
   accepted occurrence in the whole bundle, which only makes sense if that is the
   expected prefix.

2. **`[metadata]` fields outside the expected set.** The review flags
   `category = "Science"`, `subcategory`, and the three explanation fields
   (`difficulty_explanation`, `solution_explanation`, `verification_explanation`)
   as not belonging, with the explanations said to belong in `README.md` instead.
   The most recent review is explicit about the reasoning: it says this benchmark
   "intentionally uses domain/field/subfield instead" of `category` and
   `subcategory`, and notes that the three explanations are also present in
   `README.md`, which is exactly what the documented bundle layout asks for.
   `Authoring tasks.md` lists every one of those as required, says to keep
   `category` at exactly `Science` and to set `subcategory` to the field's display
   name, and says reviewers read the three explanations first. The second review
   also noted the explanations are duplicated in `README.md`, which is what the
   documented bundle layout asks for: `README.md` carries Difficulty, Reference
   solution and Verification sections.

## What I have done

Both tasks follow `Authoring tasks.md`, since that is what the structure check
enforces and a bundle that fails it never reaches the pipeline. I have not
silently changed either field to match the review.

## What I am asking for

- Which document is authoritative for `[task].name` on this dataset, and what the
  prefix should be if it is not `afterquery`.
- Whether `category`, `subcategory` and the three `*_explanation` keys should stay
  in `[metadata]` or move, and if they move, where the structure check expects
  them.
- If the review's expectation is the correct one, an update to
  `Authoring tasks.md` so the two agree, or a note in the review output that the
  criterion is advisory and the documented form is accepted.

Happy to resubmit either bundle in whichever form is wanted; the change is a few
lines in `task.toml`.
