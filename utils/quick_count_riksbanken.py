#!/usr/bin/env python3
"""Quick count of Riksbanken documents (no PDF extraction)"""

import re
import time

import requests
from bs4 import BeautifulSoup

PUBLICATION_URLS = {
    "penningpolitisk_rapport": "https://www.riksbank.se/sv/penningpolitik/penningpolitisk-rapport/penningpolitiska-rapporter-och-uppdateringar/",
    "publikationer": "https://www.riksbank.se/sv/press-och-publicerat/publikationer/",
    "ekonomiska_kommentarer": "https://www.riksbank.se/sv/press-och-publicerat/publikationer/ekonomiska-kommentarer/",
    "finansiell_stabilitet": "https://www.riksbank.se/sv/press-och-publicerat/publikationer/finansiell-stabilitetsrapport/",
    "tal": "https://www.riksbank.se/sv/press-och-publicerat/tal/",
}

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})

total_docs = 0

for pub_type, url in PUBLICATION_URLS.items():
    print(f"\nChecking {pub_type}...")
    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "lxml")

        # Count PDF links
        pdf_links = soup.find_all("a", href=re.compile(r"\.pdf$", re.I))

        # Count publication pages
        pub_links = soup.find_all("a", href=re.compile(r"/(publikationer|rapporter|tal)/[^/]+/$"))

        count = len(pdf_links) + len(pub_links)
        total_docs += count

        print(f"  Found {len(pdf_links)} PDFs + {len(pub_links)} pages = {count} documents")

        time.sleep(1)

    except Exception as e:
        print(f"  ERROR: {e}")

print(f"\n{'='*60}")
print(f"TOTAL DOCUMENTS FOUND: {total_docs}")
print(f"Status: {'OK' if total_docs >= 100 else 'FLAGGAD - Under threshold!'}")
print(f"{'='*60}")
