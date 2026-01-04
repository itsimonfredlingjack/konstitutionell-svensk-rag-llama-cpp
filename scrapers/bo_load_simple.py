#!/usr/bin/env python3
"""
Simple loader for BO documents - outputs summary JSON
"""

import json
import sys
from datetime import datetime
from pathlib import Path


def create_summary(json_file: str):
    """Create summary of BO documents"""

    # Load JSON
    with open(json_file, encoding="utf-8") as f:
        documents = json.load(f)

    print(f"Loaded {len(documents)} documents from {json_file}")

    # Create summary
    summary = {
        "source": "barnombudsmannen",
        "source_full": "Barnombudsmannen",
        "total_documents": len(documents),
        "scraped_at": datetime.now().isoformat(),
        "by_type": {},
        "by_year": {},
        "sample_documents": [],
    }

    # Count by type
    for doc in documents:
        doc_type = doc["doc_type"]
        summary["by_type"][doc_type] = summary["by_type"].get(doc_type, 0) + 1

        year = doc.get("year", "unknown")
        summary["by_year"][str(year)] = summary["by_year"].get(str(year), 0) + 1

    # Sample documents
    for doc in documents[:10]:
        summary["sample_documents"].append(
            {
                "title": doc["title"],
                "type": doc["doc_type"],
                "year": doc.get("year", "unknown"),
                "url": doc["url"],
            }
        )

    # Save summary
    output_dir = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/scraped_data")
    summary_file = output_dir / "bo_summary.json"

    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print("BO SCRAPE SUMMARY")
    print(f"{'='*60}")
    print(f"Total documents: {summary['total_documents']}")
    print("\nBy type:")
    for doc_type, count in sorted(summary["by_type"].items()):
        print(f"  {doc_type}: {count}")

    print("\nBy year:")
    year_counts = [(y, c) for y, c in summary["by_year"].items()]
    for year, count in sorted(year_counts, key=lambda x: (x[0] == "unknown", x[0]), reverse=True):
        print(f"  {year}: {count}")

    print(f"\nSummary saved to: {summary_file}")

    # Status check
    if summary["total_documents"] < 100:
        print(f"\n⚠️  WARNING: Only {summary['total_documents']} documents found (expected >100)")
        print("This may be due to pagination not working properly.")
    else:
        print(f"\n✓ {summary['total_documents']} documents scraped successfully")

    return summary_file


if __name__ == "__main__":
    # Use latest JSON file
    scraped_dir = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/scraped_data")
    json_files = list(scraped_dir.glob("bo_documents_v2_*.json"))

    if not json_files:
        print("No BO JSON files found!")
        sys.exit(1)

    # Use the latest file
    latest_file = sorted(json_files)[-1]
    print(f"Using file: {latest_file}\n")

    summary_file = create_summary(str(latest_file))
