#!/usr/bin/env python3
"""Generate 1.8M Q&A pairs from DiVA abstracts for SFT training."""

import json
import re
from pathlib import Path


def strip_html(text):
    """Remove HTML tags from text."""
    return re.sub(r"<[^>]+>", "", text).strip()


def generate_qa_pairs(title, abstract):
    """Generate 3 Q&A variants from title + abstract."""
    abstract_clean = strip_html(abstract)
    if len(abstract_clean) < 30:
        return []

    return [
        {"instruction": f"Vad handlar '{title}' om?", "input": "", "output": abstract_clean},
        {"instruction": "Sammanfatta följande arbete:", "input": title, "output": abstract_clean},
        {
            "instruction": "Beskriv innehållet i detta akademiska arbete:",
            "input": title,
            "output": abstract_clean,
        },
    ]


# Main execution
diva_dir = Path("./data")
output_file = Path("./data/prompt-training-viking/diva_enhanced_qa.jsonl")
output_file.parent.mkdir(parents=True, exist_ok=True)

total_pairs = 0
processed_files = 0
skipped_no_abstract = 0

print("🔄 Processing DiVA files...")
with open(output_file, "w", encoding="utf-8") as out:
    for diva_file in sorted(diva_dir.glob("diva_full_*.json")):
        try:
            with open(diva_file, encoding="utf-8") as f:
                data = json.load(f)

            # Handle both dict and list formats
            records = data if isinstance(data, list) else data.get("records", [])
            if not records:
                continue

            file_pairs = 0
            for record in records:
                if (
                    not isinstance(record, dict)
                    or "abstract" not in record
                    or not record["abstract"]
                ):
                    skipped_no_abstract += 1
                    continue

                title = record.get("title", "Untitled")
                abstract = record["abstract"]

                for qa in generate_qa_pairs(title, abstract):
                    out.write(json.dumps(qa, ensure_ascii=False) + "\n")
                    file_pairs += 1

            total_pairs += file_pairs
            processed_files += 1
            print(f"  ✅ {diva_file.name}: {file_pairs:,} pairs")
        except Exception as e:
            print(f"  ⚠️  {diva_file.name}: {e}")

print(f"\n{'=' * 60}")
print("✅ SUCCESS!")
print(f"  Files processed: {processed_files}")
print(f"  Total Q&A pairs: {total_pairs:,}")
print(f"  Skipped (no abstract): {skipped_no_abstract:,}")
print(f"  Output: {output_file.name}")
print(f"  Size: {output_file.stat().st_size / 1024 / 1024:.1f} MB")
print(f"{'=' * 60}")
