#!/usr/bin/env python3
"""
Generate final report for Skatteverket scraping operation
"""

import json
from datetime import datetime
from pathlib import Path

import chromadb

CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "skatteverket_docs"
OUTPUT_DIR = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/skatteverket_docs")


def generate_report():
    # Connect to ChromaDB
    client = chromadb.PersistentClient(path=CHROMADB_PATH)
    collection = client.get_collection(name=COLLECTION_NAME)

    # Get statistics
    total_docs = collection.count()

    # Sample documents
    sample = collection.get(limit=10, include=["documents", "metadatas"])

    # Extract unique URLs
    unique_urls = set()
    document_types = {}

    all_docs = collection.get(limit=10000, include=["metadatas"])
    for metadata in all_docs["metadatas"]:
        url = metadata.get("url", "")
        unique_urls.add(url)

        # Categorize by document type
        if "stallningstaganden" in url:
            doc_type = "ställningstaganden"
        elif "rattsfall" in url:
            doc_type = "rättsfall"
        elif "handledningar" in url:
            doc_type = "handledningar"
        elif "foreskrifter" in url:
            doc_type = "föreskrifter"
        elif "allmannarad" in url:
            doc_type = "allmänna råd"
        else:
            doc_type = "other"

        document_types[doc_type] = document_types.get(doc_type, 0) + 1

    # Count PDFs
    pdf_files = list(OUTPUT_DIR.glob("*.pdf"))

    # Generate report
    report = {
        "operation": "MYNDIGHETS-SWEEP - SKATTEVERKET",
        "timestamp": datetime.now().isoformat(),
        "status": "SUCCESS" if total_docs >= 100 else "WARNING",
        "statistics": {
            "total_documents_indexed": total_docs,
            "unique_source_pages": len(unique_urls),
            "pdfs_downloaded": len(pdf_files),
            "embedding_model": "KBLab/sentence-bert-swedish-cased",
            "chromadb_collection": COLLECTION_NAME,
        },
        "document_types": document_types,
        "sample_documents": [
            {
                "url": sample["metadatas"][i].get("url", "N/A"),
                "title": sample["metadatas"][i].get("title", "N/A"),
                "content_preview": sample["documents"][i][:200] + "...",
            }
            for i in range(min(5, len(sample["documents"])))
        ],
        "pdf_files": [str(f.name) for f in pdf_files],
        "warning": None
        if total_docs >= 100
        else f"SIMON: Skatteverket verkar ha problem - endast {total_docs} dokument indexerade (förväntat: >100)",
    }

    # Save report
    report_path = (
        OUTPUT_DIR / f"skatteverket_final_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Print summary
    print("=" * 70)
    print("OPERATION MYNDIGHETS-SWEEP - SKATTEVERKET - FINAL REPORT")
    print("=" * 70)
    print(f"\nStatus: {report['status']}")
    print("\nStatistik:")
    print(f"  Totalt indexerade dokument: {total_docs}")
    print(f"  Unika källsidor: {len(unique_urls)}")
    print(f"  Nedladdade PDFer: {len(pdf_files)}")
    print("\nDokumenttyper:")
    for doc_type, count in sorted(document_types.items(), key=lambda x: x[1], reverse=True):
        print(f"  {doc_type}: {count}")
    print("\nChromaDB:")
    print(f"  Collection: {COLLECTION_NAME}")
    print(f"  Path: {CHROMADB_PATH}")
    print(f"\nRapport sparad: {report_path}")

    if report["warning"]:
        print(f"\n⚠️  {report['warning']}")

    return report


if __name__ == "__main__":
    report = generate_report()
