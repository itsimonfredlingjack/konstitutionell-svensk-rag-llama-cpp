#!/usr/bin/env python3
"""
Dela upp långa juridiska dokument i logiska sektioner för analys.
Optimerat för Qwen 2.5 3B med begränsat context window (4096 tokens).
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path

# 1 token ≈ 4 tecken för svensk text
MAX_CHARS_PER_CHUNK = 12000  # ~3000 tokens, lämnar utrymme för prompt + output


@dataclass
class DocumentSection:
    """En sektion av ett juridiskt dokument."""

    title: str
    content: str
    section_type: str  # bakgrund, beslut, motivering, hanvisningar
    char_count: int
    estimated_tokens: int


def detect_section_type(text: str) -> str:
    """Identifiera vilken typ av sektion texten tillhör."""
    text_lower = text.lower()[:500]  # Kolla början

    if any(x in text_lower for x in ["bakgrund", "ärendet gäller", "historik", "inledning"]):
        return "bakgrund"
    elif any(x in text_lower for x in ["beslut", "beslutar", "avgörande"]):
        return "beslut"
    elif any(x in text_lower for x in ["motivering", "skäl", "bedömning", "överväganden"]):
        return "motivering"
    elif any(x in text_lower for x in ["hänvisning", "lagrum", "tillämpliga", "författning"]):
        return "hanvisningar"
    else:
        return "ovrigt"


def split_by_headers(text: str) -> list[str]:
    """Dela upp text baserat på vanliga rubrikformat i juridiska dokument."""
    # Mönster för vanliga rubriker
    patterns = [
        r"\n(?=\d+\.\s+[A-ZÅÄÖ])",  # "1. Bakgrund"
        r"\n(?=[A-ZÅÄÖ]{2,}\s*\n)",  # "BAKGRUND\n"
        r"\n(?=#{1,3}\s+)",  # Markdown-rubriker
        r"\n(?=\*\*[A-ZÅÄÖ])",  # **RUBRIK**
        r"\n{3,}",  # Flera tomma rader
    ]

    # Kombinera mönster
    combined_pattern = "|".join(patterns)

    # Dela upp
    sections = re.split(combined_pattern, text)

    # Filtrera tomma sektioner
    return [s.strip() for s in sections if s.strip()]


def chunk_text(text: str, max_chars: int = MAX_CHARS_PER_CHUNK) -> list[str]:
    """Dela upp text i chunks som passar context window."""
    if len(text) <= max_chars:
        return [text]

    # Försök dela vid paragraf-gränser
    paragraphs = text.split("\n\n")

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= max_chars:
            current_chunk += para + "\n\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())

            # Om enskild paragraf är för lång, dela den
            if len(para) > max_chars:
                # Dela vid meningar
                sentences = re.split(r"(?<=[.!?])\s+", para)
                sent_chunk = ""
                for sent in sentences:
                    if len(sent_chunk) + len(sent) + 1 <= max_chars:
                        sent_chunk += sent + " "
                    else:
                        if sent_chunk:
                            chunks.append(sent_chunk.strip())
                        sent_chunk = sent + " "
                if sent_chunk:
                    current_chunk = sent_chunk
                else:
                    current_chunk = ""
            else:
                current_chunk = para + "\n\n"

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


def process_document(text: str) -> list[DocumentSection]:
    """Bearbeta ett helt dokument och returnera sektioner."""
    # Steg 1: Dela vid rubriker
    raw_sections = split_by_headers(text)

    sections = []

    for raw in raw_sections:
        # Steg 2: Chunka om för lång
        chunks = chunk_text(raw)

        for i, chunk in enumerate(chunks):
            section_type = detect_section_type(chunk)

            # Extrahera titel (första raden)
            lines = chunk.split("\n")
            title = lines[0][:80] if lines else "Okänd sektion"

            if len(chunks) > 1:
                title += f" (del {i+1}/{len(chunks)})"

            sections.append(
                DocumentSection(
                    title=title,
                    content=chunk,
                    section_type=section_type,
                    char_count=len(chunk),
                    estimated_tokens=len(chunk) // 4,
                )
            )

    return sections


def format_for_analysis(sections: list[DocumentSection]) -> str:
    """Formatera sektioner för utskrift/loggning."""
    output = []
    output.append("=" * 60)
    output.append("DOKUMENT UPPDELAT I SEKTIONER")
    output.append("=" * 60)
    output.append(f"Totalt {len(sections)} sektioner\n")

    for i, section in enumerate(sections, 1):
        output.append(f"─── SEKTION {i} ───")
        output.append(f"Titel: {section.title}")
        output.append(f"Typ: {section.section_type}")
        output.append(f"Storlek: {section.char_count} tecken (~{section.estimated_tokens} tokens)")
        output.append(f"Förhandsgranskning: {section.content[:200]}...")
        output.append("")

    return "\n".join(output)


def save_sections(sections: list[DocumentSection], output_dir: Path, base_name: str):
    """Spara sektioner som separata filer för batch-analys."""
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = []

    for i, section in enumerate(sections, 1):
        filename = f"{base_name}_section_{i:02d}_{section.section_type}.txt"
        filepath = output_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# Sektion {i}: {section.title}\n")
            f.write(f"# Typ: {section.section_type}\n")
            f.write(f"# Tokens: ~{section.estimated_tokens}\n")
            f.write("-" * 40 + "\n\n")
            f.write(section.content)

        manifest.append(
            {
                "file": filename,
                "title": section.title,
                "type": section.section_type,
                "tokens": section.estimated_tokens,
            }
        )

    # Spara manifest
    manifest_path = output_dir / f"{base_name}_manifest.txt"
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write("SEKTIONSMANIFEST\n")
        f.write("=" * 40 + "\n\n")
        for m in manifest:
            f.write(f"Fil: {m['file']}\n")
            f.write(f"  Titel: {m['title']}\n")
            f.write(f"  Typ: {m['type']}\n")
            f.write(f"  Tokens: ~{m['tokens']}\n\n")

    return manifest


def main():
    """CLI för dokumentuppdelning."""
    if len(sys.argv) < 2:
        print("Användning: python long_document_split.py <dokument.txt> [output_dir]")
        print("\nDelar upp långa dokument i sektioner för Qwen-analys.")
        sys.exit(1)

    input_file = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("./sections")

    if not input_file.exists():
        print(f"Fel: Filen {input_file} finns inte")
        sys.exit(1)

    # Läs dokument
    with open(input_file, encoding="utf-8") as f:
        text = f.read()

    print(f"Läser: {input_file}")
    print(f"Dokumentstorlek: {len(text)} tecken (~{len(text)//4} tokens)")

    # Bearbeta
    sections = process_document(text)

    # Visa sammanfattning
    print(format_for_analysis(sections))

    # Spara
    base_name = input_file.stem
    manifest = save_sections(sections, output_dir, base_name)

    print(f"\n✅ Sparat {len(manifest)} sektioner till {output_dir}/")
    print(f"📋 Manifest: {output_dir}/{base_name}_manifest.txt")


if __name__ == "__main__":
    main()
