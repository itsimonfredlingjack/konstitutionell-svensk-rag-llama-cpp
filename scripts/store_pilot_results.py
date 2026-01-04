#!/usr/bin/env python3
"""
Store pilot batch results in SQLite database.
"""

import json
import sqlite3
from datetime import datetime

DB_PATH = "kommun_tasks.db"

# Pilot batch results from 10 kommuner
PILOT_RESULTS = [
    {
        "id": "0180",
        "kommun": "Stockholm",
        "status": "done",
        "result": {
            "kommun": "Stockholm",
            "kommun_kod": "0180",
            "url": "https://stockholm.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "cms_indicators": ["/download/18.", "sv-use-margins", "sv-layout"],
            "diarium": "meetings-plus",
            "diarium_url": "https://insynsverige.se/stockholm",
            "doc_sections": [
                {"path": "/politik-och-demokrati/", "type": "protokoll", "accessible": True},
                {"path": "/om-stockholms-stad/", "type": "handlingar", "accessible": True},
            ],
            "doc_count_estimate": 500,
            "robots_txt": {"status": "partial", "crawl_delay": None, "disallowed_paths": ["/sok/"]},
            "api_available": False,
            "priority_score": 5,
            "requests_made": 5,
            "notes": "Sitevision CMS confirmed. Meetings Plus diarium via insynsverige.se",
        },
    },
    {
        "id": "1480",
        "kommun": "Göteborg",
        "status": "done",
        "result": {
            "kommun": "Göteborg",
            "kommun_kod": "1480",
            "url": "https://goteborg.se",
            "cms": "websphere",
            "cms_confidence": "medium",
            "cms_indicators": ["IBM WebSphere Portal 8.5"],
            "diarium": "unknown",
            "diarium_url": None,
            "doc_sections": [{"path": "/wps/portal/", "type": "handlingar", "accessible": True}],
            "doc_count_estimate": None,
            "robots_txt": {"status": "partial", "crawl_delay": None, "disallowed_paths": []},
            "api_available": False,
            "priority_score": 5,
            "requests_made": 5,
            "notes": "Complex enterprise portal. Needs deeper analysis for diarium.",
        },
    },
    {
        "id": "1280",
        "kommun": "Malmö",
        "status": "done",
        "result": {
            "kommun": "Malmö",
            "kommun_kod": "1280",
            "url": "https://malmo.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "cms_indicators": ["/download/18.", "sv-portal"],
            "diarium": "unknown",
            "diarium_url": None,
            "doc_sections": [
                {"path": "/kommun-och-politik/", "type": "protokoll", "accessible": True}
            ],
            "doc_count_estimate": None,
            "robots_txt": {"status": "allows", "crawl_delay": None, "disallowed_paths": []},
            "api_available": False,
            "priority_score": 5,
            "requests_made": 4,
            "notes": "Sitevision CMS. Needs sitemap analysis for diarium.",
        },
    },
    {
        "id": "0380",
        "kommun": "Uppsala",
        "status": "done",
        "result": {
            "kommun": "Uppsala",
            "kommun_kod": "0380",
            "url": "https://uppsala.se",
            "cms": "custom",
            "cms_confidence": "medium",
            "cms_indicators": ["Custom proprietary system"],
            "diarium": "unknown",
            "diarium_url": None,
            "doc_sections": [{"path": "/publikationer/", "type": "handlingar", "accessible": True}],
            "doc_count_estimate": 30014,
            "robots_txt": {
                "status": "partial",
                "crawl_delay": None,
                "disallowed_paths": ["/search"],
            },
            "api_available": True,
            "api_endpoints": ["/api/find/v2"],
            "priority_score": 5,
            "requests_made": 5,
            "notes": "Find API v2 endpoint discovered. 30,014 publications.",
        },
    },
    {
        "id": "0580",
        "kommun": "Linköping",
        "status": "done",
        "result": {
            "kommun": "Linköping",
            "kommun_kod": "0580",
            "url": "https://linkoping.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "cms_indicators": ["/download/18.", "sv-grid"],
            "diarium": "klara",
            "diarium_url": None,
            "doc_sections": [
                {"path": "/kommun-och-politik/", "type": "protokoll", "accessible": True}
            ],
            "doc_count_estimate": None,
            "robots_txt": {"status": "allows", "crawl_delay": None, "disallowed_paths": []},
            "api_available": False,
            "priority_score": 4,
            "requests_made": 4,
            "notes": "Sitevision CMS. Klara arkivsök/E-arkiv mentioned.",
        },
    },
    {
        "id": "1880",
        "kommun": "Örebro",
        "status": "done",
        "result": {
            "kommun": "Örebro",
            "kommun_kod": "1880",
            "url": "https://orebro.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "cms_indicators": ["/download/18.", "sv-layout"],
            "diarium": "unknown",
            "diarium_url": None,
            "doc_sections": [
                {"path": "/kommun-och-politik--demokrati/", "type": "protokoll", "accessible": True}
            ],
            "doc_count_estimate": None,
            "robots_txt": {"status": "allows", "crawl_delay": None, "disallowed_paths": []},
            "api_available": False,
            "priority_score": 4,
            "requests_made": 4,
            "notes": "Sitevision CMS. Double-hyphens in URL structure.",
        },
    },
    {
        "id": "1980",
        "kommun": "Västerås",
        "status": "done",
        "result": {
            "kommun": "Västerås",
            "kommun_kod": "1980",
            "url": "https://vasteras.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "cms_indicators": ["/download/18.", "sv-portal"],
            "diarium": "unknown",
            "diarium_url": None,
            "doc_sections": [{"path": "/politik/", "type": "protokoll", "accessible": True}],
            "doc_count_estimate": None,
            "robots_txt": {"status": "allows", "crawl_delay": None, "disallowed_paths": []},
            "api_available": False,
            "priority_score": 4,
            "requests_made": 4,
            "notes": "Sitevision CMS. Non-standard URL structure.",
        },
    },
    {
        "id": "1283",
        "kommun": "Helsingborg",
        "status": "done",
        "result": {
            "kommun": "Helsingborg",
            "kommun_kod": "1283",
            "url": "https://helsingborg.se",
            "cms": "wordpress",
            "cms_confidence": "high",
            "cms_indicators": ["/wp-content/", "/wp-includes/"],
            "diarium": "unknown",
            "diarium_url": None,
            "doc_sections": [],
            "doc_count_estimate": None,
            "robots_txt": {
                "status": "partial",
                "crawl_delay": None,
                "disallowed_paths": ["/wp-admin/"],
            },
            "api_available": False,
            "priority_score": 4,
            "requests_made": 5,
            "notes": "WordPress CMS. Document paths not found via standard URLs.",
        },
    },
    {
        "id": "0581",
        "kommun": "Norrköping",
        "status": "done",
        "result": {
            "kommun": "Norrköping",
            "kommun_kod": "0581",
            "url": "https://norrkoping.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "cms_indicators": ["/download/18.", "sv-layout"],
            "diarium": "custom",
            "diarium_url": None,
            "doc_sections": [
                {"path": "/kommun-och-politik/", "type": "protokoll", "accessible": True}
            ],
            "doc_count_estimate": None,
            "robots_txt": {"status": "allows", "crawl_delay": None, "disallowed_paths": []},
            "api_available": False,
            "priority_score": 4,
            "requests_made": 4,
            "notes": "Sitevision CMS. Diariet/Anslagstavla in footer.",
        },
    },
    {
        "id": "0680",
        "kommun": "Jönköping",
        "status": "failed",
        "error": "WAF blocked all 5 requests. Aggressive firewall protection. Requires browser automation (Selenium/Playwright).",
    },
]


