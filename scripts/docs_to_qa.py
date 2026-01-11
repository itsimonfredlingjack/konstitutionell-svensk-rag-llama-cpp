#!/usr/bin/env python3
"""
Documentation to Q&A Converter
==============================
Konverterar markdown-dokumentation till Q&A träningsexempel.
"""

import json
import re
from pathlib import Path


def extract_sections(content: str) -> list[tuple[str, str]]:
    """Extrahera sektioner från markdown."""
    sections = []

    # Split på headers
    header_pattern = r"^(#{1,3})\s+(.+)$"
    lines = content.split("\n")

    current_header = None
    current_content = []

    for line in lines:
        match = re.match(header_pattern, line)
        if match:
            # Spara föregående sektion
            if current_header and current_content:
                text = "\n".join(current_content).strip()
                if len(text) > 50:  # Min längd
                    sections.append((current_header, text))

            current_header = match.group(2)
            current_content = []
        else:
            current_content.append(line)

    # Sista sektionen
    if current_header and current_content:
        text = "\n".join(current_content).strip()
        if len(text) > 50:
            sections.append((current_header, text))

    return sections


def generate_qa_from_section(header: str, content: str, source_file: str) -> list[dict]:
    """Generera Q&A-par från en sektion."""
    examples = []

    # Rensa content
    content = content.strip()
    if len(content) < 100:
        return examples

    # Generera frågor baserat på header-typen
    header_lower = header.lower()

    # Arkitektur-frågor
    if any(
        word in header_lower for word in ["arkitektur", "architecture", "struktur", "structure"]
    ):
        examples.append(
            {"instruction": f"Förklara arkitekturen för {header} i Simon's AI", "output": content}
        )

    # API/Endpoint-frågor
    elif any(word in header_lower for word in ["api", "endpoint", "route"]):
        examples.append({"instruction": f"Hur fungerar {header}?", "output": content})

    # Workflow-frågor
    elif any(word in header_lower for word in ["workflow", "flöde", "process"]):
        examples.append({"instruction": f"Beskriv {header} processen", "output": content})

    # Konfiguration-frågor
    elif any(word in header_lower for word in ["config", "konfig", "setting", "parameter"]):
        examples.append({"instruction": f"Hur konfigurerar jag {header}?", "output": content})

    # Felsökning-frågor
    elif any(word in header_lower for word in ["felsök", "debug", "troubleshoot", "problem"]):
        examples.append({"instruction": f"Hur felsöker jag {header}?", "output": content})

    # Installation/Setup-frågor
    elif any(word in header_lower for word in ["install", "setup", "start", "börja"]):
        examples.append({"instruction": f"Hur sätter jag upp {header}?", "output": content})

    # Generisk fråga för övriga
    else:
        examples.append({"instruction": f"Vad är {header}?", "output": content})

    # Lägg till källa
    for ex in examples:
        ex["output"] += f"\n\n*Källa: {source_file}*"

    return examples


def extract_code_examples(content: str) -> list[dict]:
    """Extrahera kodexempel från markdown."""
    examples = []

    # Hitta kodblock med kontext
    pattern = r"([^\n]+)\n\n```(\w+)\n([\s\S]+?)\n```"

    for match in re.finditer(pattern, content):
        context = match.group(1).strip()
        lang = match.group(2)
        code = match.group(3)

        # Hoppa över för korta
        if len(code) < 50:
            continue

        # Generera instruktion från kontext
        if ":" in context:
            instruction = context.split(":")[-1].strip()
        else:
            instruction = context

        if instruction:
            examples.append(
                {
                    "instruction": f"Visa hur man {instruction.lower()}",
                    "output": f"```{lang}\n{code}\n```",
                }
            )

    return examples


def process_markdown_file(filepath: Path, base_dir: Path) -> list[dict]:
    """Processa en markdown-fil."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  Skip: {filepath} ({e})")
        return []

    rel_path = str(filepath.relative_to(base_dir))
    examples = []

    # Extrahera sektioner
    sections = extract_sections(content)
    for header, section_content in sections:
        qa_examples = generate_qa_from_section(header, section_content, rel_path)
        examples.extend(qa_examples)

    # Extrahera kodexempel
    code_examples = extract_code_examples(content)
    examples.extend(code_examples)

    return examples


def main():
    base_dir = Path("/home/ai-server/01_PROJECTS/01_AI-VIBE-WORLD")
    output_file = base_dir / "data" / "docs_qa_training.jsonl"

    print("=" * 60)
    print("Documentation to Q&A Converter")
    print("=" * 60)

    # Hitta alla markdown-filer
    md_files = [
        base_dir / "DEEP_DOCS.md",
        base_dir / "ARCHITECTURE_MASTER.md",
        base_dir / "CHANGELOG.md",
        base_dir / "CLAUDE.md",
        base_dir / "frontend" / "README.md",
    ]

    # Lägg till eventuella docs/
    for doc in (base_dir / "docs").glob("*.md"):
        md_files.append(doc)

    all_examples = []

    print("\nProcessing markdown files...")
    for filepath in md_files:
        if not filepath.exists():
            continue

        examples = process_markdown_file(filepath, base_dir)
        if examples:
            print(f"  {filepath.name}: {len(examples)} examples")
            all_examples.extend(examples)

    # Filtrera duplicat
    seen = set()
    unique_examples = []
    for ex in all_examples:
        key = ex["instruction"][:50]
        if key not in seen and len(ex["output"]) > 50:
            seen.add(key)
            unique_examples.append(ex)

    # Spara
    print(f"\nSaving {len(unique_examples)} examples to {output_file}")
    with open(output_file, "w", encoding="utf-8") as f:
        for ex in unique_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print("Done!")


if __name__ == "__main__":
    main()
