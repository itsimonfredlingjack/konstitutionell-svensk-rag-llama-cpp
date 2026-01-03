#!/usr/bin/env python3
"""
Extended Documentation to Q&A Converter
=======================================
Konverterar ALL dokumentation till Q&A träningsexempel.
Inkluderar: projekt-docs, juridiska dokument, myndighetsdokumentation.
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Tuple


def extract_sections(content: str) -> List[Tuple[str, str]]:
    """Extrahera sektioner från markdown."""
    sections = []
    header_pattern = r'^(#{1,4})\s+(.+)$'
    lines = content.split('\n')

    current_header = None
    current_content = []

    for line in lines:
        match = re.match(header_pattern, line)
        if match:
            if current_header and current_content:
                text = '\n'.join(current_content).strip()
                if len(text) > 50:
                    sections.append((current_header, text))
            current_header = match.group(2)
            current_content = []
        else:
            current_content.append(line)

    if current_header and current_content:
        text = '\n'.join(current_content).strip()
        if len(text) > 50:
            sections.append((current_header, text))

    return sections


def extract_timeline_entries(content: str, source: str) -> List[Dict]:
    """Extrahera tidslinjeformat (### YYYY-MM-DD)."""
    examples = []

    # Matcha tidslinjeformat
    pattern = r'###\s+(\d{4}-\d{2}-\d{2})\n(.*?)(?=###\s+\d{4}|\Z)'

    for match in re.finditer(pattern, content, re.DOTALL):
        date = match.group(1)
        entry_content = match.group(2).strip()

        if len(entry_content) > 100:
            # Extrahera ämne om det finns
            subject_match = re.search(r'\*\*Ämne:\*\*\s*(.+)', entry_content)
            subject = subject_match.group(1) if subject_match else f"händelse {date}"

            examples.append({
                "instruction": f"Vad hände {date} i GU-ärendet?",
                "output": entry_content + f"\n\n*Källa: {source}*"
            })

    return examples


def extract_evidence_entries(content: str, source: str) -> List[Dict]:
    """Extrahera bevisstruktur (numrerade bevis med stjärnor)."""
    examples = []

    # Matcha bevisformat
    pattern = r'###\s+(\d+)\.\s+\*\*(.+?)\*\*.*?\n(.*?)(?=###\s+\d+\.|\Z)'

    for match in re.finditer(pattern, content, re.DOTALL):
        num = match.group(1)
        title = match.group(2)
        evidence_content = match.group(3).strip()

        if len(evidence_content) > 100:
            examples.append({
                "instruction": f"Beskriv bevis #{num}: {title}",
                "output": evidence_content + f"\n\n*Källa: {source}*"
            })

    return examples


def generate_legal_qa(header: str, content: str, source: str) -> List[Dict]:
    """Generera juridiska Q&A-par."""
    examples = []
    header_lower = header.lower()

    # Juridiska termer
    if any(word in header_lower for word in ['afs', 'arbetsmiljö', 'lag', 'brottsbalken', 'arkivlagen']):
        examples.append({
            "instruction": f"Förklara den juridiska aspekten av {header}",
            "output": content
        })

    # GDPR/IMY
    elif any(word in header_lower for word in ['gdpr', 'imy', 'personuppgift', 'integritet']):
        examples.append({
            "instruction": f"Hur relaterar {header} till GDPR?",
            "output": content
        })

    # Rehabilitering
    elif any(word in header_lower for word in ['rehab', 'sjuk', 'återgång', 'avonova']):
        examples.append({
            "instruction": f"Beskriv rehabiliteringsaspekten i {header}",
            "output": content
        })

    # Bevis
    elif any(word in header_lower for word in ['bevis', 'inspelning', 'mejl', 'dokument']):
        examples.append({
            "instruction": f"Vad visar {header} som bevis?",
            "output": content
        })

    # Tidslinje
    elif any(word in header_lower for word in ['tidslinje', 'kronolog', 'händelse']):
        examples.append({
            "instruction": f"Beskriv tidslinjen för {header}",
            "output": content
        })

    # Aktörer
    elif any(word in header_lower for word in ['roger', 'rebecka', 'henrik', 'christina', 'donika']):
        examples.append({
            "instruction": f"Vilken roll spelar {header} i ärendet?",
            "output": content
        })

    # Myndigheter
    elif any(word in header_lower for word in ['gu', 'universitet', 'ivo', 'jo', 'facket']):
        examples.append({
            "instruction": f"Hur agerade {header}?",
            "output": content
        })

    return examples


def generate_technical_qa(header: str, content: str, source: str) -> List[Dict]:
    """Generera tekniska Q&A-par (MCP, API, etc)."""
    examples = []
    header_lower = header.lower()

    if any(word in header_lower for word in ['mcp', 'protocol', 'server', 'client']):
        examples.append({
            "instruction": f"Förklara MCP-konceptet: {header}",
            "output": content
        })
    elif any(word in header_lower for word in ['api', 'endpoint', 'request', 'response']):
        examples.append({
            "instruction": f"Hur fungerar {header} i API:et?",
            "output": content
        })
    elif any(word in header_lower for word in ['config', 'setup', 'install']):
        examples.append({
            "instruction": f"Hur konfigurerar man {header}?",
            "output": content
        })

    return examples


def process_markdown_file(filepath: Path, category: str) -> List[Dict]:
    """Processa en markdown-fil baserat på kategori."""
    try:
        content = filepath.read_text(encoding='utf-8')
    except Exception as e:
        print(f"  Skip: {filepath} ({e})")
        return []

    source = filepath.name
    examples = []

    # Extrahera sektioner
    sections = extract_sections(content)

    for header, section_content in sections:
        if len(section_content) < 100:
            continue

        if category == 'legal':
            qa = generate_legal_qa(header, section_content, source)
        elif category == 'technical':
            qa = generate_technical_qa(header, section_content, source)
        else:
            # Generisk
            qa = [{
                "instruction": f"Vad är {header}?",
                "output": section_content
            }]

        examples.extend(qa)

    # Speciella extraheringar för juridiska dokument
    if category == 'legal':
        examples.extend(extract_timeline_entries(content, source))
        examples.extend(extract_evidence_entries(content, source))

    # Lägg till källa
    for ex in examples:
        if '*Källa:' not in ex["output"]:
            ex["output"] += f"\n\n*Källa: {source}*"

    return examples


def process_txt_file(filepath: Path) -> List[Dict]:
    """Processa textfiler (mejl, transkriptioner, etc)."""
    try:
        content = filepath.read_text(encoding='utf-8')
    except Exception as e:
        print(f"  Skip: {filepath} ({e})")
        return []

    if len(content) < 200:
        return []

    source = filepath.name

    # Avgör typ baserat på filnamn
    name_lower = source.lower()

    if 'transkri' in name_lower:
        instruction = f"Visa transkribering från {source}"
    elif 'epost' in name_lower or 'mejl' in name_lower:
        instruction = f"Visa mejlkorrespondens: {source}"
    elif 'begär' in name_lower or 'begar' in name_lower:
        instruction = f"Visa begäran: {source}"
    else:
        instruction = f"Visa dokumentet: {source}"

    return [{
        "instruction": instruction,
        "output": content[:3000] + ("\n\n[...]" if len(content) > 3000 else "") + f"\n\n*Källa: {source}*"
    }]


def main():
    output_file = Path("/home/ai-server/01_PROJECTS/01_AI-VIBE-WORLD/data/extended_docs_training.jsonl")

    print("=" * 60)
    print("Extended Documentation to Q&A Converter")
    print("=" * 60)

    all_examples = []

    # === 1. PROJEKT-DOCS (tekniska) ===
    print("\n[1/4] Processing project documentation...")
    project_docs = [
        Path("/home/ai-server/01_PROJECTS/01_AI-VIBE-WORLD/docs/MCP_REMOTE_SERVER_SPECIFICATION.md"),
        Path("/home/ai-server/01_PROJECTS/01_AI-VIBE-WORLD/cli/HANDOVER_CONTEXT.md"),
        Path("/home/ai-server/01_PROJECTS/01_AI-VIBE-WORLD/FELSÖKNING.md"),
        Path("/home/ai-server/01_PROJECTS/01_AI-VIBE-WORLD/frontend/FLOWCONNECTOR_USAGE.md"),
    ]

    for filepath in project_docs:
        if filepath.exists():
            examples = process_markdown_file(filepath, 'technical')
            if examples:
                print(f"  {filepath.name}: {len(examples)} examples")
                all_examples.extend(examples)

    # === 2. UNIVERSITY_OF_FUCKERS (juridiska) ===
    print("\n[2/4] Processing University_Of_Fuckers...")
    uof_base = Path("/home/ai-server/University_Of_Fuckers")

    if uof_base.exists():
        for md_file in uof_base.glob("**/*.md"):
            # Skippa duplicat (THE_MASTERS har kopior)
            if 'THE_MASTERS' in str(md_file) and any(
                (uof_base / d / md_file.name).exists()
                for d in ['00_TIDSLINJE', '01_LAKARLOGN', '02_AVONOVA_REBECKA']
            ):
                continue

            examples = process_markdown_file(md_file, 'legal')
            if examples:
                print(f"  {md_file.name}: {len(examples)} examples")
                all_examples.extend(examples)

    # === 3. GU_CASE_BACKUP ===
    print("\n[3/4] Processing GU_CASE_BACKUP...")
    gu_base = Path("/home/ai-server/GU_CASE_BACKUP")

    if gu_base.exists():
        # Markdown
        for md_file in list(gu_base.glob("**/*.md"))[:50]:  # Limit för hastighet
            examples = process_markdown_file(md_file, 'legal')
            if examples:
                print(f"  {md_file.name}: {len(examples)} examples")
                all_examples.extend(examples)

        # Textfiler (mejl, transkriptioner)
        for txt_file in list(gu_base.glob("**/*.txt"))[:30]:  # Limit
            examples = process_txt_file(txt_file)
            if examples:
                print(f"  {txt_file.name}: {len(examples)} examples")
                all_examples.extend(examples)

    # === 4. EXTRA PROJEKT-DOCS ===
    print("\n[4/4] Processing additional docs...")
    extra_docs = list(Path("/home/ai-server/01_PROJECTS/01_AI-VIBE-WORLD/docs").glob("*.md"))

    for filepath in extra_docs:
        if filepath.exists() and filepath.name not in ['MCP_REMOTE_SERVER_SPECIFICATION.md']:
            examples = process_markdown_file(filepath, 'technical')
            if examples:
                print(f"  {filepath.name}: {len(examples)} examples")
                all_examples.extend(examples)

    # === FILTRERA DUPLICAT ===
    print("\nFiltering duplicates...")
    seen = set()
    unique_examples = []

    for ex in all_examples:
        # Använd första 80 tecken av instruction som nyckel
        key = ex["instruction"][:80]
        if key not in seen and len(ex["output"]) > 100:
            seen.add(key)
            unique_examples.append(ex)

    # === SPARA ===
    print(f"\nSaving {len(unique_examples)} examples to {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        for ex in unique_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + '\n')

    print(f"\nDone! Total unique examples: {len(unique_examples)}")

    # Stats
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total raw examples: {len(all_examples)}")
    print(f"Unique examples: {len(unique_examples)}")
    print(f"Output file: {output_file}")


if __name__ == "__main__":
    main()
