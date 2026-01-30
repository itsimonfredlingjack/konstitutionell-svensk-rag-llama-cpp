import json
import os
from pathlib import Path

def prepare_dataset(root_dir: str, output_file: str):
    root_path = Path(root_dir)
    with open(output_file, 'w', encoding='utf-8') as f_out:
        for file_path in root_path.rglob('*.py'):
            if 'venv' in str(file_path) or 'finetune' in str(file_path):
                continue
                
            try:
                content = file_path.read_text(encoding='utf-8')
                # Format as a "document" for the model to learn
                # Including the path helps the model understand project structure
                relative_path = file_path.relative_to(root_path.parent)
                entry = {
                    "text": f"# File: {relative_path}\n\n{content}\n<|endoftext|>"
                }
                f_out.write(json.dumps(entry) + "\n")
            except Exception as e:
                print(f"Skipping {file_path}: {e}")

if __name__ == "__main__":
    # Assuming we run this from vibe-cli/finetune
    project_root = Path(__file__).parent.parent
    prepare_dataset(str(project_root), "dataset.jsonl")
    print(f"Dataset created at dataset.jsonl")
