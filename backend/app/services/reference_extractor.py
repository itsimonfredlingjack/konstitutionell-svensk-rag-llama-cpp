"""
Reference Extractor — Comprehensive Swedish Legal Cross-Reference Extraction
=============================================================================

Extracts typed legal references from Swedish legal text using regex patterns.
Covers SFS numbers, section/chapter references, propositioner, SOU, Ds,
betankanden, NJA, HFD, and EU directives/regulations.

Supersedes the cross-ref extraction in sfs_structure_parser.py (which only
covers internal, external SFS, and 5 named grundlagar).

Usage:
    from backend.app.services.reference_extractor import extract_references, references_to_metadata

    refs = extract_references("Enligt 2 kap. 3 § regeringsformen och SFS 2009:400...")
    metadata = references_to_metadata(refs)
"""

from __future__ import annotations

import re
from dataclasses import dataclass  # noqa: F401


@dataclass
class LegalReference:
    """A typed legal reference extracted from Swedish legal text."""

    ref_type: str  # "sfs", "section", "proposition", "sou", "nja", "hfd", "eu", "ds", "betankande"
    raw_match: str  # Original matched text
    target_sfs: str | None = None  # e.g. "1974:152"
    target_chapter: str | None = None  # e.g. "2"
    target_section: str | None = None  # e.g. "3"
    display: str = ""  # Human-readable citation


# Swedish ordinal-to-number mapping for stycke references
ORDINAL_MAP = {
    "första": 1,
    "andra": 2,
    "tredje": 3,
    "fjärde": 4,
    "femte": 5,
    "sjätte": 6,
    "sjunde": 7,
    "åttonde": 8,
    "nionde": 9,
    "tionde": 10,
}


# ── Compiled Regex Patterns ──────────────────────────────────────────────

# 1. Explicit SFS reference: "SFS 2009:400", "SFS 1974:152"
_SFS_EXPLICIT_RE = re.compile(r"SFS\s+(\d{4}:\d+)", re.IGNORECASE)

# 2. Implicit SFS reference: "1974:152" in running text (not preceded by word chars)
# Must not match dates like "2024-01-15" or time "14:30"
_SFS_IMPLICIT_RE = re.compile(r"(?<!\w)(\d{4}:\d{2,})\b")

# 3. Section + chapter reference: "2 kap. 3 §", "1 a kap. 5 §"
_SECTION_CHAPTER_RE = re.compile(r"(\d+[a-z]?)\s*kap\.?\s+(\d+[a-z]?)\s*§")

# 4. Simple section reference: "3 §" standalone
# Uses a broad match; filtering out kap+§ matches is done in extract_references()
_SECTION_SIMPLE_RE = re.compile(r"(?<!\w)(\d+[a-z]?)\s*§")

# 5. Stycke reference: "6 kap. 7 § första stycket"
_STYCKE_RE = re.compile(
    r"(\d+[a-z]?)\s*kap\.?\s+(\d+[a-z]?)\s*§\s+"
    r"(första|andra|tredje|fjärde|femte|sjätte|sjunde|åttonde|nionde|tionde)\s+stycket",
    re.IGNORECASE,
)

# 6. Proposition reference: "prop. 1997/98:45", "Prop. 2020/21:150"
_PROPOSITION_RE = re.compile(r"[Pp]rop\.\s*(\d{4}/\d{2}:\d+)")

# 7. SOU reference: "SOU 2020:47"
_SOU_RE = re.compile(r"SOU\s+(\d{4}:\d+)", re.IGNORECASE)

# 8. Ds reference: "Ds 2019:1"
_DS_RE = re.compile(r"Ds\s+(\d{4}:\d+)")

# 9. Betänkande reference: "bet. 2019/20:KU10"
_BETANKANDE_RE = re.compile(r"[Bb]et\.\s*(\d{4}/\d{2}:[A-ZÅÄÖ]+\d+)")

# 10. NJA reference: "NJA 2014 s. 323"
_NJA_RE = re.compile(r"NJA\s+(\d{4})\s+s\.\s*(\d+)")

# 11. HFD reference: "HFD 2018 ref. 51"
_HFD_RE = re.compile(r"HFD\s+(\d{4})\s+ref\.\s*(\d+)")

# 12. EU directive/regulation: "förordning (EU) 2016/679", "direktiv 2006/24/EG"
_EU_DIRECTIVE_RE = re.compile(
    r"(förordning|direktiv)\s*" r"(?:\((?:EU|EG|EEG)\)\s*)?" r"(\d{4}/\d+(?:/[A-Z]{2,3})?)",
    re.IGNORECASE,
)

# Named grundlagar for resolving implicit references
_NAMED_LAGAR = {
    "regeringsformen": "1974:152",
    "successionsordningen": "1810:0926",
    "tryckfrihetsförordningen": "1949:105",
    "yttrandefrihetsgrundlagen": "1991:1469",
    "riksdagsordningen": "2014:801",
    "brottsbalken": "1962:700",
    "rättegångsbalken": "1942:740",
    "miljöbalken": "1998:808",
    "kommunallagen": "2017:725",
    "förvaltningslagen": "2017:900",
    "offentlighets- och sekretesslagen": "2009:400",
    "socialtjänstlagen": "2001:453",
    "plan- och bygglagen": "2010:900",
    "arbetsmiljölagen": "1977:1160",
    "dataskyddslagen": "2018:218",
}


