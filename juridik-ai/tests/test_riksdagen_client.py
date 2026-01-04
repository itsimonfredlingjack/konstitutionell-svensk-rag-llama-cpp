"""
Unit tests for RiksdagenClient module.

Run with: pytest tests/test_riksdagen_client.py -v
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from pipelines.riksdagen_client import (
    Document,
    DocumentType,
    RiksdagenClient,
)


class TestDocument:
    """Test Document class."""

    def test_document_creation(self):
        """Test creating a Document object."""
        doc = Document(dokid="1984:1234", titel="Test Document", doktyp="prop")
        assert doc.dokid == "1984:1234"
        assert doc.titel == "Test Document"
        assert doc.doktyp == "prop"

    def test_document_to_dict(self):
        """Test converting Document to dict."""
        doc = Document(dokid="1984:1234", titel="Test Document", subtitel="Subtitle", doktyp="prop")
        doc_dict = doc.to_dict()
        assert isinstance(doc_dict, dict)
        assert doc_dict["dokid"] == "1984:1234"
        assert doc_dict["titel"] == "Test Document"
        assert doc_dict["subtitel"] == "Subtitle"

    def test_document_optional_fields(self):
        """Test Document with optional fields."""
        doc = Document(dokid="1984:1234", titel="Test")
        assert doc.subtitel is None
        assert doc.doktyp is None
        assert doc.publicerad is None


class TestDocumentType:
    """Test DocumentType enum."""

    def test_document_types(self):
        """Test all document types are defined."""
        assert DocumentType.PROPOSITION.value == "prop"
        assert DocumentType.MOTION.value == "mot"
        assert DocumentType.SOU.value == "sou"
        assert DocumentType.BETANKANDE.value == "bet"
        assert DocumentType.INTERPELLATION.value == "ip"
        assert DocumentType.FRÅGA_UTAN_SVAR.value == "fsk"
        assert DocumentType.DIREKTIV.value == "dir"
        assert DocumentType.DEPARTEMENTSSKRIVELSE.value == "ds"
        assert DocumentType.SKRIVELSE.value == "skr"


class TestRiksdagenClientInit:
    """Test RiksdagenClient initialization."""

    def test_default_initialization(self):
        """Test client initialization with defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = RiksdagenClient(base_dir=tmpdir)
            assert client.base_dir == Path(tmpdir)
            assert client.rate_limit_delay == 0.5
            assert client.timeout == 30
            assert client.max_retries == 3

    def test_custom_initialization(self):
        """Test client initialization with custom parameters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = RiksdagenClient(
                base_dir=tmpdir, rate_limit_delay=1.0, timeout=60, max_retries=5
            )
            assert client.rate_limit_delay == 1.0
            assert client.timeout == 60
            assert client.max_retries == 5

    def test_base_dir_creation(self):
        """Test that base directory is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "new_dir"
            assert not base_dir.exists()

            client = RiksdagenClient(base_dir=str(base_dir))
            assert base_dir.exists()
            assert base_dir.is_dir()


class TestRiksdagenClientRateLimit:
    """Test rate limiting functionality."""

    def test_rate_limit_applied(self):
        """Test that rate limiting works."""
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            client = RiksdagenClient(base_dir=tmpdir, rate_limit_delay=0.1)

            start = time.time()
            client._rate_limit()
            client._rate_limit()
            elapsed = time.time() - start

            # Should be at least 0.1 seconds
            assert elapsed >= 0.1


