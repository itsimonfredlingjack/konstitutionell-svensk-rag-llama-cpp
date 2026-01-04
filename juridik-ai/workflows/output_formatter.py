#!/usr/bin/env python3
"""
Formatera AI-output till standardiserade juridiska loggböcker.
Säkerställer konsistent format oavsett modellens output.
"""

import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class JuridiskLoggbok:
    """Strukturerad juridisk loggbok."""

    datum: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    arende: str = ""
    kalla: str = ""
    myndighet: str = ""

    # Juridisk grund
    lagrum: list = field(default_factory=list)
    jo_beslut: list = field(default_factory=list)

    # Analys
    bedomning: str = ""

    # Risker
    risker: list = field(default_factory=list)  # [(beskrivning, nivå)]

    # Dokumentation
    saknas: list = field(default_factory=list)
    bristfalligt: list = field(default_factory=list)

    # Åtgärder
    atgarder: list = field(default_factory=list)


def extract_sections(raw_text: str) -> dict:
    """Extrahera sektioner från rå AI-output."""
    sections = {"bedomning": "", "risker": [], "lagrum": [], "saknas": [], "atgarder": []}

    # Hitta bedömning/analys
    bedömning_match = re.search(
        r"(?:BEDÖMNING|ANALYS|🔍)[:\s]*\n?(.*?)(?=(?:RISK|⚠️|SAKNAS|📊|NÄSTA|✅|$))",
        raw_text,
        re.IGNORECASE | re.DOTALL,
    )
    if bedömning_match:
        sections["bedomning"] = bedömning_match.group(1).strip()

    # Hitta risker
    risk_pattern = r"(?:RISK|⚠️)[^:]*:\s*\n?(.*?)(?=(?:RISK|⚠️|SAKNAS|📊|NÄSTA|✅|$))"
    risk_matches = re.findall(risk_pattern, raw_text, re.IGNORECASE | re.DOTALL)

    for risk_text in risk_matches:
        # Försök extrahera nivå
        niva_match = re.search(r"(?:Nivå|NIVÅ):\s*(Låg|Medel|Hög)", risk_text, re.IGNORECASE)
        niva = niva_match.group(1) if niva_match else "Medel"

        # Rensa risk-text
        risk_clean = re.sub(r"(?:Nivå|NIVÅ):\s*(?:Låg|Medel|Hög)", "", risk_text).strip()
        if risk_clean:
            sections["risker"].append((risk_clean[:200], niva))

    # Hitta lagrum/paragrafer
    lagrum_matches = re.findall(
        r"§\s*\d+[a-z]?\s*(?:i\s+)?([A-ZÅÄÖ][a-zåäö]+(?:lagen|lag|FL|SoL|LSS)?)", raw_text
    )
    sections["lagrum"] = list(set(lagrum_matches))

    # Hitta saknade dokument
    saknas_pattern = r"(?:SAKNAS|📊)[^:]*:[^\n]*\n((?:[-•*]\s*\[?\s*\]?\s*[^\n]+\n?)+)"
    saknas_match = re.search(saknas_pattern, raw_text, re.IGNORECASE)
    if saknas_match:
        items = re.findall(r"[-•*]\s*\[?\s*\]?\s*([^\n]+)", saknas_match.group(1))
        sections["saknas"] = [item.strip() for item in items if item.strip()]

    # Hitta åtgärder
    atgard_pattern = r"(?:NÄSTA STEG|ÅTGÄRD|✅)[^:]*:[^\n]*\n((?:\d+\.\s*[^\n]+\n?)+)"
    atgard_match = re.search(atgard_pattern, raw_text, re.IGNORECASE)
    if atgard_match:
        items = re.findall(r"\d+\.\s*([^\n]+)", atgard_match.group(1))
        sections["atgarder"] = [item.strip() for item in items if item.strip()]

    return sections