def extract_references(text: str) -> list[LegalReference]:
    """
    Extract all legal references from Swedish legal text.

    Deduplicates via a seen set on (ref_type, raw_match).

    Args:
        text: Swedish legal text to analyze

    Returns:
        List of LegalReference objects, deduplicated
    """
    if not text or not text.strip():
        return []

    refs: list[LegalReference] = []
    seen: set[str] = set()

    def _add(ref: LegalReference) -> None:
        key = f"{ref.ref_type}:{ref.raw_match}"
        if key not in seen:
            seen.add(key)
            refs.append(ref)

    # 5. Stycke references (must come before section_chapter to avoid partial matches)
    for m in _STYCKE_RE.finditer(text):
        kap, par, ordinal = m.group(1), m.group(2), m.group(3).lower()
        raw = m.group(0)
        _add(
            LegalReference(
                ref_type="section",
                raw_match=raw,
                target_chapter=kap,
                target_section=par,
                display=f"{kap} kap. {par} § {ordinal} stycket",
            )
        )
        # Also mark the kap+§ part as seen so it doesn't get re-extracted
        seen.add(f"section:{kap} kap. {par} §")

    # 3. Section + chapter references: "2 kap. 3 §"
    for m in _SECTION_CHAPTER_RE.finditer(text):
        kap, par = m.group(1), m.group(2)
        raw = m.group(0)
        dedup_key = f"section:{kap} kap. {par} §"
        if dedup_key in seen:
            continue
        _add(
            LegalReference(
                ref_type="section",
                raw_match=raw,
                target_chapter=kap,
                target_section=par,
                display=f"{kap} kap. {par} §",
            )
        )

    # 1. Explicit SFS references: "SFS 2009:400"
    for m in _SFS_EXPLICIT_RE.finditer(text):
        sfs_nr = m.group(1)
        _add(
            LegalReference(
                ref_type="sfs",
                raw_match=m.group(0),
                target_sfs=sfs_nr,
                display=f"SFS {sfs_nr}",
            )
        )

    # 6. Proposition references
    for m in _PROPOSITION_RE.finditer(text):
        prop_nr = m.group(1)
        _add(
            LegalReference(
                ref_type="proposition",
                raw_match=m.group(0),
                display=f"prop. {prop_nr}",
            )
        )

    # 7. SOU references
    for m in _SOU_RE.finditer(text):
        sou_nr = m.group(1)
        _add(
            LegalReference(
                ref_type="sou",
                raw_match=m.group(0),
                display=f"SOU {sou_nr}",
            )
        )

    # 8. Ds references
    for m in _DS_RE.finditer(text):
        ds_nr = m.group(1)
        _add(
            LegalReference(
                ref_type="ds",
                raw_match=m.group(0),
                display=f"Ds {ds_nr}",
            )
        )

    # 9. Betänkande references
    for m in _BETANKANDE_RE.finditer(text):
        bet_nr = m.group(1)
        _add(
            LegalReference(
                ref_type="betankande",
                raw_match=m.group(0),
                display=f"bet. {bet_nr}",
            )
        )

    # 10. NJA references
    for m in _NJA_RE.finditer(text):
        year, page = m.group(1), m.group(2)
        _add(
            LegalReference(
                ref_type="nja",
                raw_match=m.group(0),
                display=f"NJA {year} s. {page}",
            )
        )

    # 11. HFD references
    for m in _HFD_RE.finditer(text):
        year, ref_num = m.group(1), m.group(2)
        _add(
            LegalReference(
                ref_type="hfd",
                raw_match=m.group(0),
                display=f"HFD {year} ref. {ref_num}",
            )
        )

    # 12. EU directive/regulation references
    for m in _EU_DIRECTIVE_RE.finditer(text):
        doc_type = m.group(1).lower()
        eu_nr = m.group(2)
        _add(
            LegalReference(
                ref_type="eu",
                raw_match=m.group(0),
                display=f"{doc_type} {eu_nr}",
            )
        )

    # 2. Implicit SFS references: "1974:152" (not already captured as explicit SFS)
    for m in _SFS_IMPLICIT_RE.finditer(text):
        sfs_nr = m.group(1)
        # Skip if already captured via explicit SFS pattern
        if f"sfs:SFS {sfs_nr}" in seen or f"sfs:SFS  {sfs_nr}" in seen:
            continue
        # Skip if this looks like it's part of a larger pattern already captured
        start = m.start()
        prefix = text[max(0, start - 5) : start].strip()
        if prefix.upper().endswith("SFS"):
            continue
        _add(
            LegalReference(
                ref_type="sfs",
                raw_match=m.group(0),
                target_sfs=sfs_nr,
                display=f"SFS {sfs_nr}",
            )
        )

    # 4. Simple section references: "3 §" (only if not part of kap. reference)
    for m in _SECTION_SIMPLE_RE.finditer(text):
        par = m.group(1)
        raw = m.group(0)
        # Skip if this § was already captured in a kap+§ pattern
        already_captured = False
        for ref in refs:
            if ref.ref_type == "section" and ref.target_section == par:
                already_captured = True
                break
        if already_captured:
            continue
        _add(
            LegalReference(
                ref_type="section",
                raw_match=raw,
                target_section=par,
                display=f"{par} §",
            )
        )

    return refs


def references_to_metadata(refs: list[LegalReference]) -> list[dict]:
    """
    Convert LegalReference objects to JSON-serializable dicts for ChromaDB/storage.

    Args:
        refs: List of LegalReference objects

    Returns:
        List of dicts suitable for JSON serialization
    """
    return [
        {
            "ref_type": r.ref_type,
            "raw_match": r.raw_match,
            "target_sfs": r.target_sfs,
            "target_chapter": r.target_chapter,
            "target_section": r.target_section,
            "display": r.display,
        }
        for r in refs
    ]
