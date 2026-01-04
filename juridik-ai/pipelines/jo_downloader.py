#!/usr/bin/env python3
"""
Download JO (Justitieombudsmans) ämbetsberättelser (annual reports) PDFs.

This script downloads official reports from Jo.se and optionally from Riksdagen.
It handles rate limiting, resume functionality, and maintains a download log.
"""

import argparse
import json
import logging
import time
from datetime import datetime
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class JODownloader:
    """Download JO ämbetsberättelser PDFs with rate limiting and resumption support."""

    # Known URL patterns for JO reports
    JO_BASE_URL = "https://www.jo.se/app/uploads"
    RIKSDAGEN_BASE_URL = "https://data.riksdagen.se/fil"

    # Known filenames for recent years (year -> filename mapping)
    KNOWN_FILES = {
        2024: "ambetsberattelse_2024.pdf",
        2023: "ambetsberattelse_2023.pdf",
        2022: "ambetsberattelse_2022.pdf",
        2021: "ambetsberattelse_2021.pdf",
        2020: "ambetsberattelse_2020.pdf",
        2019: "ambetsberattelse_2019.pdf",
        2018: "ambetsberattelse_2018.pdf",
        2017: "ambetsberattelse_2017.pdf",
        2016: "ambetsberattelse_2016.pdf",
        2015: "ambetsberattelse_2015.pdf",
    }

    def __init__(
        self,
        output_dir: str = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/juridik-ai/data/jo/",
        rate_limit_delay: float = 2.0,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        """
        Initialize the downloader.

        Args:
            output_dir: Directory to save PDFs
            rate_limit_delay: Seconds to wait between requests
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts per file
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.rate_limit_delay = rate_limit_delay
        self.timeout = timeout
        self.max_retries = max_retries

        # Metadata file to track downloads
        self.metadata_file = self.output_dir / "download_metadata.json"
        self.metadata = self._load_metadata()

        # Setup session with retry strategy
        self.session = self._setup_session()

        logger.info(f"JO Downloader initialized. Output dir: {self.output_dir}")

    def _setup_session(self) -> requests.Session:
        """Create requests session with retry strategy."""
        session = requests.Session()

        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set user agent
        session.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})

        return session

    def _load_metadata(self) -> dict:
        """Load download metadata from file."""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Could not load metadata: {e}. Starting fresh.")
                return {}
        return {}

    def _save_metadata(self) -> None:
        """Save download metadata to file."""
        try:
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump(self.metadata, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.error(f"Failed to save metadata: {e}")

    def _is_file_downloaded(self, year: int) -> bool:
        """Check if a file is already downloaded and complete."""
        filename = f"jo_ambetsberattelse_{year}.pdf"
        filepath = self.output_dir / filename

        if not filepath.exists():
            return False

        # Check metadata
        if str(year) in self.metadata:
            record = self.metadata[str(year)]
            if record.get("status") == "completed" and filepath.stat().st_size > 1000:
                logger.info(
                    f"Year {year} already downloaded (size: {filepath.stat().st_size} bytes)"
                )
                return True

        return False

    def _find_download_url(self, year: int) -> tuple[str, str, bool]:
        """
        Find the download URL for a given year.

        Returns:
            Tuple of (url, source, is_direct) where:
            - url: The download URL
            - source: Where the URL came from ('jo.se', 'riksdagen', or 'unknown')
            - is_direct: Whether this is a direct PDF link
        """
        # Try known filename patterns on JO
        if year in self.KNOWN_FILES:
            filename = self.KNOWN_FILES[year]
            url = f"{self.JO_BASE_URL}/{year}/{filename}"
            logger.debug(f"Trying known JO URL: {url}")

            # Verify URL is reachable
            try:
                response = self.session.head(url, timeout=self.timeout)
                if response.status_code == 200:
                    return url, "jo.se", True
            except requests.RequestException as e:
                logger.debug(f"Known URL check failed: {e}")

        # Try alternative filename patterns
        patterns = [
            f"{self.JO_BASE_URL}/{year}/ambetsberattelse_{year}.pdf",
            f"{self.JO_BASE_URL}/{year}/ambetsberattelse_{year}-sv.pdf",
            f"{self.JO_BASE_URL}/{year}/{year}_ambetsberattelse.pdf",
        ]

        for url in patterns:
            logger.debug(f"Trying alternative JO URL: {url}")
            try:
                response = self.session.head(url, timeout=self.timeout)
                if response.status_code == 200:
                    logger.debug(f"Found: {url}")
                    return url, "jo.se", True
            except requests.RequestException as e:
                logger.debug(f"Alternative URL check failed: {e}")

        # Fallback: Return the standard pattern (will be attempted)
        default_url = f"{self.JO_BASE_URL}/{year}/ambetsberattelse_{year}.pdf"
        return default_url, "jo.se", True

    def download_year(self, year: int) -> bool:
        """
        Download the ämbetsberättelse for a specific year.

        Args:
            year: The year to download

        Returns:
            True if successful, False otherwise
        """
        # Check if already downloaded
        if self._is_file_downloaded(year):
            return True

        filename = f"jo_ambetsberattelse_{year}.pdf"
        filepath = self.output_dir / filename

        # Find the download URL
        url, source, is_direct = self._find_download_url(year)

        logger.info(f"Downloading year {year} from {source}: {url}")

        # Rate limiting
        time.sleep(self.rate_limit_delay)

        # Download with retry logic
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, timeout=self.timeout, stream=True)

                if response.status_code == 404:
                    logger.warning(f"Year {year}: File not found (404) - {url}")
                    self._update_metadata(year, "not_found")
                    return False

                if response.status_code != 200:
                    logger.warning(
                        f"Year {year}: HTTP {response.status_code} (attempt {attempt + 1}/{self.max_retries})"
                    )
                    if attempt < self.max_retries - 1:
                        time.sleep(2**attempt)  # Exponential backoff
                    continue

                # Write file
                content_length = int(response.headers.get("content-length", 0))

                with open(filepath, "wb") as f:
                    downloaded = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                file_size = filepath.stat().st_size

                if file_size < 1000:
                    logger.warning(
                        f"Year {year}: Downloaded file is suspiciously small ({file_size} bytes)"
                    )
                    self._update_metadata(year, "invalid_size")
                    filepath.unlink()
                    return False

                logger.info(f"Year {year}: Successfully downloaded ({file_size} bytes)")
                self._update_metadata(year, "completed", {"source": source, "size": file_size})
                return True

            except requests.Timeout:
                logger.warning(
                    f"Year {year}: Request timeout (attempt {attempt + 1}/{self.max_retries})"
                )
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)
                continue
            except requests.RequestException as e:
                logger.error(
                    f"Year {year}: Request error (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)
                continue
            except OSError as e:
                logger.error(f"Year {year}: File write error: {e}")
                return False

        logger.error(f"Year {year}: Failed after {self.max_retries} attempts")
        self._update_metadata(year, "failed")
        return False

    def download_range(self, start_year: int, end_year: int) -> dict[str, int]:
        """
        Download ämbetsberättelser for a range of years.

        Args:
            start_year: First year (inclusive)
            end_year: Last year (inclusive)

        Returns:
            Dictionary with download statistics
        """
        logger.info(f"Starting downloads for years {start_year}-{end_year}")

        stats = {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "skipped": 0,
        }

        for year in range(start_year, end_year + 1):
            stats["total"] += 1

            if self._is_file_downloaded(year):
                stats["skipped"] += 1
                continue

            if self.download_year(year):
                stats["successful"] += 1
            else:
                stats["failed"] += 1

        return stats

    def _update_metadata(self, year: int, status: str, extra: dict = None) -> None:
        """Update metadata for a year."""
        record = {
            "status": status,
            "timestamp": datetime.now().isoformat(),
        }

        if extra:
            record.update(extra)

        self.metadata[str(year)] = record
        self._save_metadata()

    def get_status(self) -> dict:
        """Get current download status."""
        status = {
            "output_dir": str(self.output_dir),
            "files": {},
            "summary": {
                "total_files": 0,
                "complete": 0,
                "failed": 0,
                "not_found": 0,
            },
        }

        # Check actual files
        for filepath in sorted(self.output_dir.glob("jo_ambetsberattelse_*.pdf")):
            year = filepath.stem.split("_")[-1]
            file_size = filepath.stat().st_size
            status["files"][year] = {"path": str(filepath), "size": file_size, "exists": True}
            status["summary"]["total_files"] += 1
            status["summary"]["complete"] += 1

        # Check metadata
        for year_str, record in self.metadata.items():
            if year_str not in status["files"]:
                if record["status"] == "not_found":
                    status["summary"]["not_found"] += 1
                elif record["status"] == "failed":
                    status["summary"]["failed"] += 1

        return status

    def list_downloads(self) -> None:
        """Print list of all downloaded files."""
        status = self.get_status()

        print("\n" + "=" * 60)
        print("JO Ämbetsberättelser Download Status")
        print("=" * 60)

        if status["files"]:
            print("\nDownloaded files:")
            for year in sorted(status["files"].keys()):
                info = status["files"][year]
                size_mb = info["size"] / (1024 * 1024)
                print(f"  {year}: {info['path']} ({size_mb:.2f} MB)")
        else:
            print("\nNo files downloaded yet.")

        print("\nSummary:")
        print(f"  Total files: {status['summary']['total_files']}")
        print(f"  Complete: {status['summary']['complete']}")
        print(f"  Failed: {status['summary']['failed']}")
        print(f"  Not found: {status['summary']['not_found']}")
        print("=" * 60 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Download JO ämbetsberättelser (annual reports) PDFs"
    )

    parser.add_argument(
        "years",
        nargs="?",
        help="Year or year range (e.g., 2020 or 2020-2024). Defaults to 2020-2024.",
    )

    parser.add_argument(
        "-o",
        "--output",
        default="/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/juridik-ai/data/jo/",
        help="Output directory (default: /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/juridik-ai/data/jo/)",
    )

    parser.add_argument(
        "-d",
        "--delay",
        type=float,
        default=2.0,
        help="Delay between requests in seconds (default: 2.0)",
    )

    parser.add_argument(
        "-t", "--timeout", type=int, default=30, help="Request timeout in seconds (default: 30)"
    )

    parser.add_argument(
        "-r", "--retries", type=int, default=3, help="Maximum retry attempts (default: 3)"
    )

    parser.add_argument(
        "-l", "--list", action="store_true", help="List all downloaded files and exit"
    )

    parser.add_argument("-s", "--status", action="store_true", help="Show status and exit")

    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Set log level
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        for handler in logger.handlers:
            handler.setLevel(logging.DEBUG)

    # Initialize downloader
    downloader = JODownloader(
        output_dir=args.output,
        rate_limit_delay=args.delay,
        timeout=args.timeout,
        max_retries=args.retries,
    )

    # Handle list/status commands
    if args.list:
        downloader.list_downloads()
        return 0

    if args.status:
        downloader.list_downloads()
        return 0

    # Parse year range
    if not args.years:
        start_year = 2020
        end_year = 2024
    else:
        if "-" in args.years:
            parts = args.years.split("-")
            start_year = int(parts[0])
            end_year = int(parts[1])
        else:
            start_year = end_year = int(args.years)

    # Run downloads
    try:
        stats = downloader.download_range(start_year, end_year)

        print("\n" + "=" * 60)
        print("Download Summary")
        print("=" * 60)
        print(f"Total years: {stats['total']}")
        print(f"Successful: {stats['successful']}")
        print(f"Failed: {stats['failed']}")
        print(f"Skipped (already downloaded): {stats['skipped']}")
        print("=" * 60 + "\n")

        if stats["failed"] > 0:
            return 1
        return 0

    except KeyboardInterrupt:
        logger.info("Download interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit(main())