def store_results():
    """Store pilot batch results in SQLite."""
    conn = sqlite3.connect(DB_PATH)

    done_count = 0
    failed_count = 0

    for item in PILOT_RESULTS:
        if item["status"] == "done":
            conn.execute(
                """
                UPDATE kommuner
                SET status = 'done',
                    batch_id = 1,
                    completed_at = ?,
                    result = ?
                WHERE id = ?
            """,
                (datetime.now().isoformat(), json.dumps(item["result"]), item["id"]),
            )
            done_count += 1
        else:
            conn.execute(
                """
                UPDATE kommuner
                SET status = 'failed',
                    batch_id = 1,
                    completed_at = ?,
                    error = ?
                WHERE id = ?
            """,
                (datetime.now().isoformat(), item.get("error", "Unknown error"), item["id"]),
            )
            failed_count += 1

    conn.commit()
    conn.close()

    print(f"Stored {done_count} successful, {failed_count} failed results")
    return done_count, failed_count


def validate_results():
    """Validate pilot batch results."""
    issues = []
    valid_count = 0

    for item in PILOT_RESULTS:
        if item["status"] == "failed":
            continue

        result = item["result"]
        item_issues = []

        # Required fields
        required = ["kommun", "kommun_kod", "url", "cms", "diarium", "priority_score"]
        for field in required:
            if field not in result:
                item_issues.append(f"Missing: {field}")

        # kommun_kod format
        kod = result.get("kommun_kod", "")
        if not (len(kod) == 4 and kod.isdigit()):
            item_issues.append(f"Invalid kommun_kod: {kod}")

        # priority_score range
        score = result.get("priority_score", 0)
        if not (1 <= score <= 5):
            item_issues.append(f"priority_score out of range: {score}")

        # URL format
        url = result.get("url", "")
        if not url.startswith("https://"):
            item_issues.append("URL missing https://")

        if item_issues:
            issues.append((item["kommun"], item_issues))
        else:
            valid_count += 1

    return valid_count, issues


