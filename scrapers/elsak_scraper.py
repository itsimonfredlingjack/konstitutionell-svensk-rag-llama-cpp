#!/usr/bin/env python3
"""
Elsäkerhetsverket Scraper
========================
KÄLLA: elsakerhetsverket.se
FOKUS: Föreskrifter (ELSÄK-FS), vägledningar, publikationer
OUTPUT: JSON till /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/elsak_harvest.json
"""

import json
import re
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.elsakerhetsverket.se"
OUTPUT_FILE = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/elsak_harvest.json"


class ElsakScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (constitutional-ai-research-crawler)"}
        )
        self.documents = []
        self.visited_urls = set()

    def scrape_foreskrifter(self) -> list[dict]:
        """Skrapa ELSÄK-FS föreskrifter"""
        print("[1/4] Skrapar föreskrifter (ELSÄK-FS)...")
        urls = [
            f"{BASE_URL}/om-oss/lag-och-ratt/foreskrifter/",
            f"{BASE_URL}/om-oss/lag-och-ratt/foreskrifter-i-nummerordning/",
            f"{BASE_URL}/om-oss/lag-och-ratt/regler-efter-omrade/",
        ]

        docs = []
        for url in urls:
            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, "html.parser")

                # Hitta alla länkar till ELSÄK-FS dokument
                for link in soup.find_all("a", href=True):
                    href = link["href"]
                    text = link.get_text(strip=True)

                    # Matcha ELSÄK-FS dokument
                    if "ELSÄK-FS" in text.upper() or "elsak-fs" in href.lower():
                        full_url = urljoin(BASE_URL, href)

                        if full_url in self.visited_urls:
                            continue
                        self.visited_urls.add(full_url)

                        # Om det är en PDF-länk
                        if href.endswith(".pdf"):
                            doc = {
                                "url": full_url,
                                "title": text,
                                "type": "föreskrift",
                                "source": "elsakerhetsverket",
                                "format": "pdf",
                                "scraped_at": datetime.now().isoformat(),
                            }
                            docs.append(doc)
                            print(f"  ✓ {text[:60]}")

                        # Om det är en webbsida
                        elif "elsakerhetsverket.se" in full_url:
                            content = self._scrape_page(full_url)
                            if content:
                                doc = {
                                    "url": full_url,
                                    "title": text,
                                    "content": content,
                                    "type": "föreskrift",
                                    "source": "elsakerhetsverket",
                                    "format": "html",
                                    "scraped_at": datetime.now().isoformat(),
                                }
                                docs.append(doc)
                                print(f"  ✓ {text[:60]}")

                        time.sleep(0.5)

            except Exception as e:
                print(f"  ✗ Fel vid {url}: {e}")

        return docs

    def scrape_vagledningar(self) -> list[dict]:
        """Skrapa vägledningar och riktlinjer"""
        print("[2/4] Skrapar vägledningar...")
        urls = [
            f"{BASE_URL}/vagledning-fortlopande-kontroll/",
            f"{BASE_URL}/om-oss/lag-och-ratt/vad-innebar-de-nya-starkstromsforeskrifterna/",
        ]

        docs = []
        for url in urls:
            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, "html.parser")

                # Hitta artiklar och innehållssidor
                for article in soup.find_all(
                    ["article", "div"], class_=re.compile(r"content|article|publication")
                ):
                    title_elem = article.find(["h1", "h2", "h3", "h4"])
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)

                    # Extrahera innehåll
                    paragraphs = article.find_all("p")
                    content = "\n\n".join(
                        [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
                    )

                    if content and len(content) > 100:
                        doc = {
                            "url": url,
                            "title": title,
                            "content": content,
                            "type": "vägledning",
                            "source": "elsakerhetsverket",
                            "format": "html",
                            "scraped_at": datetime.now().isoformat(),
                        }
                        docs.append(doc)
                        print(f"  ✓ {title[:60]}")

                time.sleep(0.5)

            except Exception as e:
                print(f"  ✗ Fel vid {url}: {e}")

        return docs

    def scrape_publikationer(self) -> list[dict]:
        """Skrapa publikationer och rapporter"""
        print("[3/4] Skrapar publikationer...")
        urls = [
            f"{BASE_URL}/om-oss/publikationer/",
            f"{BASE_URL}/om-oss/press/",
        ]

        docs = []
        for url in urls:
            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, "html.parser")

                # Hitta alla publikationslänkar
                for link in soup.find_all("a", href=True):
                    href = link["href"]
                    text = link.get_text(strip=True)

                    # Filtrera relevanta publikationer
                    if any(
                        keyword in text.lower()
                        for keyword in [
                            "rapport",
                            "publikation",
                            "årsredovisning",
                            "handbok",
                            "guide",
                        ]
                    ):
                        full_url = urljoin(BASE_URL, href)

                        if full_url in self.visited_urls:
                            continue
                        self.visited_urls.add(full_url)

                        if href.endswith(".pdf"):
                            doc = {
                                "url": full_url,
                                "title": text,
                                "type": "publikation",
                                "source": "elsakerhetsverket",
                                "format": "pdf",
                                "scraped_at": datetime.now().isoformat(),
                            }
                            docs.append(doc)
                            print(f"  ✓ {text[:60]}")

                        time.sleep(0.3)

            except Exception as e:
                print(f"  ✗ Fel vid {url}: {e}")

        return docs

    def scrape_beslut(self) -> list[dict]:
        """Skrapa myndighetsbeslut och lagar"""
        print("[4/4] Skrapar myndighetsbeslut och lagar...")
        urls = [
            f"{BASE_URL}/om-oss/lag-och-ratt/lagar-och-forordningar/",
            f"{BASE_URL}/om-oss/lag-och-ratt/rattsakter-inom-eu/",
            f"{BASE_URL}/om-oss/lag-och-ratt/upphavda-foreskrifter/",
            f"{BASE_URL}/privatpersoner/dina-elprodukter/forsaljningsforbud/",
        ]

        docs = []
        for url in urls:
            try:
                response = self.session.get(url, timeout=15)
                if response.status_code == 404:
                    continue

                response.raise_for_status()
                soup = BeautifulSoup(response.content, "html.parser")

                # Hitta beslutsdokument
                for link in soup.find_all("a", href=True):
                    href = link["href"]
                    text = link.get_text(strip=True)

                    if "beslut" in text.lower() or "beslut" in href.lower():
                        full_url = urljoin(BASE_URL, href)

                        if full_url in self.visited_urls:
                            continue
                        self.visited_urls.add(full_url)

                        if href.endswith(".pdf"):
                            doc = {
                                "url": full_url,
                                "title": text,
                                "type": "beslut",
                                "source": "elsakerhetsverket",
                                "format": "pdf",
                                "scraped_at": datetime.now().isoformat(),
                            }
                            docs.append(doc)
                            print(f"  ✓ {text[:60]}")

                        time.sleep(0.3)

            except Exception as e:
                print(f"  ✗ Fel vid {url}: {e}")

        return docs

    def _scrape_page(self, url: str) -> str:
        """Extrahera innehåll från en webbsida"""
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Ta bort navigation, header, footer
            for element in soup.find_all(["nav", "header", "footer", "script", "style"]):
                element.decompose()

            # Extrahera huvudinnehåll
            main_content = soup.find(["main", "article"]) or soup.find(
                "div", class_=re.compile(r"content|main")
            )

            if main_content:
                paragraphs = main_content.find_all(["p", "li", "h1", "h2", "h3", "h4", "h5", "h6"])
                content = "\n\n".join(
                    [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
                )
                return content

            return ""

        except Exception as e:
            print(f"    ✗ Kunde inte skrapa {url}: {e}")
            return ""

    def run(self) -> dict:
        """Kör hela scrapingen"""
        print("=" * 60)
        print("ELSÄKERHETSVERKET SCRAPER")
        print("=" * 60)

        start_time = datetime.now()

        # Samla alla dokument
        self.documents.extend(self.scrape_foreskrifter())
        self.documents.extend(self.scrape_vagledningar())
        self.documents.extend(self.scrape_publikationer())
        self.documents.extend(self.scrape_beslut())

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Skapa resultat
        result = {
            "source": "elsakerhetsverket",
            "scraped_at": datetime.now().isoformat(),
            "duration_seconds": duration,
            "total_documents": len(self.documents),
            "documents_by_type": {
                "föreskrift": len([d for d in self.documents if d["type"] == "föreskrift"]),
                "vägledning": len([d for d in self.documents if d["type"] == "vägledning"]),
                "publikation": len([d for d in self.documents if d["type"] == "publikation"]),
                "beslut": len([d for d in self.documents if d["type"] == "beslut"]),
            },
            "documents": self.documents,
        }

        # Spara till JSON
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print("\n" + "=" * 60)
        print("KLART!")
        print(f"Totalt: {len(self.documents)} dokument")
        print(f"Tid: {duration:.1f}s")
        print(f"Output: {OUTPUT_FILE}")
        print("=" * 60)

        return result


if __name__ == "__main__":
    scraper = ElsakScraper()
    result = scraper.run()

    # Skriv ut sammanfattning
    print("\nSAMMANFATTNING:")
    for doc_type, count in result["documents_by_type"].items():
        print(f"  {doc_type}: {count}")
