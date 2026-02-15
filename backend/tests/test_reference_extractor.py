"""
Tests for reference_extractor.py — Swedish legal cross-reference extraction.
"""

from app.services.reference_extractor import (
    LegalReference,
    ORDINAL_MAP,
    extract_references,
    references_to_metadata,
)


class TestExtractReferences:
    """Test the main extract_references function."""

    def test_empty_input(self):
        assert extract_references("") == []
        assert extract_references("   ") == []
        assert extract_references(None) == []

    def test_no_references(self):
        text = "Det var en gång en kung som bodde i ett slott."
        assert extract_references(text) == []

    def test_explicit_sfs(self):
        text = "Enligt SFS 2009:400 ska handlingar vara offentliga."
        refs = extract_references(text)
        sfs_refs = [r for r in refs if r.ref_type == "sfs"]
        assert len(sfs_refs) >= 1
        assert sfs_refs[0].target_sfs == "2009:400"
        assert sfs_refs[0].display == "SFS 2009:400"

    def test_implicit_sfs(self):
        text = "I lagen (1974:152) stadgas grundläggande fri- och rättigheter."
        refs = extract_references(text)
        sfs_refs = [r for r in refs if r.ref_type == "sfs"]
        assert len(sfs_refs) >= 1
        assert any(r.target_sfs == "1974:152" for r in sfs_refs)

    def test_section_chapter(self):
        text = "Se 2 kap. 3 § om yttrandefrihet."
        refs = extract_references(text)
        section_refs = [r for r in refs if r.ref_type == "section"]
        assert len(section_refs) >= 1
        r = section_refs[0]
        assert r.target_chapter == "2"
        assert r.target_section == "3"

    def test_section_simple(self):
        text = "Enligt 5 § gäller följande."
        refs = extract_references(text)
        section_refs = [r for r in refs if r.ref_type == "section"]
        assert len(section_refs) >= 1
        assert section_refs[0].target_section == "5"

    def test_stycke_ordinal(self):
        text = "6 kap. 7 § första stycket anger att beslut ska motiveras."
        refs = extract_references(text)
        section_refs = [r for r in refs if r.ref_type == "section"]
        assert len(section_refs) >= 1
        r = section_refs[0]
        assert r.target_chapter == "6"
        assert r.target_section == "7"
        assert "första stycket" in r.display

    def test_proposition(self):
        text = "Se prop. 1997/98:45 om miljölagstiftning."
        refs = extract_references(text)
        prop_refs = [r for r in refs if r.ref_type == "proposition"]
        assert len(prop_refs) == 1
        assert prop_refs[0].display == "prop. 1997/98:45"

    def test_sou(self):
        text = "SOU 2020:47 behandlar digitalisering av offentlig förvaltning."
        refs = extract_references(text)
        sou_refs = [r for r in refs if r.ref_type == "sou"]
        assert len(sou_refs) == 1
        assert sou_refs[0].display == "SOU 2020:47"

    def test_ds(self):
        text = "Ds 2019:1 handlar om förslag till ny lagstiftning."
        refs = extract_references(text)
        ds_refs = [r for r in refs if r.ref_type == "ds"]
        assert len(ds_refs) == 1
        assert ds_refs[0].display == "Ds 2019:1"

    def test_betankande(self):
        text = "Se bet. 2019/20:KU10 för utskottets bedömning."
        refs = extract_references(text)
        bet_refs = [r for r in refs if r.ref_type == "betankande"]
        assert len(bet_refs) == 1
        assert bet_refs[0].display == "bet. 2019/20:KU10"

    def test_nja(self):
        text = "Högsta domstolen fastslog i NJA 2014 s. 323 att..."
        refs = extract_references(text)
        nja_refs = [r for r in refs if r.ref_type == "nja"]
        assert len(nja_refs) == 1
        assert nja_refs[0].display == "NJA 2014 s. 323"

    def test_hfd(self):
        text = "Enligt HFD 2018 ref. 51 ska myndigheten..."
        refs = extract_references(text)
        hfd_refs = [r for r in refs if r.ref_type == "hfd"]
        assert len(hfd_refs) == 1
        assert hfd_refs[0].display == "HFD 2018 ref. 51"

    def test_eu_directive(self):
        text = "förordning (EU) 2016/679 om skydd av personuppgifter."
        refs = extract_references(text)
        eu_refs = [r for r in refs if r.ref_type == "eu"]
        assert len(eu_refs) == 1
        assert "2016/679" in eu_refs[0].display

    def test_eu_directive_without_parenthesis(self):
        text = "direktiv 2006/24/EG om datalagring."
        refs = extract_references(text)
        eu_refs = [r for r in refs if r.ref_type == "eu"]
        assert len(eu_refs) == 1
        assert "2006/24/EG" in eu_refs[0].display

    def test_mixed_references(self):
        """Test text with multiple reference types."""
        text = (
            "Enligt 2 kap. 1 § regeringsformen (SFS 1974:152) och "
            "prop. 1975/76:209 ska yttrandefriheten skyddas. "
            "Se även NJA 2014 s. 323 och förordning (EU) 2016/679."
        )
        refs = extract_references(text)
        ref_types = {r.ref_type for r in refs}
        assert "section" in ref_types
        assert "sfs" in ref_types
        assert "proposition" in ref_types
        assert "nja" in ref_types
        assert "eu" in ref_types

    def test_deduplication(self):
        """Identical references should not be duplicated."""
        text = "SFS 2009:400 och SFS 2009:400 anger samma sak."
        refs = extract_references(text)
        sfs_refs = [r for r in refs if r.ref_type == "sfs" and r.target_sfs == "2009:400"]
        assert len(sfs_refs) == 1

    def test_section_a_paragraph(self):
        """Test 'a' suffixed section: '1 a kap. 3 §'."""
        text = "I 1a kap. 3 § finns bestämmelser om..."
        refs = extract_references(text)
        section_refs = [r for r in refs if r.ref_type == "section"]
        assert len(section_refs) >= 1
        assert section_refs[0].target_chapter == "1a"

    def test_false_positive_resistance_time(self):
        """Time references like '14:30' should not match as SFS."""
        text = "Mötet börjar kl. 14:30 och slutar kl. 16:00."
        refs = extract_references(text)
        sfs_refs = [r for r in refs if r.ref_type == "sfs"]
        # "14:30" has only 2-digit suffix, our pattern requires \d{2,} so it might match
        # but "14:30" is a time not an SFS — the pattern matches \d{4}:\d{2,}
        # 14:30 would not match since 14 is only 2 digits (need 4)
        assert len(sfs_refs) == 0

    def test_real_rf_text(self):
        """Test with real text from Regeringsformen."""
        text = (
            "1 § Varje medborgare är gentemot det allmänna tillförsäkrad\n"
            "1. yttrandefrihet: frihet att i tal, skrift eller bild eller på\n"
            "annat sätt meddela upplysningar samt uttrycka tankar, åsikter och\n"
            "känslor,\n"
            "2. informationsfrihet: frihet att inhämta och ta emot upplysningar\n"
            "samt att i övrigt ta del av andras yttranden,\n\n"
            "Lag (2010:1408).\n"
        )
        refs = extract_references(text)
        # Should extract simple section ref (1 §) and implicit SFS (2010:1408)
        assert any(r.ref_type == "section" for r in refs) or any(r.ref_type == "sfs" for r in refs)

    def test_real_osl_text(self):
        """Test with text referencing OSL."""
        text = (
            "Enligt 25 kap. 1 § offentlighets- och sekretesslagen (2009:400) "
            "gäller sekretess inom hälso- och sjukvården."
        )
        refs = extract_references(text)
        section_refs = [r for r in refs if r.ref_type == "section"]
        sfs_refs = [r for r in refs if r.ref_type == "sfs"]
        assert len(section_refs) >= 1
        assert section_refs[0].target_chapter == "25"
        assert section_refs[0].target_section == "1"
        assert len(sfs_refs) >= 1
        assert any(r.target_sfs == "2009:400" for r in sfs_refs)

    def test_real_mb_text(self):
        """Test with Miljöbalken cross-references."""
        text = (
            "Enligt 9 kap. 6 § miljöbalken (1998:808) krävs tillstånd. "
            "Se även prop. 1997/98:45 del 2 s. 77 och "
            "HFD 2018 ref. 51 om tillståndsprövning."
        )
        refs = extract_references(text)
        ref_types = {r.ref_type for r in refs}
        assert "section" in ref_types
        assert "sfs" in ref_types
        assert "proposition" in ref_types
        assert "hfd" in ref_types


