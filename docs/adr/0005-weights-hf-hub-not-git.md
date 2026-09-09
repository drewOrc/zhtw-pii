# 0005: Model weights on HF Hub and GitHub Releases, not in git

## Context

Trained weights and their ONNX exports are large binary files that do not
diff well. Committing them to git history would make every clone slow and
would make the repository grow without bound across training iterations.

## Decision

Weights are published to the Hugging Face Hub as the primary distribution
point, with the int8 ONNX export mirrored as a GitHub Release asset so the
browser demo has a stable, CORS-friendly URL to load from. Nothing under
`*.onnx`, `*.safetensors`, `*.bin`, or `*.pt` is committed to git (enforced
by `.gitignore`, and by a CI artifact guard once CI exists).

## Consequences

`git clone` stays fast no matter how many training runs happen. The
tradeoff is an extra release step: exporting and uploading weights is a
manual or scripted action outside `git push`, not something `git log`
shows by itself.
