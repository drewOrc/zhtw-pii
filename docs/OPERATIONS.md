# Operations

This is the exit-path and secrets reference for zhtw-pii: how to undo a bad
change, and where the one credential this project uses lives. It is short
on purpose; expand it when a real incident shows a gap, not in advance.

## Rollback

zhtw-pii is an L2 project (public, other people clone it and read it, but
it does not process real data), so rollback is lighter than an L3
production system, but the path is still written down rather than
improvised under pressure.

- **Code on `main`**: `main` is branch-protected (PRs only, required
  checks, no force-push). To undo a bad merge, open a `git revert` PR
  against the offending commit(s) and let it go through the normal
  CI-gated PR flow. Do not force-push or hard-reset a protected branch.
- **Releases**: a bad tagged release is not deleted or moved. Fix forward
  with a new tag (for example `v0.3.1` after `v0.3.0`, or `v1.0.1` after
  `v1.0.0`). Consumers pinned to the old tag are unaffected; the release
  notes for the new tag should say what changed and why.
- **Model weights** (from M3 onward): published to the Hugging Face Hub,
  which is itself versioned. The GitHub Release asset mirror (see
  `docs/adr/0005-weights-hf-hub-not-git.md`) is tied to a specific tag.
  Rolling back means pointing the demo's manifest at the previous weight
  version, not deleting the new one.
- **GitHub Pages demo** (from M2 onward): rebuilt from `main` on every push
  that touches `demo/**`. Reverting the `main` commit that broke the demo
  and letting `pages.yml` rebuild is the rollback; there is no separate
  deploy state to reset.

## Test set versioning

`data/testset/v0/test.jsonl` is frozen once the M1 manual audit
(`data/testset/v0/AUDIT.md`) passes. "Frozen" means: benchmark numbers
that cite "v0" must always be reproducible against exactly this file.

The audit is `make audit-sample`, which writes a blank `AUDIT.md` for a
seeded sample of the committed file, followed by answering it by hand.
`make audit-check` runs in CI's `test` job and holds the freeze claim to
that record: it passes while `AUDIT.md` is missing or has no verdict, and
fails if the verdict is PASS with any question unanswered or any `disagree`
or `yes` left without a note, if anything beyond the answers differs from
the template for the committed test set (a regenerated file, a swapped row,
an edited span), or if `data/CHANGELOG.md` exists without a PASS.

If a later fix to the generator (`zhtw_pii/data/generate.py`) would change
`v0`'s output:

1. Do **not** overwrite `data/testset/v0/test.jsonl` in place. The weekly
   `reproduce.yml` run exists specifically to catch this if it happens by
   accident (see that workflow's failure-issue message).
2. Generate the new set under `data/testset/v1/` instead.
3. Record what changed and why in `data/CHANGELOG.md` (created at the same
   time as the first version bump).
4. Update any results, README table, or blog post that reports numbers
   against "v0" to say which version they used.
5. Keep `v0` in the repository and in git history, so benchmark numbers
   published against it stay reproducible.

## Secrets

- `ANTHROPIC_API_KEY` is the only credential this project uses (the LLM
  few-shot baseline in `zhtw_pii/eval/benchmark.py`). The repository's
  GitHub Actions secret (Settings > Secrets and variables > Actions) is
  already configured with it.
- For a local run, put it in a gitignored `.env` file in the repo root;
  `make benchmark` picks it up automatically by passing `--env-file` to
  `uv run` when `.env` exists (see the Makefile). It is never committed
  and never hardcoded.
- No workflow reads this secret yet. `ci.yml` (`lint`, `test`,
  `secrets-guard`, `report-check`) and `reproduce.yml` need no secrets at
  all and run the same way on a fork's pull request as they do on `main`.
  Wiring a workflow that does use it (`eval.yml`, running the full
  benchmark including the Claude Haiku baseline in CI) is a tracked
  follow-up from M1: see issue #13.
- If the key is ever accidentally committed, treat it as compromised
  immediately: rotate it at the provider, then remove it from git history
  (see the "Remove a tracked secret" procedure the team uses for every
  repository), do not just delete the file in a new commit.
