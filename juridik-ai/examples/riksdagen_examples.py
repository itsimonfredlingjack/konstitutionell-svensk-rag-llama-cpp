"""
Riksdagen Client Examples

This file demonstrates various usage patterns for the RiksdagenClient module.
Run with: python examples/riksdagen_examples.py
"""

import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipelines.riksdagen_client import RiksdagenClient


def example_1_basic_search():
    """Example 1: Basic document search."""
    print("\n" + "=" * 60)
    print("Example 1: Basic Document Search")
    print("=" * 60)

    client = RiksdagenClient()

    # Search for propositions from 2024
    print("\nSearching for propositions from 2024...")
    documents = client.search_documents(
        doktyp="prop",
        year_from=2024,
        year_to=2024,
        max_results=5,  # Limit results for example
    )

    print(f"Found {len(documents)} documents:")
    for i, doc in enumerate(documents, 1):
        print(f"\n  {i}. {doc.titel}")
        print(f"     ID: {doc.dokid}")
        print(f"     Status: {doc.dokumentstatus}")
        if doc.publicerad:
            print(f"     Published: {doc.publicerad}")


def example_2_search_with_filter():
    """Example 2: Search with search term filter."""
    print("\n" + "=" * 60)
    print("Example 2: Search with Filter")
    print("=" * 60)

    client = RiksdagenClient()

    # Search for motions about healthcare
    print("\nSearching for motions about 'hälsa' (health)...")
    documents = client.search_documents(
        doktyp="mot",  # Motions
        year_from=2023,
        year_to=2024,
        search_term="hälsa",
        max_results=5,
    )

    print(f"Found {len(documents)} documents:")
    for doc in documents:
        print(f"  - {doc.titel} ({doc.dokid})")


def example_3_get_single_document():
    """Example 3: Fetch a single document by ID."""
    print("\n" + "=" * 60)
    print("Example 3: Get Single Document")
    print("=" * 60)

    client = RiksdagenClient()

    # First, find a document ID
    print("\nSearching for a document...")
    documents = client.search_documents(doktyp="sou", year_from=2024, year_to=2024, max_results=1)

    if documents:
        doc_id = documents[0].dokid
        print(f"Found document: {doc_id}")

        # Now fetch it directly
        print(f"\nFetching document {doc_id}...")
        doc = client.get_document(doc_id)

        if doc:
            print(f"Title: {doc.titel}")
            print(f"Type: {doc.doktyp}")
            print(f"Designation: {doc.beteckning}")
            print(f"Status: {doc.dokumentstatus}")
            if doc.pdf_url:
                print(f"PDF URL: {doc.pdf_url}")


def example_4_download_single():
    """Example 4: Download a single document."""
    print("\n" + "=" * 60)
    print("Example 4: Download Single Document")
    print("=" * 60)

    client = RiksdagenClient()

    # Search and download
    print("\nSearching for documents...")
    documents = client.search_documents(doktyp="prop", year_from=2024, year_to=2024, max_results=1)

    if documents:
        doc = documents[0]
        print(f"Downloading: {doc.titel}")

        filepath = client.download_document(doc, file_format="pdf")
        if filepath:
            print(f"Successfully downloaded to: {filepath}")
            print(f"File size: {filepath.stat().st_size / 1024:.2f} KB")
        else:
            print("Download failed")


def example_5_batch_download():
    """Example 5: Batch download documents."""
    print("\n" + "=" * 60)
    print("Example 5: Batch Download Documents")
    print("=" * 60)

    client = RiksdagenClient()

    print("\nDownloading all motions from 2024...")
    total, downloaded, failed = client.download_all(
        doktyp="mot", year_range=(2024, 2024), file_format="pdf", resume=True
    )

    print("\nDownload Results:")
    print(f"  Total documents: {total}")
    print(f"  Downloaded: {downloaded}")
    print(f"  Failed: {len(failed)}")

    if failed:
        print(f"  Failed IDs: {failed[:5]}")  # Show first 5


def example_6_export_metadata():
    """Example 6: Search and export metadata."""
    print("\n" + "=" * 60)
    print("Example 6: Export Metadata to JSON")
    print("=" * 60)

    client = RiksdagenClient()

    # Search for documents
    print("\nSearching for committee reports from 2024...")
    documents = client.search_documents(
        doktyp="bet",  # Committee reports
        year_from=2024,
        year_to=2024,
        max_results=10,
    )

    print(f"Found {len(documents)} documents")

    # Export metadata
    metadata_file = client.export_metadata(documents)
    print(f"Metadata exported to: {metadata_file}")

    # Show sample of metadata
    with open(metadata_file) as f:
        data = json.load(f)
    print("\nMetadata summary:")
    print(f"  Total documents: {data['total_documents']}")
    print(f"  Exported: {data['exported']}")


