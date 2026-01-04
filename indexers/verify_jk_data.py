#!/usr/bin/env python3
"""
Verify JK ChromaDB data and generate final report
"""

import json
from datetime import datetime
from pathlib import Path

import chromadb
from chromadb.config import Settings

# Connect to ChromaDB
chroma_path = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data")
client = chromadb.PersistentClient(
    path=str(chroma_path), settings=Settings(anonymized_telemetry=False)
)

# Get collection
collection = client.get_collection(name="swedish_gov_docs")

# Query all JK documents
results = collection.get(where={"source": "jk"}, include=["metadatas"])

# Analyze results
total_jk_docs = len(results["ids"])
categories = {}
years = {}

for metadata in results["metadatas"]:
    # Count categories
    category = metadata.get("category", "unknown")
    categories[category] = categories.get(category, 0) + 1

    # Count years
    diary_number = metadata.get("diary_number", "")
    year = diary_number.split("-")[0] if diary_number else "unknown"
    years[year] = years.get(year, 0) + 1

# Create final report
report = {
    "myndighet": "JK",
    "status": "FLAGGAD" if total_jk_docs < 100 else "OK",
    "docs_found": total_jk_docs,
    "docs_indexed": total_jk_docs,
    "errors": [],
    "analysis": {
        "note": "JK publicerar endast beslut 'av allmänt intresse' (fr.o.m. år 2000)",
        "expected": "JK's website states only decisions of 'public interest' are published",
        "categories": categories,
        "years": sorted(years.items()),
    },
    "warning": "SIMON: JK publicerar INTE alla sina beslut online - endast ~10-20 featured per år"
    if total_jk_docs < 500
    else "",
    "chromadb_location": str(chroma_path),
    "collection_name": "swedish_gov_docs",
    "verified_at": datetime.now().isoformat(),
}

# Print report
print(json.dumps(report, indent=2, ensure_ascii=False))

# Save report
output_file = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/jk_final_report.json")
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print(f"\n✅ Report saved to: {output_file}")
