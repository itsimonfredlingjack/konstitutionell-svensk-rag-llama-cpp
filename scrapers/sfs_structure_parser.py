"""
SFS Structure Parser — Structural annotations for Swedish legal text chunks
============================================================================

Pure-logic module for parsing legal text structure. No I/O dependencies.
Extracts stycken (sub-paragraphs), punkt (numbered items), cross-references,
and amendment references from individual paragraf text blocks.

Used by sfs_scraper.py to annotate chunks with structural metadata.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Data Structures ──────────────────────────────────────────────────


@dataclass
class PunktAnnotation:
    """A numbered or lettered item within a stycke."""

    number: int | str  # 1, 2, 3 or "a", "b", "c"
    text: str


@dataclass
class StyckeAnnotation:
    """A sub-paragraph (stycke) within a paragraf."""

    index: int  # 1-based
    text: str
    has_punkt: bool = False
    punkt: list[PunktAnnotation] = field(default_factory=list)


@dataclass
class CrossReference:
    """A cross-reference to another legal provision."""

    ref_type: str  # "internal" | "external" | "amendment"
    raw_text: str  # Original matched text, e.g. "30 kap. 1 §"
    target_kap: str | None = None
    target_paragraf: str | None = None
    target_sfs: str | None = None
    target_name: str | None = None


@dataclass
class ParagrafStructure:
    """Structural annotations for a single paragraf."""

    stycken: list[StyckeAnnotation] = field(default_factory=list)
    cross_refs: list[CrossReference] = field(default_factory=list)
    amendment_ref: str | None = None  # e.g. "Lag (2010:1408)"
    stycke_count: int = 0
    punkt_count: int = 0


# ── Named Grundlagar for External Cross-Reference Detection ─────────

# Map of grundlag names to their SFS numbers
_NAMED_GRUNDLAGAR = {
    "regeringsformen": "1974:152",
    "successionsordningen": "1810:0926",
    "tryckfrihetsförordningen": "1949:105",
    "yttrandefrihetsgrundlagen": "1991:1469",
    "riksdagsordningen": "2014:801",
}


# ── Compiled Regex Patterns ──────────────────────────────────────────

# Amendment ref at end of paragraf text: "Lag (2010:1408)" or "Lag (2010:1408)."
_AMENDMENT_RE = re.compile(
    r"(?:Lag|Förordning)\s*\(\d{4}:\d+\)\s*\.?\s*$",
    re.MULTILINE,
)

# Internal cross-reference: "30 kap. 1 §", "2 kap. 23 §", "1 a kap. 3 §"
_INTERNAL_XREF_RE = re.compile(
    r"(\d+[a-z]?\s*kap\.?\s+\d+[a-z]?\s*§)",
)

# External SFS reference: "lagen (1980:424)", "förordning (2003:234)", "balk (1962:700)"
_EXTERNAL_SFS_RE = re.compile(
    r"((?:lag(?:en)?|förordning(?:en)?|balk(?:en)?)\s*\(\d{4}:\d+\))",
    re.IGNORECASE,
)

# Extract SFS number from external ref: "(1980:424)"
_SFS_NUMBER_RE = re.compile(r"\((\d{4}:\d+)\)")

# Internal xref parts: extract kap and paragraf
_INTERNAL_PARTS_RE = re.compile(r"(\d+[a-z]?)\s*kap\.?\s+(\d+[a-z]?)\s*§")

# Numeric punkt: "1. text", "2. text" etc. at start of line
_NUMERIC_PUNKT_RE = re.compile(r"^(\d+)\.\s+(.+)", re.MULTILINE)

# Lettered punkt: "a) text", "b) text" etc. at start of line
_LETTER_PUNKT_RE = re.compile(r"^([a-z])\)\s+(.+)", re.MULTILINE)

# Paragraf header pattern to strip from first stycke: "1 § " or "23 a § "
_PARAGRAF_HEADER_RE = re.compile(r"^\d+[a-z]?\s*§\s*")


# ── Parsing Functions ────────────────────────────────────────────────


def _extract_amendment_ref(text: str) -> tuple[str | None, str]:
    """
    Extract trailing amendment reference from paragraf text.

    Returns:
        Tuple of (amendment_ref or None, text with amendment stripped)
    """
    match = _AMENDMENT_RE.search(text)
    if match:
        amendment = match.group(0).rstrip(". ")
        cleaned = text[: match.start()].rstrip()
        return amendment, cleaned
    return None, text


def _extract_cross_references(text: str) -> list[CrossReference]:
    """
    Extract all cross-references from paragraf text.

    Detects:
    - Internal refs: "30 kap. 1 §"
    - External SFS refs: "lagen (1980:424)"
    - Named grundlagar: "tryckfrihetsförordningen"
    """
    refs: list[CrossReference] = []
    seen: set[str] = set()

    # Internal cross-references
    for match in _INTERNAL_XREF_RE.finditer(text):
        raw = match.group(1)
        if raw in seen:
            continue
        seen.add(raw)

        parts = _INTERNAL_PARTS_RE.match(raw)
        kap = parts.group(1) if parts else None
        par = parts.group(2) if parts else None

        refs.append(
            CrossReference(
                ref_type="internal",
                raw_text=raw,
                target_kap=f"{kap} kap." if kap else None,
                target_paragraf=f"{par} §" if par else None,
            )
        )

    # External SFS references
    for match in _EXTERNAL_SFS_RE.finditer(text):
        raw = match.group(1)
        if raw in seen:
            continue
        seen.add(raw)

        sfs_match = _SFS_NUMBER_RE.search(raw)
        sfs_nr = sfs_match.group(1) if sfs_match else None

        refs.append(
            CrossReference(
                ref_type="external",
                raw_text=raw,
                target_sfs=sfs_nr,
            )
        )

    # Named grundlagar
    text_lower = text.lower()
    for name, sfs_nr in _NAMED_GRUNDLAGAR.items():
        if name in text_lower:
            if name in seen:
                continue
            seen.add(name)
            refs.append(
                CrossReference(
                    ref_type="external",
                    raw_text=name,
                    target_sfs=sfs_nr,
                    target_name=name,
                )
            )

    return refs


def _parse_punkt_in_stycke(text: str) -> list[PunktAnnotation]:
    """
    Extract numbered or lettered items from a stycke text.

    Detects:
    - Numeric: "1. text", "2. text"
    - Lettered: "a) text", "b) text"
    """
    # Try numeric first
    numeric_matches = list(_NUMERIC_PUNKT_RE.finditer(text))
    if numeric_matches:
        return [
            PunktAnnotation(number=int(m.group(1)), text=m.group(2).strip())
            for m in numeric_matches
        ]

    # Try lettered
    letter_matches = list(_LETTER_PUNKT_RE.finditer(text))
    if letter_matches:
        return [PunktAnnotation(number=m.group(1), text=m.group(2).strip()) for m in letter_matches]

    return []


def _split_stycken(text: str) -> list[str]:
    """
    Split paragraf text into stycken (sub-paragraphs).

    Stycken are separated by blank lines (\\n\\n).
    Strips the paragraf header ("1 §") from the first stycke.
    """
    # Split on blank lines
    raw_blocks = re.split(r"\n\s*\n", text)

    # Filter empty blocks and strip whitespace
    blocks = [b.strip() for b in raw_blocks if b.strip()]

    if not blocks:
        return []

    # Strip paragraf header from first block
    blocks[0] = _PARAGRAF_HEADER_RE.sub("", blocks[0]).strip()

    # Filter out blocks that became empty after stripping
    return [b for b in blocks if b]


def parse_paragraf_structure(text: str) -> ParagrafStructure:
    """
    Parse structural annotations from a paragraf text block.

    This is the main entry point for the structure parser.

    Args:
        text: Raw paragraf text (as extracted by sfs_scraper chunk_by_paragraph)

    Returns:
        ParagrafStructure with stycken, cross-references, and amendment info
    """
    if not text or not text.strip():
        return ParagrafStructure()

    # Extract amendment reference (remove from text for further parsing)
    amendment_ref, cleaned_text = _extract_amendment_ref(text)

    # Extract cross-references (from original text, amendment may contain refs)
    cross_refs = _extract_cross_references(text)

    # Split into stycken
    stycke_texts = _split_stycken(cleaned_text)

    stycken: list[StyckeAnnotation] = []
    total_punkt_count = 0

    for i, st_text in enumerate(stycke_texts, 1):
        punkt_items = _parse_punkt_in_stycke(st_text)
        total_punkt_count += len(punkt_items)

        stycken.append(
            StyckeAnnotation(
                index=i,
                text=st_text,
                has_punkt=bool(punkt_items),
                punkt=punkt_items,
            )
        )

    return ParagrafStructure(
        stycken=stycken,
        cross_refs=cross_refs,
        amendment_ref=amendment_ref,
        stycke_count=len(stycken),
        punkt_count=total_punkt_count,
    )