class TestRiksdagenClientCheckpoint:
    """Test checkpoint functionality."""

    def test_save_checkpoint(self):
        """Test saving checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = RiksdagenClient(base_dir=tmpdir)

            checkpoint = {
                "downloaded": ["doc1", "doc2"],
                "failed": ["doc3"],
                "progress": 10,
                "total": 20,
            }

            client._save_checkpoint("test_task", checkpoint)

            checkpoint_file = Path(tmpdir) / ".checkpoint_test_task.json"
            assert checkpoint_file.exists()

            with open(checkpoint_file) as f:
                saved = json.load(f)
            assert saved == checkpoint

    def test_get_checkpoint(self):
        """Test loading checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = RiksdagenClient(base_dir=tmpdir)

            checkpoint = {"downloaded": ["doc1", "doc2"], "failed": [], "progress": 5}

            client._save_checkpoint("test_task", checkpoint)
            loaded = client._get_checkpoint("test_task")

            assert loaded == checkpoint

    def test_get_checkpoint_nonexistent(self):
        """Test getting nonexistent checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = RiksdagenClient(base_dir=tmpdir)
            checkpoint = client._get_checkpoint("nonexistent")
            assert checkpoint is None


class TestRiksdagenClientParseDocument:
    """Test document parsing."""

    def test_parse_document(self):
        """Test parsing document from API response."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = RiksdagenClient(base_dir=tmpdir)

            doc_data = {
                "dokid": "1984:1234",
                "titel": "Test Proposition",
                "subtitel": "Subtitle",
                "doktyp": "prop",
                "publicerad": "2024-01-15",
                "rm": "2023/24",
                "beteckning": "1984:1234",
                "dokumentstatus": "Fastställd",
                "dokument_url_text": "http://example.com/text",
                "dokument_url_html": "http://example.com/html",
                "dokument_url_pdf": "http://example.com/pdf",
                "dokstat": "samlat",
            }

            doc = client._parse_document(doc_data)

            assert doc.dokid == "1984:1234"
            assert doc.titel == "Test Proposition"
            assert doc.subtitel == "Subtitle"
            assert doc.doktyp == "prop"
            assert doc.publicerad == "2024-01-15"
            assert doc.rm == "2023/24"
            assert doc.beteckning == "1984:1234"
            assert doc.url == "http://example.com/text"
            assert doc.html_url == "http://example.com/html"
            assert doc.pdf_url == "http://example.com/pdf"

    def test_parse_document_minimal(self):
        """Test parsing document with minimal data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = RiksdagenClient(base_dir=tmpdir)

            doc_data = {"dokid": "1984:1234", "titel": "Test Document"}

            doc = client._parse_document(doc_data)

            assert doc.dokid == "1984:1234"
            assert doc.titel == "Test Document"
            assert doc.subtitel is None


class TestRiksdagenClientExportMetadata:
    """Test metadata export."""

    def test_export_metadata_default_filename(self):
        """Test exporting metadata with default filename."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = RiksdagenClient(base_dir=tmpdir)

            docs = [
                Document(dokid="1", titel="Doc 1"),
                Document(dokid="2", titel="Doc 2"),
            ]

            filepath = client.export_metadata(docs)

            assert Path(filepath).exists()
            with open(filepath) as f:
                data = json.load(f)
            assert data["total_documents"] == 2
            assert len(data["documents"]) == 2

    def test_export_metadata_custom_filename(self):
        """Test exporting metadata with custom filename."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = RiksdagenClient(base_dir=tmpdir)
            docs = [Document(dokid="1", titel="Doc 1")]
            output_file = str(Path(tmpdir) / "custom_metadata.json")

            filepath = client.export_metadata(docs, output_file=output_file)

            assert Path(filepath).exists()
            assert "custom_metadata" in filepath


class TestRiksdagenClientStatistics:
    """Test statistics functionality."""

    def test_statistics_empty(self):
        """Test statistics on empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = RiksdagenClient(base_dir=tmpdir)
            stats = client.get_statistics()

            assert stats["total_documents"] == 0
            assert stats["total_size_mb"] == 0.0
            assert stats["document_types"] == {}

    def test_statistics_with_documents(self):
        """Test statistics with downloaded documents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = RiksdagenClient(base_dir=tmpdir)

            # Create some test files
            prop_dir = Path(tmpdir) / "prop"
            prop_dir.mkdir()
            (prop_dir / "test1.pdf").write_bytes(b"x" * 1024)
            (prop_dir / "test2.pdf").write_bytes(b"x" * 2048)

            stats = client.get_statistics()

            assert stats["total_documents"] == 2
            assert "prop" in stats["document_types"]
            assert stats["document_types"]["prop"]["count"] == 2


class TestRiksdagenClientSession:
    """Test session logging."""

    def test_session_log_created(self):
        """Test that session log file is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = RiksdagenClient(base_dir=tmpdir)
            client._log_session("test_action", {"test": "data"})

            assert client.session_log_file.exists()

            with open(client.session_log_file) as f:
                lines = f.readlines()
            assert len(lines) == 1
            log_entry = json.loads(lines[0])
            assert log_entry["action"] == "test_action"
            assert log_entry["details"]["test"] == "data"


