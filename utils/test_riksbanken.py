#!/usr/bin/env python3
"""Quick test of Riksbanken scraping"""

import re

import requests
from bs4 import BeautifulSoup

url = "https://www.riksbank.se/sv/penningpolitik/penningpolitisk-rapport/penningpolitiska-rapporter-och-uppdateringar/"

print(f"Testing URL: {url}\n")

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})

try:
    response = session.get(url, timeout=30)
    response.raise_for_status()
    print(f"Status code: {response.status_code}")

    soup = BeautifulSoup(response.content, "lxml")

    # Find PDF links
    pdf_links = soup.find_all("a", href=re.compile(r"\.pdf$", re.I))
    print(f"\nFound {len(pdf_links)} PDF links:")

    for i, link in enumerate(pdf_links[:10]):
        href = link.get("href", "")
        text = link.get_text(strip=True)[:80]
        print(f"  {i+1}. {text}")
        print(f"     URL: {href}")

    # Find other publication links
    pub_links = soup.find_all("a", href=re.compile(r"/(publikationer|rapporter|tal)/"))
    print(f"\nFound {len(pub_links)} publication links:")

    for i, link in enumerate(pub_links[:10]):
        href = link.get("href", "")
        text = link.get_text(strip=True)[:80]
        print(f"  {i+1}. {text}")
        print(f"     URL: {href}")

except Exception as e:
    print(f"ERROR: {e}")