def analyze_distribution():
    """Analyze CMS and diarium distribution."""
    cms_counts = {}
    diarium_counts = {}

    for item in PILOT_RESULTS:
        if item["status"] == "failed":
            continue

        cms = item["result"].get("cms", "unknown")
        cms_counts[cms] = cms_counts.get(cms, 0) + 1

        diarium = item["result"].get("diarium", "unknown")
        diarium_counts[diarium] = diarium_counts.get(diarium, 0) + 1

    return cms_counts, diarium_counts


if __name__ == "__main__":
    print("=" * 60)
    print("PILOT BATCH VALIDATION")
    print("=" * 60)

    # Validate
    valid_count, issues = validate_results()
    total = len([r for r in PILOT_RESULTS if r["status"] == "done"])
    failed = len([r for r in PILOT_RESULTS if r["status"] == "failed"])

    print(f"\nResults: {valid_count}/{total} valid, {failed} failed")
    print(f"Failure rate: {failed/len(PILOT_RESULTS)*100:.1f}%")

    if issues:
        print("\nValidation issues:")
        for kommun, item_issues in issues:
            print(f"  {kommun}: {', '.join(item_issues)}")

    # Distribution
    cms_counts, diarium_counts = analyze_distribution()
    print("\nCMS Distribution:")
    for cms, count in sorted(cms_counts.items(), key=lambda x: -x[1]):
        print(f"  {cms}: {count}")

    print("\nDiarium Distribution:")
    for diarium, count in sorted(diarium_counts.items(), key=lambda x: -x[1]):
        print(f"  {diarium}: {count}")

    # Store in DB
    print("\n" + "=" * 60)
    print("STORING IN DATABASE")
    print("=" * 60)
    done, failed = store_results()

    # Get overall progress
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as done,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending
        FROM kommuner
    """)
    row = cursor.fetchone()
    conn.close()

    print("\nOverall Progress:")
    print(f"  Total: {row[0]}")
    print(f"  Done: {row[1]} ({row[1]/row[0]*100:.1f}%)")
    print(f"  Failed: {row[2]}")
    print(f"  Pending: {row[3]}")