def format_loggbok(loggbok: JuridiskLoggbok) -> str:
    """Formatera loggbok till standardformat."""
    output = []

    output.append("═" * 55)
    output.append("BYRÅKRATISK LOGGBOK")
    output.append("═" * 55)
    output.append("")
    output.append(f"📅 DATUM: {loggbok.datum}")
    output.append(f"📋 ÄRENDE: {loggbok.arende or 'Ej angivet'}")
    output.append(f"📄 KÄLLA: {loggbok.kalla or 'Ej angivet'}")
    if loggbok.myndighet:
        output.append(f"🏛️ MYNDIGHET: {loggbok.myndighet}")
    output.append("")

    # Juridisk grund
    output.append("─" * 55)
    output.append("⚖️ JURIDISK GRUND")
    output.append("─" * 55)
    if loggbok.lagrum:
        for lag in loggbok.lagrum:
            output.append(f"- {lag}")
    else:
        output.append("- Inga specifika lagrum identifierade")
    if loggbok.jo_beslut:
        output.append("")
        output.append("JO-beslut:")
        for jo in loggbok.jo_beslut:
            output.append(f"- {jo}")
    output.append("")

    # Bedömning
    output.append("─" * 55)
    output.append("🔍 BEDÖMNING")
    output.append("─" * 55)
    output.append(loggbok.bedomning or "Ingen bedömning tillgänglig.")
    output.append("")

    # Risker
    output.append("─" * 55)
    output.append("⚠️ IDENTIFIERADE RISKER")
    output.append("─" * 55)
    if loggbok.risker:
        for i, (beskrivning, niva) in enumerate(loggbok.risker, 1):
            emoji = {"Låg": "🟢", "Medel": "🟡", "Hög": "🔴"}.get(niva, "🟡")
            output.append(f"{i}. {beskrivning}")
            output.append(f"   {emoji} Risknivå: {niva}")
            output.append("")
    else:
        output.append("Inga specifika risker identifierade.")
    output.append("")

    # Dokumentation
    if loggbok.saknas or loggbok.bristfalligt:
        output.append("─" * 55)
        output.append("📊 DOKUMENTATIONSGRANSKNING")
        output.append("─" * 55)
        if loggbok.saknas:
            output.append("SAKNAS:")
            for item in loggbok.saknas:
                output.append(f"- [ ] {item}")
        if loggbok.bristfalligt:
            output.append("")
            output.append("BRISTFÄLLIGT:")
            for item in loggbok.bristfalligt:
                output.append(f"- [ ] {item}")
        output.append("")

    # Åtgärder
    output.append("─" * 55)
    output.append("✅ NÄSTA STEG")
    output.append("─" * 55)
    if loggbok.atgarder:
        for i, atgard in enumerate(loggbok.atgarder, 1):
            output.append(f"{i}. {atgard}")
    else:
        output.append("1. Granska dokumentet manuellt")
        output.append("2. Komplettera eventuella brister")
    output.append("")

    output.append("═" * 55)
    output.append(f"Genererad: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    output.append("Modell: Qwen 2.5 3B Juridik")
    output.append("═" * 55)

    return "\n".join(output)


def process_raw_output(raw_text: str, metadata: Optional[dict] = None) -> str:
    """Bearbeta rå AI-output till formaterad loggbok."""
    # Extrahera sektioner
    sections = extract_sections(raw_text)

    # Skapa loggbok
    loggbok = JuridiskLoggbok()

    # Fyll i metadata om tillgänglig
    if metadata:
        loggbok.arende = metadata.get("arende", "")
        loggbok.kalla = metadata.get("kalla", "")
        loggbok.myndighet = metadata.get("myndighet", "")

    # Fyll i extraherade sektioner
    loggbok.bedomning = sections["bedomning"]
    loggbok.risker = sections["risker"]
    loggbok.lagrum = sections["lagrum"]
    loggbok.saknas = sections["saknas"]
    loggbok.atgarder = sections["atgarder"]

    # Formatera
    return format_loggbok(loggbok)


def main():
    """CLI för output-formatering."""
    if len(sys.argv) < 2:
        print("Användning: python output_formatter.py <raw_output.txt> [output.md]")
        print("\nKonverterar rå AI-output till standardiserad juridisk loggbok.")
        sys.exit(1)

    input_file = Path(sys.argv[1])
    output_file = (
        Path(sys.argv[2]) if len(sys.argv) > 2 else input_file.with_suffix(".formatted.md")
    )

    if not input_file.exists():
        print(f"Fel: Filen {input_file} finns inte")
        sys.exit(1)

    # Läs rå output
    raw_text = input_file.read_text(encoding="utf-8")

    # Formatera
    formatted = process_raw_output(raw_text)

    # Spara
    output_file.write_text(formatted, encoding="utf-8")

    print(f"✅ Formaterad loggbok sparad: {output_file}")
    print("\n" + formatted)


if __name__ == "__main__":
    main()
