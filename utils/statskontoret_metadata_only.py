#!/usr/bin/env python3
"""
Quick metadata harvest from Statskontoret sitemap
Creates index for later full scraping
"""

import json
import xml.etree.ElementTree as ET
from datetime import datetime

import requests


def get_statskontoret_index():
    """Get all publication URLs from sitemap"""

    sitemap_url = "https://www.statskontoret.se/sitemap.xml"

    try:
        resp = requests.get(sitemap_url, timeout=10)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)

        urls = []
        for url_elem in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
            url = url_elem.text
            if "/publicerat/" in url:
                urls.append(url)

        result = {
            "source": "statskontoret",
            "timestamp": datetime.now().isoformat(),
            "total_urls": len(urls),
            "urls": urls,
            "status": "metadata_only",
            "message": f"Found {len(urls)} publication URLs. Full scraping required for content.",
        }

        return result

    except Exception as e:
        return {
            "source": "statskontoret",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "total_urls": 0,
        }


if __name__ == "__main__":
    result = get_statskontoret_index()

    output_file = f"/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/statskontoret_index_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("✅ Statskontoret Index")
    print(f"   URLs found: {result.get('total_urls', 0)}")
    print(f"   Output: {output_file}")

    if result.get("urls"):
        print("\n📄 Sample URLs:")
        for url in result["urls"][:5]:
            print(f"   - {url}")