@pytest.mark.integration
class TestRiksdagenClientIntegration:
    """Integration tests (require API access)."""

    @patch("pipelines.riksdagen_client.requests.Session.get")
    def test_search_documents_mocked(self, mock_get):
        """Test search_documents with mocked API."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = RiksdagenClient(base_dir=tmpdir)

            # Mock API response
            mock_response = Mock()
            mock_response.json.return_value = {
                "dokument": [
                    {
                        "dokid": "1984:1234",
                        "titel": "Test Prop 1",
                        "doktyp": "prop",
                    },
                    {
                        "dokid": "1984:1235",
                        "titel": "Test Prop 2",
                        "doktyp": "prop",
                    },
                ]
            }
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            # Search
            docs = client.search_documents(
                doktyp="prop", year_from=2024, year_to=2024, max_results=10
            )

            assert len(docs) == 2
            assert docs[0].dokid == "1984:1234"
            assert docs[1].dokid == "1984:1235"

    @patch("pipelines.riksdagen_client.requests.Session.get")
    def test_get_document_mocked(self, mock_get):
        """Test get_document with mocked API."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = RiksdagenClient(base_dir=tmpdir)

            mock_response = Mock()
            mock_response.json.return_value = {
                "dokument": [
                    {
                        "dokid": "1984:1234",
                        "titel": "Test Proposition",
                        "doktyp": "prop",
                    }
                ]
            }
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            doc = client.get_document("1984:1234")

            assert doc is not None
            assert doc.dokid == "1984:1234"
            assert doc.titel == "Test Proposition"

    @patch("pipelines.riksdagen_client.requests.Session.get")
    def test_download_document_mocked(self, mock_get):
        """Test download_document with mocked API."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = RiksdagenClient(base_dir=tmpdir)

            # Create document
            doc = Document(
                dokid="1984:1234",
                titel="Test Document",
                doktyp="prop",
                pdf_url="http://example.com/doc.pdf",
            )

            # Mock PDF download
            mock_response = Mock()
            mock_response.iter_content.return_value = [b"PDF content"]
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            filepath = client.download_document(doc, file_format="pdf")

            assert filepath is not None
            assert filepath.exists()
            assert filepath.parent.name == "prop"

    @patch("pipelines.riksdagen_client.requests.Session.get")
    def test_download_all_mocked(self, mock_get):
        """Test download_all with mocked API."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = RiksdagenClient(base_dir=tmpdir)

            # Mock search response
            search_response = Mock()
            search_response.json.return_value = {
                "dokument": [
                    {
                        "dokid": f"1984:{1000+i}",
                        "titel": f"Document {i}",
                        "doktyp": "prop",
                        "dokument_url_pdf": f"http://example.com/doc{i}.pdf",
                    }
                    for i in range(3)
                ]
            }
            search_response.raise_for_status.return_value = None

            # Mock download response
            download_response = Mock()
            download_response.iter_content.return_value = [b"PDF"]
            download_response.raise_for_status.return_value = None

            # Alternate responses
            mock_get.side_effect = [
                search_response,
                download_response,
                download_response,
                download_response,
            ]

            total, downloaded, failed = client.download_all(
                doktyp="prop", year_range=(2024, 2024), file_format="pdf", resume=False
            )

            assert total == 3
            assert downloaded == 3
            assert len(failed) == 0


def test_imports():
    """Test that all classes and enums can be imported."""
    from pipelines.riksdagen_client import (
        Document,
        DocumentType,
        RiksdagenClient,
    )

    assert RiksdagenClient is not None
    assert Document is not None
    assert DocumentType is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
