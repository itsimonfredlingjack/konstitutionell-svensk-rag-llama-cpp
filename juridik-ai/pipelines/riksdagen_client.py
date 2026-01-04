"""
Riksdagen Open Data API Client

A module for fetching and downloading documents from the Swedish Parliament's
(Riksdagen) open data API. Supports querying various document types, pagination,
rate limiting, and resume capabilities.

API Documentation: http://data.riksdagen.se/
"""

import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DocumentType(str, Enum):
    """Supported document types in Riksdagen."""

    PROPOSITION = "prop"  # Proposition (Government bill)
    MOTION = "mot"  # Motion (Parliamentary motion)
    SOU = "sou"  # Government investigation report
    BETANKANDE = "bet"  # Committee report
    INTERPELLATION = "ip"  # Interpellation
    FRÅGA_UTAN_SVAR = "fsk"  # Question for written reply
    DIREKTIV = "dir"  # Directive
    DEPARTEMENTSSKRIVELSE = "ds"  # Department memo
    SKRIVELSE = "skr"  # Written statement


@dataclass
class Document:
    """Represents a document from Riksdagen."""

    dokid: str
    titel: str
    subtitel: Optional[str] = None
    doktyp: Optional[str] = None
    publicerad: Optional[str] = None
    rm: Optional[str] = None
    beteckning: Optional[str] = None
    dokumentstatus: Optional[str] = None
    url: Optional[str] = None
    html_url: Optional[str] = None
    pdf_url: Optional[str] = None
    dokstat: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert document to dictionary."""
        return asdict(self)


class RiksdagenClient:
    """
    Client for accessing Riksdagen's open data API.

    Supports searching, filtering, and downloading documents with rate limiting
    and resume capabilities.
    """

    BASE_URL = "http://data.riksdagen.se"
    DOKUMENTLISTA_ENDPOINT = "/dokumentlista/"
    DEFAULT_PAGE_SIZE = 100
    MAX_PAGE_SIZE = 500

    def __init__(
        self,
        base_dir: str = "/home/dev/juridik-ai/data/riksdagen",
        rate_limit_delay: float = 0.5,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        """
        Initialize the Riksdagen client.

        Args:
            base_dir: Base directory for saving documents
            rate_limit_delay: Delay between requests in seconds (be nice to the API)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
        """
        self.base_dir = Path(base_dir)
        self.rate_limit_delay = rate_limit_delay
        self.timeout = timeout
        self.max_retries = max_retries

        # Ensure base directory exists
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # Setup session with retries
        self.session = self._create_session()

        # Track state
        self.last_request_time = 0
        self.session_log_file = self.base_dir / "session.log"

    def _create_session(self) -> requests.Session:
        """Create a requests session with retry strategy."""
        session = requests.Session()

        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def _rate_limit(self) -> None:
        """Apply rate limiting to be respectful to the API."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - elapsed
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    def _log_session(self, action: str, details: dict[str, Any]) -> None:
        """Log session activity for resume capability."""
        with open(self.session_log_file, "a") as f:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "action": action,
                "details": details,
            }
            f.write(json.dumps(log_entry) + "\n")

    def _get_checkpoint(self, task_key: str) -> Optional[dict[str, Any]]:
        """Load the last checkpoint for a task to enable resume."""
        checkpoint_file = self.base_dir / f".checkpoint_{task_key}.json"
        if checkpoint_file.exists():
            try:
                with open(checkpoint_file) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load checkpoint: {e}")
        return None

    def _save_checkpoint(self, task_key: str, checkpoint: dict[str, Any]) -> None:
        """Save checkpoint for resume capability."""
        checkpoint_file = self.base_dir / f".checkpoint_{task_key}.json"
        try:
            with open(checkpoint_file, "w") as f:
                json.dump(checkpoint, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")

    def search_documents(
        self,
        doktyp: str,
        year_from: int = 2020,
        year_to: int = 2024,
        search_term: Optional[str] = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_results: Optional[int] = None,
    ) -> list[Document]:
        """
        Search for documents in Riksdagen.

        Args:
            doktyp: Document type (prop, mot, sou, bet, ip, fsk, dir, ds, skr)
            year_from: Start year (e.g., 2020)
            year_to: End year (e.g., 2024)
            search_term: Optional search term
            page_size: Results per page (1-500)
            max_results: Maximum total results to fetch (None = all)

        Returns:
            List of Document objects
        """
        if page_size > self.MAX_PAGE_SIZE:
            logger.warning(f"Page size {page_size} exceeds max {self.MAX_PAGE_SIZE}, capping...")
            page_size = self.MAX_PAGE_SIZE

        documents = []
        current_page = 1
        total_fetched = 0

        while True:
            # Apply rate limiting
            self._rate_limit()

            # Build query parameters
            params = {
                "doktyp": doktyp,
                "sz": page_size,
                "utformat": "json",
                "sid": current_page,
            }

            # Add year range as riksmöte (parliament session)
            # Riksmöte format is "YYYY/YY" e.g. "2023/24"
            session_ids = []
            for year in range(year_from, year_to + 1):
                next_year = str(year + 1)[-2:]
                session_ids.append(f"{year}/{next_year}")
            params["rm"] = ",".join(session_ids)

            # Add search term if provided
            if search_term:
                params["sok"] = search_term

            try:
                logger.info(f"Fetching page {current_page} for doktyp={doktyp}")
                response = self.session.get(
                    f"{self.BASE_URL}{self.DOKUMENTLISTA_ENDPOINT}",
                    params=params,
                    timeout=self.timeout,
                )
                response.raise_for_status()

                data = response.json()

                if "dokument" not in data:
                    logger.warning(f"No documents in response for page {current_page}")
                    break

                page_docs = data["dokument"]
                if not page_docs:
                    logger.info(f"Empty page {current_page}, stopping pagination")
                    break

                # Parse documents
                for doc_data in page_docs:
                    doc = self._parse_document(doc_data)
                    documents.append(doc)
                    total_fetched += 1

                    if max_results and total_fetched >= max_results:
                        logger.info(f"Reached max_results limit of {max_results}")
                        return documents

                # Check if we got fewer results than page size (last page)
                if len(page_docs) < page_size:
                    logger.info(f"Reached last page with {len(page_docs)} documents")
                    break

                current_page += 1

            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed for page {current_page}: {e}")
                self._log_session(
                    "search_failed", {"doktyp": doktyp, "page": current_page, "error": str(e)}
                )
                break

        logger.info(f"Fetched {len(documents)} documents for doktyp={doktyp}")
        return documents

    def _parse_document(self, doc_data: dict[str, Any]) -> Document:
        """Parse document data from API response."""
        return Document(
            dokid=doc_data.get("dokid", ""),
            titel=doc_data.get("titel", ""),
            subtitel=doc_data.get("subtitel"),
            doktyp=doc_data.get("doktyp"),
            publicerad=doc_data.get("publicerad"),
            rm=doc_data.get("rm"),
            beteckning=doc_data.get("beteckning"),
            dokumentstatus=doc_data.get("dokumentstatus"),
            url=doc_data.get("dokument_url_text"),
            html_url=doc_data.get("dokument_url_html"),
            pdf_url=doc_data.get("dokument_url_pdf"),
            dokstat=doc_data.get("dokstat"),
        )

    def get_document(self, doc_id: str) -> Optional[Document]:
        """
        Fetch a single document by ID.

        Args:
            doc_id: Document ID (dokid)

        Returns:
            Document object or None if not found
        """
        self._rate_limit()

        try:
            logger.info(f"Fetching document {doc_id}")
            params = {"dokid": doc_id, "utformat": "json"}

            response = self.session.get(
                f"{self.BASE_URL}{self.DOKUMENTLISTA_ENDPOINT}", params=params, timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            if data.get("dokument"):
                return self._parse_document(data["dokument"][0])
            else:
                logger.warning(f"Document {doc_id} not found")
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch document {doc_id}: {e}")
            return None

    def download_document(self, document: Document, file_format: str = "pdf") -> Optional[Path]:
        """
        Download a document's content.

        Args:
            document: Document object to download
            file_format: File format ('pdf', 'html', 'text')

        Returns:
            Path to downloaded file or None if failed
        """
        # Determine URL based on format
        if file_format == "pdf" and document.pdf_url:
            url = document.pdf_url
            ext = ".pdf"
        elif file_format == "html" and document.html_url:
            url = document.html_url
            ext = ".html"
        elif file_format == "text" and document.url:
            url = document.url
            ext = ".txt"
        else:
            logger.warning(f"No {file_format} URL available for {document.dokid}")
            return None

        # Create output directory
        doc_type_dir = self.base_dir / (document.doktyp or "unknown")
        doc_type_dir.mkdir(parents=True, exist_ok=True)

        # Create filename from dokid and title
        safe_title = "".join(c for c in document.titel if c.isalnum() or c in " -_")[:50]
        filename = f"{document.dokid}_{safe_title}{ext}"
        filepath = doc_type_dir / filename

        # Skip if already exists
        if filepath.exists():
            logger.info(f"Document already exists: {filepath}")
            return filepath

        self._rate_limit()

        try:
            logger.info(f"Downloading {document.dokid} to {filepath}")
            response = self.session.get(url, timeout=self.timeout, stream=True)
            response.raise_for_status()

            # Write file
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            logger.info(f"Successfully downloaded: {filepath}")
            self._log_session(
                "download_success",
                {
                    "dokid": document.dokid,
                    "filepath": str(filepath),
                    "size": filepath.stat().st_size,
                },
            )
            return filepath

        except Exception as e:
            logger.error(f"Failed to download {document.dokid}: {e}")
            self._log_session("download_failed", {"dokid": document.dokid, "error": str(e)})
            if filepath.exists():
                filepath.unlink()
            return None

    def download_all(
        self,
        doktyp: str,
        year_range: tuple[int, int],
        file_format: str = "pdf",
        search_term: Optional[str] = None,
        resume: bool = True,
    ) -> tuple[int, int, list[str]]:
        """
        Download all documents of a specific type within a year range.

        Args:
            doktyp: Document type (prop, mot, sou, bet, ip, fsk, dir, ds, skr)
            year_range: Tuple of (year_from, year_to)
            file_format: File format to download (pdf, html, text)
            search_term: Optional search term to filter documents
            resume: Enable resume capability using checkpoints

        Returns:
            Tuple of (total_docs, downloaded_count, failed_docs)
        """
        year_from, year_to = year_range
        task_key = f"download_{doktyp}_{year_from}_{year_to}"

        # Check for existing checkpoint
        downloaded_docs = set()
        failed_docs = []

        if resume:
            checkpoint = self._get_checkpoint(task_key)
            if checkpoint:
                logger.info(f"Resuming from checkpoint: {checkpoint}")
                downloaded_docs = set(checkpoint.get("downloaded", []))
                failed_docs = checkpoint.get("failed", [])

        try:
            # Search for documents
            logger.info(f"Searching for {doktyp} documents ({year_from}-{year_to})")
            documents = self.search_documents(
                doktyp=doktyp,
                year_from=year_from,
                year_to=year_to,
                search_term=search_term,
                page_size=self.MAX_PAGE_SIZE,
            )

            logger.info(f"Found {len(documents)} documents")
            total_docs = len(documents)

            # Download each document
            for i, doc in enumerate(documents, 1):
                if doc.dokid in downloaded_docs:
                    logger.debug(f"Skipping already downloaded: {doc.dokid}")
                    continue

                if doc.dokid in failed_docs:
                    logger.debug(f"Skipping previously failed: {doc.dokid}")
                    continue

                logger.info(f"[{i}/{total_docs}] Downloading {doc.dokid}")

                filepath = self.download_document(doc, file_format=file_format)

                if filepath:
                    downloaded_docs.add(doc.dokid)
                else:
                    failed_docs.append(doc.dokid)

                # Save checkpoint every 10 documents
                if i % 10 == 0:
                    self._save_checkpoint(
                        task_key,
                        {
                            "downloaded": list(downloaded_docs),
                            "failed": failed_docs,
                            "progress": i,
                            "total": total_docs,
                            "timestamp": datetime.now().isoformat(),
                        },
                    )

            # Final checkpoint
            self._save_checkpoint(
                task_key,
                {
                    "downloaded": list(downloaded_docs),
                    "failed": failed_docs,
                    "progress": total_docs,
                    "total": total_docs,
                    "timestamp": datetime.now().isoformat(),
                    "completed": True,
                },
            )

            logger.info(
                f"Download complete: {len(downloaded_docs)}/{total_docs} successful, "
                f"{len(failed_docs)} failed"
            )

            return (total_docs, len(downloaded_docs), failed_docs)

        except Exception as e:
            logger.error(f"Download operation failed: {e}")
            raise

    def export_metadata(self, documents: list[Document], output_file: Optional[str] = None) -> str:
        """
        Export document metadata to JSON.

        Args:
            documents: List of Document objects
            output_file: Output file path (optional)

        Returns:
            Path to output file
        """
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = str(self.base_dir / f"metadata_{timestamp}.json")

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        metadata = {
            "exported": datetime.now().isoformat(),
            "total_documents": len(documents),
            "documents": [doc.to_dict() for doc in documents],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        logger.info(f"Exported metadata for {len(documents)} documents to {output_path}")
        return str(output_path)

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about downloaded documents."""
        stats = {
            "base_dir": str(self.base_dir),
            "document_types": {},
            "total_documents": 0,
            "total_size_mb": 0.0,
        }

        if not self.base_dir.exists():
            return stats

        for doc_type_dir in self.base_dir.iterdir():
            if doc_type_dir.is_dir() and not doc_type_dir.name.startswith("."):
                doc_count = 0
                doc_size = 0

                for file in doc_type_dir.rglob("*"):
                    if file.is_file() and not file.name.startswith("."):
                        doc_count += 1
                        doc_size += file.stat().st_size

                if doc_count > 0:
                    stats["document_types"][doc_type_dir.name] = {
                        "count": doc_count,
                        "size_mb": round(doc_size / (1024 * 1024), 2),
                    }
                    stats["total_documents"] += doc_count
                    stats["total_size_mb"] += doc_size / (1024 * 1024)

        stats["total_size_mb"] = round(stats["total_size_mb"], 2)
        return stats


def main():
    """Example usage of RiksdagenClient."""

    # Initialize client
    client = RiksdagenClient()

    # Example 1: Search for propositions from 2023-2024
    logger.info("Example 1: Searching for propositions...")
    docs = client.search_documents(doktyp="prop", year_from=2023, year_to=2024, max_results=10)
    logger.info(f"Found {len(docs)} documents")

    # Example 2: Export metadata
    if docs:
        metadata_file = client.export_metadata(docs)
        logger.info(f"Metadata exported to {metadata_file}")

    # Example 3: Download all motions from 2024
    logger.info("Example 3: Downloading motions...")
    total, downloaded, failed = client.download_all(
        doktyp="mot", year_range=(2024, 2024), file_format="pdf", resume=True
    )
    logger.info(f"Download results: {downloaded}/{total} successful, {len(failed)} failed")

    # Example 4: Get statistics
    logger.info("Example 4: Getting statistics...")
    stats = client.get_statistics()
    logger.info(f"Statistics: {json.dumps(stats, indent=2)}")


if __name__ == "__main__":
    main()
