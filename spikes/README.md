# Spikes

Time-boxed feasibility experiments. Each spike lives in its own directory with its own
dependencies (`package.json` and/or a local `requirements.txt`), records the exact commands
and versions used, and ends with a `RESULTS.md` that feeds a milestone decision document
under `docs/decisions/`.

Spike code is excluded from the root lint and test configuration on purpose: it is
throwaway by design and depends on heavy packages (PyTorch, ONNX export tooling, a headless
browser) that do not belong in the library environment. Reproducibility is still required:
a stranger must be able to rerun a spike from its README.

| Spike | Question | Status |
|---|---|---|
| `s1_browser_budget` | How large a model can a phone browser load in 3 s and run under 100 ms p95? | done: the ~22.5 MiB WASM runtime, not the model, dominates mobile cold load (fetched fresh every visit; ~18 s alone on 4G before any model bytes); measured data brackets a ~15 MB int8 threshold for a 30 s/4G first load (11.11 MB clears it at 29.2 s, 16.64 MB misses at 34.0 s), and the same two points also clear/miss the p95<=100 ms bar (99-170 MB models miss both); mobile-fast3g is not achievable as a load-time gate at any size tested (see `s1_browser_budget/RESULTS.md`) |
| `s2_tokenizer_parity` | Does transformers.js tokenize Traditional Chinese identically to the Python tokenizer? | done: input_ids parity is perfect (100%, 5 tokenizers x 338 examples), but transformers.js exposes no character offsets at all, so span reconstruction is required; it is ~100% accurate for WordPiece backbones and needs an extra NFKC-normalization step to reach ~95-99% for SentencePiece (see `s2_tokenizer_parity/RESULTS.md`) |
