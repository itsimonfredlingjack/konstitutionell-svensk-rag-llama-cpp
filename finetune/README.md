# Fine-Tuning Granite 3.1 2B for Vibe-CLI

This directory contains scripts to fine-tune the `ibm-granite/granite-3.1-2b-instruct` model on the `vibe-cli` codebase.

## Prerequisites

- Python 3.10+
- A GPU with at least 8GB VRAM (NVIDIA recommended for bitsandbytes 4-bit quantization)
- **Note for AMD Users**: The training script uses `bitsandbytes` for 4-bit quantization, which primarily supports NVIDIA CUDA. On an AMD iGPU, this may default to CPU or fail. Consider using a cloud GPU (Colab, RunPod) or looking into ROCm-compatible forks.

## Setup

```bash
pip install torch transformers peft bitsandbytes datasets trl accelerate
```

## Steps

1.  **Prepare the Dataset**:
    Run the preparation script to scan your `vibe-cli` code and create a JSONL file.
    ```bash
    python prepare_data.py
    ```

2.  **Run Training**:
    Start the QLoRA fine-tuning process.
    ```bash
    python train.py
    ```

3.  **Merge and Export**:
    After training, you will have LoRA adapters in `granite-vibe-cli-lora`. You can merge these back into the base model or load them at runtime.
