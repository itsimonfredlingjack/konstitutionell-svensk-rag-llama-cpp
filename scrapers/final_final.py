#!/usr/bin/env python3
from boverket_scraper import BoverketScraper

scraper = BoverketScraper()

# Try completely new documents
new_docs = [
    {
        "url": "https://rinfo.boverket.se/BFS2019-2/pdf/BFS2019-2.pdf",
        "title": "BFS 2019:2 BBR 28",
        "metadata": {
            "year": "2019",
            "type": "Föreskrift",
            "bfs": "BFS 2019:2",
            "version": "BBR 28",
        },
    },
    {
        "url": "https://rinfo.boverket.se/BFS2018-15/pdf/BFS2018-15.pdf",
        "title": "BFS 2018:15 BBR 27",
        "metadata": {
            "year": "2018",
            "type": "Föreskrift",
            "bfs": "BFS 2018:15",
            "version": "BBR 27",
        },
    },
    {
        "url": "https://rinfo.boverket.se/BFS2018-4/pdf/BFS2018-4.pdf",
        "title": "BFS 2018:4 BBR 26",
        "metadata": {
            "year": "2018",
            "type": "Föreskrift",
            "bfs": "BFS 2018:4",
            "version": "BBR 26",
        },
    },
    {
        "url": "https://rinfo.boverket.se/BFS2017-5/pdf/BFS2017-5.pdf",
        "title": "BFS 2017:5 BBR 25",
        "metadata": {
            "year": "2017",
            "type": "Föreskrift",
            "bfs": "BFS 2017:5",
            "version": "BBR 25",
        },
    },
]

for doc in new_docs:
    scraper.scrape_pdf_document(doc["url"], doc["title"], doc["metadata"])

# FINAL
import chromadb
from chromadb.config import Settings

client = chromadb.PersistentClient(
    path="/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data",
    settings=Settings(anonymized_telemetry=False),
)
collection = client.get_collection("swedish_gov_docs")
boverket_docs = collection.get(where={"source": "boverket"}, limit=200)
total = len(boverket_docs["ids"])

print(f"\n{'='*80}")
print("BOVERKET SCRAPE - FINAL STATUS")
print(f"{'='*80}")
print(f"Documents collected: {total}/100")
print(f"Status: {'✅ SUCCESS' if total >= 100 else '⚠️  FLAGGED'}")
print(f"{'='*80}")
