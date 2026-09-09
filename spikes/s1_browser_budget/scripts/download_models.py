"""Download the fp32 and int8 ONNX files for the pre-converted candidate models.

Standalone spike script. Run with:

    uv run --python 3.11 --with-requirements requirements.txt python \
        scripts/download_models.py

Fetches only the files transformers.js needs (config, tokenizer, fp32 and
int8 ONNX weights), skipping the other quantization variants (fp16, q4,
q4f16, bnb4, uint8) those repos also carry, to avoid downloading weights
this spike does not use.
"""

from pathlib import Path

from huggingface_hub import hf_hub_download

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

REPOS = {
    "xenova-bert-base-chinese": "Xenova/bert-base-chinese",
    "xenova-mbert-ner-hrl": "Xenova/bert-base-multilingual-cased-ner-hrl",
    # Added after ckiplab/albert-tiny-chinese-ner turned out unsupported by
    # transformers.js (see RESULTS.md), to keep a size point in the 10-20 MiB
    # int8 range once that data point dropped out of the main matrix.
    "xenova-paraphrase-minilm-l3": "Xenova/paraphrase-MiniLM-L3-v2",
}

FILES = [
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.txt",
    "onnx/model.onnx",
    "onnx/model_quantized.onnx",
]


def main() -> int:
    for local_name, repo_id in REPOS.items():
        dest = MODELS_DIR / local_name
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "onnx").mkdir(exist_ok=True)
        print(f"--- {repo_id} -> {dest} ---")
        for filename in FILES:
            try:
                path = hf_hub_download(repo_id=repo_id, filename=filename, local_dir=str(dest))
                size_mb = Path(path).stat().st_size / (1024 * 1024)
                print(f"  {filename}: {size_mb:.2f} MiB")
            except Exception as exc:  # noqa: BLE001 - spike script, report and continue
                print(f"  {filename}: FAILED - {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
