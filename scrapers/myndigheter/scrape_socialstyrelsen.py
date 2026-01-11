#!/usr/bin/env python3
"""
Socialstyrelsen Document Scraper
Scrapes föreskrifter (SOSFS/HSLF-FS), nationella riktlinjer, statistik och kunskapsstöd
"""

import json
import logging
import re
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(
            f"socialstyrelsen_scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        ),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class SocialstyrelsenScraper:
    """Scraper for Socialstyrelsen documents"""

    BASE_URL = "https://www.socialstyrelsen.se"

    SEARCH_ENDPOINTS = {
        "foreskrifter": "/kunskapsstod-och-regler/regler-och-riktlinjer/foreskrifter-och-allmanna-rad/",
        "riktlinjer": "/kunskapsstod-och-regler/regler-och-riktlinjer/nationella-riktlinjer/",
        "statistik": "/statistik-och-data/",
        "publikationer": "/publikationer/",
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
            }
        )
        self.documents = []
        self.visited_urls = set()

    def scrape_all(self) -> list[dict]:
        """Main scraping orchestrator"""
        logger.info("=== SOCIALSTYRELSEN SCRAPER START ===")

        # Scrape föreskrifter (SOSFS/HSLF-FS)
        self.scrape_foreskrifter()

        # Scrape nationella riktlinjer
        self.scrape_riktlinjer()

        # Scrape statistik
        self.scrape_statistik()

        # Scrape publikationer API
        self.scrape_publikationer_api()

        logger.info(f"=== SCRAPING COMPLETE: {len(self.documents)} documents ===")
        return self.documents

    def scrape_foreskrifter(self):
        """Scrape SOSFS and HSLF-FS föreskrifter"""
        logger.info("Scraping föreskrifter...")

        url = self.BASE_URL + self.SEARCH_ENDPOINTS["foreskrifter"]

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Find all links to konsoliderade föreskrifter
            foreskrift_links = soup.find_all("a", href=re.compile(r"/konsoliderade-foreskrifter/"))
            logger.info(f"Found {len(foreskrift_links)} föreskrifter links")

            for link in foreskrift_links:
                href = link.get("href", "")
                full_url = urljoin(self.BASE_URL, href)

                if full_url not in self.visited_urls:
                    self.visited_urls.add(full_url)
                    self.scrape_foreskrift_detail(full_url)
                    time.sleep(0.5)  # Rate limiting

            # Also try to find direkta publikationer
            pub_links = soup.find_all(
                "a", href=re.compile(r"/publikationer/.*(SOSFS|HSLF-FS|sosfs|hslf-fs)")
            )
            logger.info(f"Found {len(pub_links)} publikation links")

            for link in pub_links:
                href = link.get("href", "")
                full_url = urljoin(self.BASE_URL, href)

                if full_url not in self.visited_urls:
                    self.visited_urls.add(full_url)
                    self.scrape_publikation_detail(full_url)
                    time.sleep(0.5)

        except Exception as e:
            logger.error(f"Error scraping föreskrifter: {e}")

    def scrape_foreskrift_detail(self, url: str):
        """Scrape individual föreskrift page"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            title = soup.find("h1")
            title_text = title.get_text(strip=True) if title else "Untitled"

            # Extract metadata
            content_div = soup.find("div", class_=["content", "main-content", "article-content"])
            content = content_div.get_text(separator="\n", strip=True) if content_div else ""

            # Look for PDF link
            pdf_link = soup.find("a", href=re.compile(r"\.pdf$", re.I))
            pdf_url = urljoin(self.BASE_URL, pdf_link["href"]) if pdf_link else None

            # Extract föreskriftsnummer from title or URL
            foreskrift_match = re.search(r"(SOSFS|HSLF-FS)\s*(\d{4}:\d+)", title_text)
            foreskrift_id = foreskrift_match.group(0) if foreskrift_match else "Unknown"

            doc = {
                "title": title_text,
                "url": url,
                "source": "socialstyrelsen",
                "type": "föreskrift",
                "foreskrift_id": foreskrift_id,
                "content": content[:5000],  # First 5000 chars
                "pdf_url": pdf_url,
                "scraped_at": datetime.now().isoformat(),
            }

            self.documents.append(doc)
            logger.info(f"Scraped föreskrift: {foreskrift_id} - {title_text[:60]}")

        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")

    def scrape_publikation_detail(self, url: str):
        """Scrape individual publikation page"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            title = soup.find("h1")
            title_text = title.get_text(strip=True) if title else "Untitled"

            content_div = soup.find(
                "div", class_=["content", "main-content", "article-content", "preamble"]
            )
            content = content_div.get_text(separator="\n", strip=True) if content_div else ""

            # PDF link
            pdf_link = soup.find("a", href=re.compile(r"\.pdf$", re.I))
            pdf_url = urljoin(self.BASE_URL, pdf_link["href"]) if pdf_link else None

            # Determine document type
            doc_type = "publikation"
            if re.search(r"SOSFS|HSLF-FS", title_text, re.I):
                doc_type = "föreskrift"
            elif re.search(r"riktlinj", title_text, re.I):
                doc_type = "riktlinje"
            elif re.search(r"statistik", title_text, re.I):
                doc_type = "statistik"

            doc = {
                "title": title_text,
                "url": url,
                "source": "socialstyrelsen",
                "type": doc_type,
                "content": content[:5000],
                "pdf_url": pdf_url,
                "scraped_at": datetime.now().isoformat(),
            }

            self.documents.append(doc)
            logger.info(f"Scraped {doc_type}: {title_text[:60]}")

        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")

    def scrape_riktlinjer(self):
        """Scrape nationella riktlinjer"""
        logger.info("Scraping nationella riktlinjer...")

        url = self.BASE_URL + self.SEARCH_ENDPOINTS["riktlinjer"]

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Find all links to riktlinjer
            riktlinje_links = soup.find_all(
                "a", href=re.compile(r"/(riktlinjer|nationella-riktlinjer)/", re.I)
            )
            logger.info(f"Found {len(riktlinje_links)} riktlinje links")

            for link in riktlinje_links[:50]:  # Limit to avoid duplicates
                href = link.get("href", "")
                full_url = urljoin(self.BASE_URL, href)

                if full_url not in self.visited_urls and "/kunskapsstod-och-regler/" in full_url:
                    self.visited_urls.add(full_url)
                    self.scrape_riktlinje_detail(full_url)
                    time.sleep(0.5)

        except Exception as e:
            logger.error(f"Error scraping riktlinjer: {e}")

    def scrape_riktlinje_detail(self, url: str):
        """Scrape individual riktlinje page"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            title = soup.find("h1")
            title_text = title.get_text(strip=True) if title else "Untitled"

            content_div = soup.find("div", class_=["content", "main-content", "article-content"])
            content = content_div.get_text(separator="\n", strip=True) if content_div else ""

            doc = {
                "title": title_text,
                "url": url,
                "source": "socialstyrelsen",
                "type": "riktlinje",
                "content": content[:5000],
                "scraped_at": datetime.now().isoformat(),
            }

            self.documents.append(doc)
            logger.info(f"Scraped riktlinje: {title_text[:60]}")

        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")

    def scrape_statistik(self):
        """Scrape statistik section"""
        logger.info("Scraping statistik...")

        url = self.BASE_URL + self.SEARCH_ENDPOINTS["statistik"]

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Find statistik links
            stat_links = soup.find_all("a", href=re.compile(r"/statistik-och-data/", re.I))
            logger.info(f"Found {len(stat_links)} statistik links")

            for link in stat_links[:30]:  # Limit
                href = link.get("href", "")
                full_url = urljoin(self.BASE_URL, href)

                if full_url not in self.visited_urls and full_url != url:
                    self.visited_urls.add(full_url)
                    self.scrape_statistik_detail(full_url)
                    time.sleep(0.5)

        except Exception as e:
            logger.error(f"Error scraping statistik: {e}")

    def scrape_statistik_detail(self, url: str):
        """Scrape individual statistik page"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            title = soup.find("h1")
            title_text = title.get_text(strip=True) if title else "Untitled"

            content_div = soup.find("div", class_=["content", "main-content"])
            content = content_div.get_text(separator="\n", strip=True) if content_div else ""

            doc = {
                "title": title_text,
                "url": url,
                "source": "socialstyrelsen",
                "type": "statistik",
                "content": content[:5000],
                "scraped_at": datetime.now().isoformat(),
            }

            self.documents.append(doc)
            logger.info(f"Scraped statistik: {title_text[:60]}")

        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")

    def scrape_publikationer_api(self):
        """Try to scrape from publikationer search/API"""
        logger.info("Scraping publikationer search...")

        # Try search API endpoint
        search_params = [
            "SOSFS",
            "HSLF-FS",
            "föreskrift",
            "riktlinje",
        ]

        for term in search_params:
            try:
                # Try search page
                search_url = f"{self.BASE_URL}/publikationer/?q={term}"
                response = self.session.get(search_url, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, "html.parser")

                # Find result links
                result_links = soup.find_all("a", href=re.compile(r"/publikationer/\d{4}"))
                logger.info(f"Found {len(result_links)} results for '{term}'")

                for link in result_links[:20]:  # Limit per search
                    href = link.get("href", "")
                    full_url = urljoin(self.BASE_URL, href)

                    if full_url not in self.visited_urls:
                        self.visited_urls.add(full_url)
                        self.scrape_publikation_detail(full_url)
                        time.sleep(0.5)

                time.sleep(1)  # Rate limit between searches

            except Exception as e:
                logger.error(f"Error searching '{term}': {e}")

    def save_results(self, output_file: str) -> dict:
        """Save results and generate report"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save full data
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(self.documents, f, ensure_ascii=False, indent=2)

        # Generate report
        doc_types = {}
        for doc in self.documents:
            doc_type = doc.get("type", "unknown")
            doc_types[doc_type] = doc_types.get(doc_type, 0) + 1

        report = {
            "source": "socialstyrelsen",
            "total_documents": len(self.documents),
            "document_types": doc_types,
            "scraped_at": datetime.now().isoformat(),
            "output_file": output_file,
            "flagged": len(self.documents) < 100,
            "flag_reason": "Less than 100 documents found" if len(self.documents) < 100 else None,
        }

        report_file = f"socialstyrelsen_report_{timestamp}.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"Results saved to {output_file}")
        logger.info(f"Report saved to {report_file}")

        return report


def main():
    """Main execution"""
    scraper = SocialstyrelsenScraper()

    try:
        documents = scraper.scrape_all()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"socialstyrelsen_scrape_{timestamp}.json"

        report = scraper.save_results(output_file)

        print("\n" + "=" * 60)
        print("SOCIALSTYRELSEN SCRAPING COMPLETE")
        print("=" * 60)
        print(f"Total documents: {report['total_documents']}")
        print(f"Document types: {json.dumps(report['document_types'], indent=2)}")
        print(f"Flagged: {report['flagged']}")
        if report["flag_reason"]:
            print(f"Flag reason: {report['flag_reason']}")
        print(f"\nOutput: {output_file}")
        print("=" * 60)

        return report

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    main()