class TestReferencesToMetadata:
    """Test the references_to_metadata serialization."""

    def test_empty_list(self):
        assert references_to_metadata([]) == []

    def test_serialization(self):
        refs = [
            LegalReference(
                ref_type="sfs",
                raw_match="SFS 2009:400",
                target_sfs="2009:400",
                display="SFS 2009:400",
            ),
            LegalReference(
                ref_type="section",
                raw_match="2 kap. 3 §",
                target_chapter="2",
                target_section="3",
                display="2 kap. 3 §",
            ),
        ]
        result = references_to_metadata(refs)
        assert len(result) == 2
        assert result[0]["ref_type"] == "sfs"
        assert result[0]["target_sfs"] == "2009:400"
        assert result[1]["ref_type"] == "section"
        assert result[1]["target_chapter"] == "2"
        # All fields should be present
        for item in result:
            assert "ref_type" in item
            assert "raw_match" in item
            assert "target_sfs" in item
            assert "target_chapter" in item
            assert "target_section" in item
            assert "display" in item


class TestOrdinalMap:
    """Test the ordinal mapping."""

    def test_all_ordinals(self):
        assert ORDINAL_MAP["första"] == 1
        assert ORDINAL_MAP["tionde"] == 10
        assert len(ORDINAL_MAP) == 10
