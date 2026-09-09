"""Dynamic int8 quantization for an exported ONNX model.

Standalone spike script, not part of the zhtw-pii package. Run with:

    uv run --python 3.11 --with-requirements requirements.txt python \
        scripts/quantize_dynamic_int8.py <model_dir>

Reads <model_dir>/model.onnx and writes <model_dir>/model_quantized.onnx
next to it using onnxruntime's dynamic quantization (weights-only int8,
QOperator format), the same conversion transformers.js expects to find at
onnx/model_quantized.onnx.
"""

import argparse
import sys
from pathlib import Path

from onnxruntime.quantization import QuantType, quantize_dynamic


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_dir", type=Path, help="Directory containing model.onnx")
    args = parser.parse_args()

    src = args.model_dir / "model.onnx"
    dst = args.model_dir / "model_quantized.onnx"
    if not src.exists():
        print(f"error: {src} does not exist", file=sys.stderr)
        return 1

    quantize_dynamic(
        model_input=str(src),
        model_output=str(dst),
        weight_type=QuantType.QInt8,
    )

    src_mb = src.stat().st_size / (1024 * 1024)
    dst_mb = dst.stat().st_size / (1024 * 1024)
    print(f"{src.name}: {src_mb:.2f} MiB -> {dst.name}: {dst_mb:.2f} MiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
