#!/usr/bin/env python3
"""
LoRA Fine-Tuning Script för Qwen2.5-Coder
=========================================
Tränar en LoRA-adapter på n8n workflow-data för bättre
förståelse av automation och integrations-patterns.

Krav:
- PyTorch med CUDA
- transformers, peft, bitsandbytes, accelerate
- 12GB+ VRAM (RTX 4070)

Användning:
    python scripts/finetune_lora.py

Output:
    ./models/qwen-workflow-lora/ - LoRA adapter att merga med Ollama
"""

import os
import json
import torch
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# Check CUDA availability
print("=" * 60)
print("LoRA Fine-Tuning för Qwen2.5-Coder")
print("=" * 60)
print(f"PyTorch version: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
print("=" * 60)


@dataclass
class TrainingConfig:
    """Training configuration"""
    # Model
    base_model: str = "Qwen/Qwen2.5-Coder-7B-Instruct"  # Mindre för 12GB VRAM

    # LoRA parameters
    lora_r: int = 32  # Rank (högre = mer kapacitet, mer VRAM)
    lora_alpha: int = 64
    lora_dropout: float = 0.05
    target_modules: tuple = ("q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj")

    # Training
    num_epochs: int = 3
    batch_size: int = 1  # Litet för 12GB VRAM
    gradient_accumulation_steps: int = 8
    learning_rate: float = 2e-4
    max_seq_length: int = 2048

    # Output
    output_dir: str = "./models/qwen-workflow-lora"

    # Data
    training_data: str = "./data/training_data.jsonl"


def load_training_data(path: str) -> list[dict]:
    """Ladda JSONL training data"""
    data = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    print(f"Loaded {len(data)} training examples")
    return data


def format_for_training(examples: list[dict]) -> list[dict]:
    """
    Konvertera till Qwen chat-format:
    <|im_start|>system
    {system}
    <|im_end|>
    <|im_start|>user
    {instruction}
    <|im_end|>
    <|im_start|>assistant
    {output}
    <|im_end|>
    """
    formatted = []

    system_prompt = (
        "Du är en expert på n8n automation och workflow-design. "
        "Du hjälper till att skapa, förklara och optimera n8n workflows. "
        "Svara alltid på svenska."
    )

    for ex in examples:
        text = (
            f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
            f"<|im_start|>user\n{ex['instruction']}<|im_end|>\n"
            f"<|im_start|>assistant\n{ex['output']}<|im_end|>"
        )
        formatted.append({"text": text})

    return formatted


def main():
    config = TrainingConfig()

    # Check if training data exists
    if not Path(config.training_data).exists():
        print(f"ERROR: Training data not found at {config.training_data}")
        print("Run scripts/convert_workflows_to_training.py first")
        return

    # Load and format data
    raw_data = load_training_data(config.training_data)
    formatted_data = format_for_training(raw_data)

    print(f"\nFormatted {len(formatted_data)} examples for training")
    print(f"Sample (first 500 chars):\n{formatted_data[0]['text'][:500]}...")

    # Check VRAM requirements
    if not torch.cuda.is_available():
        print("\nERROR: CUDA not available. LoRA training requires GPU.")
        print("Install: pip install torch --index-url https://download.pytorch.org/whl/cu121")
        return

    vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
    if vram_gb < 10:
        print(f"\nWARNING: Only {vram_gb:.1f}GB VRAM detected.")
        print("Switching to 4-bit quantization and smaller model...")
        config.base_model = "Qwen/Qwen2.5-Coder-1.5B-Instruct"  # Fallback to smaller

    # Import heavy libraries only when needed
    print("\nLoading libraries...")
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        TrainingArguments,
        Trainer,
        DataCollatorForLanguageModeling,
        BitsAndBytesConfig
    )
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from datasets import Dataset

    # BitsAndBytes 4-bit config för att spara VRAM
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    print(f"\nLoading base model: {config.base_model}")
    print("This may take a few minutes...")

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        config.base_model,
        trust_remote_code=True
    )
    tokenizer.pad_token = tokenizer.eos_token

    # Load model with 4-bit quantization
    model = AutoModelForCausalLM.from_pretrained(
        config.base_model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

    # Prepare for k-bit training
    model = prepare_model_for_kbit_training(model)

    # Configure LoRA
    lora_config = LoraConfig(
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        target_modules=list(config.target_modules),
        lora_dropout=config.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
    )

    # Apply LoRA
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Prepare dataset
    def tokenize(example):
        result = tokenizer(
            example["text"],
            truncation=True,
            max_length=config.max_seq_length,
            padding="max_length",
        )
        result["labels"] = result["input_ids"].copy()
        return result

    dataset = Dataset.from_list(formatted_data)
    tokenized_dataset = dataset.map(tokenize, remove_columns=["text"])

    print(f"\nDataset size: {len(tokenized_dataset)}")

    # Training arguments
    training_args = TrainingArguments(
        output_dir=config.output_dir,
        num_train_epochs=config.num_epochs,
        per_device_train_batch_size=config.batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        learning_rate=config.learning_rate,
        warmup_ratio=0.1,
        logging_steps=1,
        save_strategy="epoch",
        fp16=True,  # Mixed precision
        optim="paged_adamw_8bit",  # Efficient optimizer
        report_to="none",  # No wandb etc
    )

    # Data collator
    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False,  # Causal LM, not masked
    )

    # Create trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
        data_collator=data_collator,
    )

    print("\n" + "=" * 60)
    print("Starting LoRA training...")
    print(f"Epochs: {config.num_epochs}")
    print(f"Batch size: {config.batch_size} x {config.gradient_accumulation_steps} = {config.batch_size * config.gradient_accumulation_steps}")
    print(f"Learning rate: {config.learning_rate}")
    print(f"LoRA rank: {config.lora_r}")
    print("=" * 60 + "\n")

    # Train!
    trainer.train()

    # Save LoRA adapter
    print(f"\nSaving LoRA adapter to {config.output_dir}")
    model.save_pretrained(config.output_dir)
    tokenizer.save_pretrained(config.output_dir)

    print("\n" + "=" * 60)
    print("Training complete!")
    print(f"LoRA adapter saved to: {config.output_dir}")
    print("\nNext steps:")
    print("1. Merge adapter with base model for Ollama:")
    print("   python scripts/merge_lora.py")
    print("2. Create Ollama Modelfile with merged weights")
    print("3. Test with: ollama run qwen-workflow")
    print("=" * 60)


if __name__ == "__main__":
    main()
