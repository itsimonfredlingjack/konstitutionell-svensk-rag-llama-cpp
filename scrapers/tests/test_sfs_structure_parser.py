"""
Tests for sfs_structure_parser — structural annotations for SFS legal text.

Tests use realistic SFS text patterns from actual Swedish laws.
"""

import sys
from pathlib import Path

# Add scrapers directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sfs_structure_parser import (
    parse_paragraf_structure,
)

# ── RF 1 kap. 1 § — 3 stycken, no punkt, no cross-refs ─────────


RF_1_1_TEXT = """\
1 §  All offentlig makt i Sverige utgår från folket.

Den svenska folkstyrelsen bygger på fri åsiktsbildning och på allmän och lika rösträtt. Den förverkligas genom ett representativt och parlamentariskt statsskick och genom kommunal självstyrelse.

Den offentliga makten utövas under lagarna."""


def test_rf_1_1_stycke_count():
    result = parse_paragraf_structure(RF_1_1_TEXT)
    assert result.stycke_count == 3


def test_rf_1_1_first_stycke_stripped():
    """First stycke should have paragraf header stripped."""
    result = parse_paragraf_structure(RF_1_1_TEXT)
    first = result.stycken[0]
    assert not first.text.startswith("1 §")
    assert first.text.startswith("All offentlig makt")


def test_rf_1_1_no_punkt():
    result = parse_paragraf_structure(RF_1_1_TEXT)
    assert result.punkt_count == 0
    for st in result.stycken:
        assert st.has_punkt is False


def test_rf_1_1_no_cross_refs():
    result = parse_paragraf_structure(RF_1_1_TEXT)
    assert result.cross_refs == []


def test_rf_1_1_no_amendment():
    result = parse_paragraf_structure(RF_1_1_TEXT)
    assert result.amendment_ref is None


# ── RF 2 kap. 1 § — stycke with numbered punkt items ────────────


RF_2_1_TEXT = """\
1 §  Var och en är gentemot det allmänna tillförsäkrad

1. yttrandefrihet: frihet att i tal, skrift eller bild eller på annat sätt meddela upplysningar samt uttrycka tankar, åsikter och känslor,
2. informationsfrihet: frihet att inhämta och ta emot upplysningar samt att i övrigt ta del av andras yttranden,
3. mötesfrihet: frihet att anordna och delta i sammankomster för upplysning, meningsyttring eller annat liknande ändamål eller för framförande av konstnärligt verk,
4. demonstrationsfrihet: frihet att anordna och delta i demonstrationer på allmän plats,
5. föreningsfrihet: frihet att sammansluta sig med andra för allmänna eller enskilda syften, och
6. religionsfrihet: frihet att ensam eller tillsammans med andra utöva sin religion."""


def test_rf_2_1_has_punkt():
    result = parse_paragraf_structure(RF_2_1_TEXT)
    assert result.punkt_count == 6


def test_rf_2_1_punkt_numbers():
    result = parse_paragraf_structure(RF_2_1_TEXT)
    # Find the stycke that has punkt
    punkt_stycke = [st for st in result.stycken if st.has_punkt]
    assert len(punkt_stycke) >= 1
    punkt_nums = [p.number for p in punkt_stycke[0].punkt]
    assert punkt_nums == [1, 2, 3, 4, 5, 6]


def test_rf_2_1_punkt_text_content():
    result = parse_paragraf_structure(RF_2_1_TEXT)
    punkt_stycke = next(st for st in result.stycken if st.has_punkt)
    # First punkt should contain "yttrandefrihet"
    assert "yttrandefrihet" in punkt_stycke.punkt[0].text


# ── BrB 1 kap. 5 § — internal cross-reference ───────────────────


BRB_1_5_TEXT = """\
5 §  För brott som någon begått innan han fyllt femton år får inte dömas till påföljd.

I fråga om den som har begått brott efter det att han fyllt femton men innan han fyllt tjugoett år gäller särskilda bestämmelser i 30 kap. 1 §."""


def test_brb_1_5_internal_cross_ref():
    result = parse_paragraf_structure(BRB_1_5_TEXT)
    assert len(result.cross_refs) >= 1
    internal_refs = [r for r in result.cross_refs if r.ref_type == "internal"]
    assert len(internal_refs) == 1
    ref = internal_refs[0]
    assert ref.target_kap == "30 kap."
    assert ref.target_paragraf == "1 §"


def test_brb_1_5_two_stycken():
    result = parse_paragraf_structure(BRB_1_5_TEXT)
    assert result.stycke_count == 2


# ── RF 1 kap. 3 § — named external references ───────────────────


RF_1_3_TEXT = """\
3 §  Regeringsformen, successionsordningen, tryckfrihetsförordningen och yttrandefrihetsgrundlagen är rikets grundlagar. Lag (2010:1408)."""