def example_7_statistics():
    """Example 7: Get statistics about downloaded documents."""
    print("\n" + "=" * 60)
    print("Example 7: Download Statistics")
    print("=" * 60)

    client = RiksdagenClient()

    stats = client.get_statistics()

    print("\nDownload Statistics:")
    print(f"  Base directory: {stats['base_dir']}")
    print(f"  Total documents: {stats['total_documents']}")
    print(f"  Total size: {stats['total_size_mb']} MB")

    if stats["document_types"]:
        print("\n  By document type:")
        for doc_type, info in stats["document_types"].items():
            print(f"    {doc_type:15s}: {info['count']:4d} docs, {info['size_mb']:10.2f} MB")
    else:
        print("  No documents downloaded yet")


def example_8_multiple_formats():
    """Example 8: Download document in multiple formats."""
    print("\n" + "=" * 60)
    print("Example 8: Download Multiple Formats")
    print("=" * 60)

    client = RiksdagenClient()

    # Find a document
    print("\nSearching for a document...")
    documents = client.search_documents(doktyp="sou", year_from=2024, year_to=2024, max_results=1)

    if documents:
        doc = documents[0]
        print(f"Document: {doc.titel}")

        # Try downloading in different formats
        formats = ["pdf", "html", "text"]
        for fmt in formats:
            print(f"\nDownloading as {fmt.upper()}...")
            filepath = client.download_document(doc, file_format=fmt)
            if filepath:
                print(f"  Success: {filepath}")
            else:
                print(f"  {fmt.upper()} not available")


def example_9_search_all_types():
    """Example 9: Search across all document types."""
    print("\n" + "=" * 60)
    print("Example 9: Search All Document Types")
    print("=" * 60)

    client = RiksdagenClient()

    doc_types = [
        ("prop", "Propositions"),
        ("mot", "Motions"),
        ("sou", "SOU Reports"),
        ("bet", "Committee Reports"),
        ("ip", "Interpellations"),
    ]

    print("\nSearching for documents from 2024 (max 2 per type):\n")

    results = {}
    for code, name in doc_types:
        documents = client.search_documents(
            doktyp=code, year_from=2024, year_to=2024, max_results=2
        )
        results[name] = len(documents)
        print(f"  {name:20s}: {len(documents):3d} documents")

    print(f"\nTotal across all types: {sum(results.values())} documents")


def example_10_resume_download():
    """Example 10: Resume capability demonstration."""
    print("\n" + "=" * 60)
    print("Example 10: Resume Capability")
    print("=" * 60)

    client = RiksdagenClient()

    print("\nStarting download with resume enabled...")
    print("(You can interrupt this with Ctrl+C and it will resume)")

    try:
        total, downloaded, failed = client.download_all(
            doktyp="prop",
            year_range=(2023, 2023),
            file_format="pdf",
            resume=True,  # Enable resume
        )

        print("\nDownload complete:")
        print(f"  Total: {total}")
        print(f"  Downloaded: {downloaded}")
        print(f"  Failed: {len(failed)}")
        print("\nNext run will resume from checkpoint and skip already-downloaded files")

    except KeyboardInterrupt:
        print("\n\nInterrupted! Checkpoint saved.")
        print("Run again with same parameters to resume download.")


def main():
    """Run examples."""
    import argparse

    parser = argparse.ArgumentParser(description="Riksdagen Client Examples")
    parser.add_argument(
        "example", nargs="?", type=int, default=0, help="Example number (1-10) or 0 for all"
    )

    args = parser.parse_args()

    examples = {
        1: example_1_basic_search,
        2: example_2_search_with_filter,
        3: example_3_get_single_document,
        4: example_4_download_single,
        5: example_5_batch_download,
        6: example_6_export_metadata,
        7: example_7_statistics,
        8: example_8_multiple_formats,
        9: example_9_search_all_types,
        10: example_10_resume_download,
    }

    if args.example == 0:
        # Run all examples
        for num in sorted(examples.keys()):
            try:
                examples[num]()
            except Exception as e:
                print(f"\nError in example {num}: {e}")
                import traceback

                traceback.print_exc()
    elif args.example in examples:
        # Run specific example
        try:
            examples[args.example]()
        except Exception as e:
            print(f"\nError: {e}")
            import traceback

            traceback.print_exc()
    else:
        print("Invalid example number. Choose 0-10")
        sys.exit(1)


if __name__ == "__main__":
    main()
