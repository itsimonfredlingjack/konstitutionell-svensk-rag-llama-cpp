#!/usr/bin/env python3
import chromadb
import requests
from boverket_scraper import BoverketScraper
from chromadb.config import Settings

scraper = BoverketScraper()

# BFS 2025 regulations
bfs_2025_docs = [
    {
        "url": "https://rinfo.boverket.se/BFS2025-1/pdf/BFS2025-1.pdf",
        "title": "BFS 2025:1 - Mark- och vattenområden",
        "metadata": {"year": "2025", "type": "Föreskrift", "bfs": "BFS 2025:1"},
    },
    {
        "url": "https://rinfo.boverket.se/BFS2025-2/pdf/BFS2025-2.pdf",
        "title": "BFS 2025:2 - Ekonomiska planer och kostnadskalkyler",
        "metadata": {"year": "2025", "type": "Föreskrift", "bfs": "BFS 2025:2"},
    },
]

for doc in bfs_2025_docs:
    scraper.scrape_pdf_document(doc["url"], doc["title"], doc["metadata"])

# Search for more BFS 2024 documents

# Try to find all available BFS documents
bfs_nums = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]

for num in bfs_nums:
    url = f"https://rinfo.boverket.se/BFS2024-{num}/pdf/BFS2024-{num}.pdf"

    # Quick HEAD request to check if exists
    try:
        resp = requests.head(url, timeout=5)
        if resp.status_code == 200:
            scraper.scrape_pdf_document(
                url,
                f"BFS 2024:{num}",
                {"year": "2024", "type": "Föreskrift", "bfs": f"BFS 2024:{num}"},
            )
    except Exception:
        pass

scraper.generate_report()

# Count final total

client = chromadb.PersistentClient(
    path="/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data",
    settings=Settings(anonymized_telemetry=False),
)
collection = client.get_collection("swedish_gov_docs")
boverket_docs = collection.get(where={"source": "boverket"}, limit=200)
total = len(boverket_docs["ids"])
print(f"\n📊 FINAL TOTAL: {total} Boverket documents")
print(f"✅ Threshold met: {total >= 100}")