def test_rf_1_3_named_external_refs():
    result = parse_paragraf_structure(RF_1_3_TEXT)
    external_refs = [r for r in result.cross_refs if r.ref_type == "external"]
    # Should find successionsordningen, tryckfrihetsförordningen, yttrandefrihetsgrundlagen, regeringsformen
    names_found = {r.target_name for r in external_refs if r.target_name}
    assert "successionsordningen" in names_found
    assert "tryckfrihetsförordningen" in names_found
    assert "yttrandefrihetsgrundlagen" in names_found
    assert "regeringsformen" in names_found


def test_rf_1_3_amendment_ref():
    result = parse_paragraf_structure(RF_1_3_TEXT)
    assert result.amendment_ref is not None
    assert "2010:1408" in result.amendment_ref


# ── Amendment reference extraction ───────────────────────────────


AMENDMENT_TEXT = """\
1 §  Denna lag innehåller bestämmelser om förvaltningsförfarandet.

Lagen gäller för handläggning av ärenden hos förvaltningsmyndigheterna och handläggning av förvaltningsärenden hos domstolarna. Lag (2017:900)."""


def test_amendment_extraction():
    result = parse_paragraf_structure(AMENDMENT_TEXT)
    assert result.amendment_ref is not None
    assert "2017:900" in result.amendment_ref


def test_amendment_stripped_from_stycken():
    """Amendment ref should be stripped from the last stycke text."""
    result = parse_paragraf_structure(AMENDMENT_TEXT)
    last_stycke = result.stycken[-1]
    assert "Lag (2017:900)" not in last_stycke.text


# ── External SFS reference ───────────────────────────────────────


EXTERNAL_SFS_TEXT = """\
2 §  Den som döms för brott ska straffas enligt lagen (1962:700) om brottsbalken."""


def test_external_sfs_ref():
    result = parse_paragraf_structure(EXTERNAL_SFS_TEXT)
    external_refs = [r for r in result.cross_refs if r.ref_type == "external"]
    assert len(external_refs) >= 1
    ref = external_refs[0]
    assert ref.target_sfs == "1962:700"


# ── Lettered punkt ───────────────────────────────────────────────


LETTERED_PUNKT_TEXT = """\
3 §  Följande handlingar ska vara offentliga:

a) protokoll från sammanträden
b) beslut som fattats av myndigheten
c) inkomna handlingar"""


def test_lettered_punkt():
    result = parse_paragraf_structure(LETTERED_PUNKT_TEXT)
    assert result.punkt_count == 3
    punkt_stycke = next(st for st in result.stycken if st.has_punkt)
    assert punkt_stycke.punkt[0].number == "a"
    assert punkt_stycke.punkt[1].number == "b"
    assert punkt_stycke.punkt[2].number == "c"


# ── Empty/edge cases ────────────────────────────────────────────


def test_empty_text():
    result = parse_paragraf_structure("")
    assert result.stycke_count == 0
    assert result.punkt_count == 0
    assert result.cross_refs == []


def test_whitespace_only():
    result = parse_paragraf_structure("   \n\n  ")
    assert result.stycke_count == 0


def test_single_line():
    result = parse_paragraf_structure("1 §  Kort paragraf.")
    assert result.stycke_count == 1
    assert result.stycken[0].text == "Kort paragraf."


# ── SO article format passthrough ────────────────────────────────


SO_ARTICLE_TEXT = """\
Art. 1  Konungariket Swerige skall styras af en Konung och vara ett arfrike med Succession uti den ordning, som denne Successions-Act bestämmer."""


def test_so_article_passthrough():
    """SO articles don't have paragraf headers, parser should handle gracefully."""
    result = parse_paragraf_structure(SO_ARTICLE_TEXT)
    # Should create 1 stycke from the text
    assert result.stycke_count == 1
    assert "Konungariket" in result.stycken[0].text


# ── Stycke indexing ──────────────────────────────────────────────


def test_stycke_indices_are_1_based():
    result = parse_paragraf_structure(RF_1_1_TEXT)
    indices = [st.index for st in result.stycken]
    assert indices == [1, 2, 3]


# ── Multiple cross-reference types ──────────────────────────────


MIXED_REFS_TEXT = """\
4 §  Bestämmelser om tryckfriheten finns i tryckfrihetsförordningen.
Undantag anges i 12 kap. 3 § och i lagen (2009:400)."""


def test_mixed_cross_refs():
    result = parse_paragraf_structure(MIXED_REFS_TEXT)
    ref_types = {r.ref_type for r in result.cross_refs}
    assert "internal" in ref_types  # "12 kap. 3 §"
    assert "external" in ref_types  # "lagen (2009:400)" and "tryckfrihetsförordningen"
