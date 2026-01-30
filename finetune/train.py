import torch
from datasets import load_dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
)
from trl import SFTTrainer, SFTConfig

# Configuration
MODEL_NAME = "ibm-granite/granite-3.1-2b-instruct"
OUTPUT_DIR = "granite-vibe-cli-lora"
DATASET_FILE = "dataset.jsonl"

def train():
    print(f"Loading model: {MODEL_NAME}")
    
    # 1. Quantization Config (4-bit QLoRA) for 16GB RAM efficiency
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    # 2. Load Model
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        quantization_config=bnb_config,
        device_map="auto",
        attn_implementation="flash_attention_2" if torch.cuda.is_available() and torch.cuda.get_device_capability()[0] >= 8 else "eager"
    )
    
    # Enable gradient checkpointing to save memory
    model.gradient_checkpointing_enable()
    model = prepare_model_for_kbit_training(model)

    # 3. Load Tokenizer
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    tokenizer.pad_token = tokenizer.eos_token

    # 4. LoRA Config
    peft_config = LoraConfig(
        r=16,                    # Rank
        lora_alpha=32,           # Scaling factor
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules="all-linear" # Target all linear layers for best performance
    )

    # 5. Load Dataset
    dataset = load_dataset("json", data_files=DATASET_FILE, split="train")

    # 6. Training Arguments
    args = SFTConfig(
        output_dir=OUTPUT_DIR,
        num_train_epochs=3,
        per_device_train_batch_size=1,      # Low batch size for VRAM
        gradient_accumulation_steps=4,      # Accumulate to simulate batch_size=4
        learning_rate=2e-4,
        logging_steps=10,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        max_seq_length=2048,                # Context window
        dataset_text_field="text",
        packing=False,                      # Set to True if dataset is large and you want to pack sequences
    )

    # 7. Trainer
    trainer = SFTTrainer(
        model=model,
        args=args,
        train_dataset=dataset,
        peft_config=peft_config,
    )

    print("Starting training...")
    trainer.train()
    
    print(f"Saving model to {OUTPUT_DIR}")
    trainer.save_model()

if __name__ == "__main__":
    train()
