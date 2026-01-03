#!/usr/bin/env python3
"""
Merge LoRA Adapter med Base Model
=================================
Mergar LoRA-vikter med basmodellen för Ollama-export.

Användning:
    python scripts/merge_lora.py

Output:
    ./models/qwen-workflow-merged/ - Full modell för Ollama
"""

import torch
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# Paths
LORA_PATH = "./models/qwen-workflow-lora"
OUTPUT_PATH = "./models/qwen-workflow-merged"
BASE_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"


def main():
    print("=" * 60)
    print("LoRA Merge för Ollama Export")
    print("=" * 60)

    if not Path(LORA_PATH).exists():
        print(f"ERROR: LoRA adapter not found at {LORA_PATH}")
        print("Run scripts/finetune_lora.py first")
        return

    print(f"Loading base model: {BASE_MODEL}")
    print("This may take a few minutes...")

    # Load base model (full precision for merging)
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )

    print(f"Loading LoRA adapter from {LORA_PATH}")
    model = PeftModel.from_pretrained(base_model, LORA_PATH)

    print("Merging weights...")
    model = model.merge_and_unload()

    print(f"Saving merged model to {OUTPUT_PATH}")
    Path(OUTPUT_PATH).mkdir(parents=True, exist_ok=True)

    model.save_pretrained(OUTPUT_PATH)

    # Copy tokenizer
    tokenizer = AutoTokenizer.from_pretrained(LORA_PATH)
    tokenizer.save_pretrained(OUTPUT_PATH)

    print("\n" + "=" * 60)
    print("Merge complete!")
    print(f"Merged model saved to: {OUTPUT_PATH}")
    print("\nTo use with Ollama:")
    print("1. Convert to GGUF format (requires llama.cpp):")
    print(f"   python llama.cpp/convert_hf_to_gguf.py {OUTPUT_PATH} --outfile qwen-workflow.gguf")
    print("2. Create Modelfile:")
    print("   FROM qwen-workflow.gguf")
    print("   SYSTEM \"Du är expert på n8n automation...\"")
    print("3. ollama create qwen-workflow -f Modelfile")
    print("=" * 60)


if __name__ == "__main__":
    main()
