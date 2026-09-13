"""RKNN export for RK3588 NPU.

ONNX -> RKNN via RKNN Toolkit2. INT8 quantization is NOT default.
Run this on a Linux host with RKNN Toolkit2 installed (not Windows).
"""
from __future__ import annotations

import argparse
from pathlib import Path


def export_rknn(onnx_path: str, output_path: str,
                quantize: str = "fp16", calibration_samples: int = 500):
    """Convert ONNX to RKNN.

    quantize: 'fp32', 'fp16', or 'int8'
    INT8 requires calibration data and must be compared against FP16.
    """
    try:
        from rknn.api import RKNN
    except ImportError:
        print("[RKNN] RKNN Toolkit2 not installed. Install on Linux build host.")
        print("  pip install rknn-toolkit2")
        return None

    rknn = RKNN(verbose=True)

    # Config
    rknn.config(
        mean_values=[[0]],
        std_values=[[1]],
        target_platform="rk3588",
    )

    # Load ONNX
    ret = rknn.load_onnx(model=onnx_path)
    if ret != 0:
        print(f"[RKNN] Failed to load ONNX: {onnx_path}")
        return None

    # Build (quantization)
    if quantize == "int8":
        print(f"[RKNN] INT8 quantization with {calibration_samples} samples")
        # TODO: provide calibration dataset
        ret = rknn.build(do_quantization=True, dataset="calibration.txt")
    else:
        do_quant = (quantize == "fp16")
        ret = rknn.build(do_quantization=do_quant)

    if ret != 0:
        print("[RKNN] Build failed")
        return None

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ret = rknn.export_rknn(str(out_path))
    if ret != 0:
        print("[RKNN] Export failed")
        return None

    print(f"[RKNN] Exported to {out_path} (quant={quantize})")
    rknn.release()
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--onnx", default="deployment/onnx/policy.onnx")
    parser.add_argument("--output", default="deployment/rk3588/policy.rknn")
    parser.add_argument("--quantize", choices=["fp32", "fp16", "int8"], default="fp16")
    args = parser.parse_args()
    export_rknn(args.onnx, args.output, args.quantize)


if __name__ == "__main__":
    main()
