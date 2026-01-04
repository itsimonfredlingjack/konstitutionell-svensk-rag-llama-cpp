#!/usr/bin/env python3
"""
Riksdagen Bulk Download Script

Downloads documents from Swedish Parliament (Riksdagen) in bulk.
Supports resumption, logging, and progress tracking.

Usage:
    python examples/riksdagen_bulk_download.py [--doktyp DOKTYP] [--year-from YEAR] [--year-to YEAR] [--format FORMAT]

Examples:
    # Download all propositions from 2024
    python examples/riksdagen_bulk_download.py --doktyp prop --year-from 2024 --year-to 2024

    # Download motions from 2023-2024
    python examples/riksdagen_bulk_download.py --doktyp mot --year-from 2023 --year-to 2024

    # Download SOU reports from 2020-2024 as HTML
    python examples/riksdagen_bulk_download.py --doktyp sou --year-from 2020 --year-to 2024 --format html
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipelines.riksdagen_client import DocumentType, RiksdagenClient

# Configure logging with timestamps
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)-8s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class BulkDownloadManager:
    """Manage bulk downloads from Riksdagen."""

    def __init__(
        self, base_dir: str = "/home/dev/juridik-ai/data/riksdagen", rate_limit_delay: float = 0.5
    ):
        """
        Initialize download manager.

        Args:
            base_dir: Base directory for downloads
            rate_limit_delay: Delay between requests (seconds)
        """
        self.client = RiksdagenClient(base_dir=base_dir, rate_limit_delay=rate_limit_delay)
        self.base_dir = base_dir

    def validate_inputs(self, doktyp: str, year_from: int, year_to: int, file_format: str) -> bool:
        """Validate input parameters."""
        # Validate document type
        valid_types = [dt.value for dt in DocumentType]
        if doktyp not in valid_types:
            logger.error(f"Invalid doktyp: {doktyp}")
            logger.error(f"Valid types: {', '.join(valid_types)}")
            return False

        # Validate year range
        current_year = datetime.now().year
        if year_from < 1970 or year_to > current_year:
            logger.error(f"Invalid year range: {year_from}-{year_to}")
            logger.error(f"Must be between 1970 and {current_year}")
            return False

        if year_from > year_to:
            logger.error(f"year_from ({year_from}) cannot be > year_to ({year_to})")
            return False

        # Validate file format
        valid_formats = ["pdf", "html", "text"]
        if file_format not in valid_formats:
            logger.error(f"Invalid file_format: {file_format}")
            logger.error(f"Valid formats: {', '.join(valid_formats)}")
            return False

        return True

    def print_summary(self, doktyp: str, year_from: int, year_to: int, file_format: str) -> None:
        """Print download summary."""
        print("\n" + "=" * 70)
        print("RIKSDAGEN BULK DOWNLOAD")
        print("=" * 70)
        print(f"Document type:  {doktyp}")
        print(f"Year range:     {year_from}-{year_to}")
        print(f"File format:    {file_format}")
        print(f"Output dir:     {self.base_dir}")
        print("=" * 70 + "\n")

    def format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}m"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}h"

    def download(
        self,
        doktyp: str,
        year_from: int,
        year_to: int,
        file_format: str = "pdf",
        resume: bool = True,
    ) -> tuple[int, int, int]:
        """
        Perform bulk download.

        Args:
            doktyp: Document type
            year_from: Start year
            year_to: End year
            file_format: File format (pdf, html, text)
            resume: Enable resume capability

        Returns:
            Tuple of (total, downloaded, failed)
        """
        # Validate inputs
        if not self.validate_inputs(doktyp, year_from, year_to, file_format):
            return (0, 0, 0)

        # Print summary
        self.print_summary(doktyp, year_from, year_to, file_format)

        try:
            # Start timer
            start_time = datetime.now()
            logger.info(f"Starting download at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

            # Perform download
            total, downloaded, failed = self.client.download_all(
                doktyp=doktyp,
                year_range=(year_from, year_to),
                file_format=file_format,
                resume=resume,
            )

            # Calculate statistics
            elapsed = (datetime.now() - start_time).total_seconds()
            failed_count = len(failed) if isinstance(failed, list) else failed

            # Print results
            print("\n" + "=" * 70)
            print("DOWNLOAD COMPLETE")
            print("=" * 70)
            print(f"Total documents:     {total}")
            print(f"Successfully downloaded: {downloaded}")
            print(f"Failed:              {failed_count}")
            print(f"Success rate:        {100*downloaded/max(1,total):.1f}%")
            print(f"Duration:            {self.format_duration(elapsed)}")
            print("=" * 70 + "\n")

            if failed and len(failed) > 0:
                logger.warning(f"Failed documents: {failed[:10]}")
                if len(failed) > 10:
                    logger.warning(f"  ... and {len(failed)-10} more")

            return (total, downloaded, failed_count)

        except KeyboardInterrupt:
            logger.info("\nDownload interrupted by user")
            logger.info("Progress saved. Run again with same parameters to resume.")
            return (0, 0, 0)
        except Exception as e:
            logger.error(f"Download failed with error: {e}", exc_info=True)
            return (0, 0, 0)

    def print_statistics(self) -> None:
        """Print download statistics."""
        stats = self.client.get_statistics()

        if stats["total_documents"] == 0:
            logger.info("No documents downloaded yet")
            return

        print("\n" + "=" * 70)
        print("DOWNLOAD STATISTICS")
        print("=" * 70)
        print(f"Total documents:     {stats['total_documents']}")
        print(f"Total size:          {stats['total_size_mb']:.2f} MB")

        if stats["document_types"]:
            print("\nBy document type:")
            for doc_type in sorted(stats["document_types"].keys()):
                info = stats["document_types"][doc_type]
                print(f"  {doc_type:15s}  {info['count']:5d} docs  {info['size_mb']:10.2f} MB")

        print("=" * 70 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Download documents from Swedish Parliament (Riksdagen)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download propositions from 2024
  %(prog)s --doktyp prop --year-from 2024 --year-to 2024

  # Download motions from 2023-2024
  %(prog)s --doktyp mot --year-from 2023 --year-to 2024

  # Download SOU reports from 2020-2024 as HTML
  %(prog)s --doktyp sou --year-from 2020 --year-to 2024 --format html

  # Show statistics
  %(prog)s --stats
        """,
    )

    parser.add_argument(
        "--doktyp",
        default="prop",
        choices=["prop", "mot", "sou", "bet", "ip", "fsk", "dir", "ds", "skr"],
        help="Document type (default: prop)",
    )

    parser.add_argument("--year-from", type=int, default=2024, help="Start year (default: 2024)")

    parser.add_argument("--year-to", type=int, default=2024, help="End year (default: 2024)")

    parser.add_argument(
        "--format",
        choices=["pdf", "html", "text"],
        default="pdf",
        help="File format to download (default: pdf)",
    )

    parser.add_argument(
        "--no-resume", action="store_true", help="Disable resume capability (start fresh)"
    )

    parser.add_argument(
        "--rate-limit",
        type=float,
        default=0.5,
        help="Delay between requests in seconds (default: 0.5)",
    )

    parser.add_argument(
        "--base-dir",
        default="/home/dev/juridik-ai/data/riksdagen",
        help="Base directory for downloads",
    )

    parser.add_argument("--stats", action="store_true", help="Show download statistics and exit")

    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

    # Initialize manager
    manager = BulkDownloadManager(base_dir=args.base_dir, rate_limit_delay=args.rate_limit)

    # Handle statistics request
    if args.stats:
        manager.print_statistics()
        return 0

    # Perform download
    total, downloaded, failed = manager.download(
        doktyp=args.doktyp,
        year_from=args.year_from,
        year_to=args.year_to,
        file_format=args.format,
        resume=not args.no_resume,
    )

    # Return exit code based on results
    if downloaded == total and total > 0:
        return 0  # Success
    elif downloaded > 0:
        return 1  # Partial success
    else:
        return 2  # No downloads


if __name__ == "__main__":
    sys.exit(main())
