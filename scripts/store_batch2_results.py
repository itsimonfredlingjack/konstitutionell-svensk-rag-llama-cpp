#!/usr/bin/env python3
"""Store batch 2 results in SQLite database."""

import json
import sqlite3
from datetime import datetime

DB_PATH = "kommun_tasks.db"

BATCH2_RESULTS = [
    {
        "id": "0181",
        "status": "done",
        "result": {
            "kommun": "Södertälje",
            "kommun_kod": "0181",
            "url": "https://sodertalje.se",
            "cms": "episerver",
            "cms_confidence": "low",
            "cms_indicators": [
                "Custom JavaScript framework",
                "Azure Application Insights",
                "Possibly Episerver (robots.txt hint)",
            ],
            "diarium": "other",
            "diarium_url": "https://diariet.sodertalje.se/#!/search/",
            "doc_sections": [
                {"path": "/kommun-och-politik/", "type": "portal", "accessible": True}
            ],
            "doc_count_estimate": None,
            "priority_score": 4,
            "requests_made": 5,
            "notes": "JS-heavy diarium at diariet.sodertalje.se. Requires Puppeteer/Playwright.",
        },
    },
    {
        "id": "0484",
        "status": "done",
        "result": {
            "kommun": "Eskilstuna",
            "kommun_kod": "0484",
            "url": "https://eskilstuna.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "cms_indicators": [
                "SiteVisionLTM cookie",
                "/sitevision/system-resource/",
                "dcterms metadata",
            ],
            "diarium": "other",
            "diarium_url": "https://www.eskilstuna.se/kommun-och-politik/ta-del-av-beslut/diarium/sok-i-kommunens-diarium",
            "doc_sections": [
                {
                    "path": "/kommun-och-politik/ta-del-av-beslut/diarium/",
                    "type": "diarium",
                    "accessible": True,
                }
            ],
            "doc_count_estimate": None,
            "priority_score": 3,
            "requests_made": 4,
            "notes": "SiteVision CMS. Diarium under /ta-del-av-beslut/diarium/",
        },
    },
    {
        "id": "0780",
        "status": "done",
        "result": {
            "kommun": "Växjö",
            "kommun_kod": "0780",
            "url": "https://vaxjo.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "cms_indicators": [
                "JSESSIONID cookie",
                "SiteVisionLTM cookie",
                "/sitevision/system-resource/",
            ],
            "diarium": "unknown",
            "diarium_url": None,
            "doc_sections": [
                {
                    "path": "/sidor/politik-och-demokrati/allmanna-handlingar.html",
                    "type": "handlingar",
                    "accessible": True,
                }
            ],
            "doc_count_estimate": None,
            "priority_score": 3,
            "requests_made": 4,
            "notes": "SiteVision CMS. Good structure under Politik och demokrati.",
        },
    },
    {
        "id": "1281",
        "status": "done",
        "result": {
            "kommun": "Lund",
            "kommun_kod": "1281",
            "url": "https://lund.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "cms_indicators": [
                "SiteVisionLTM cookie",
                "sv-template classes",
                "/sitevision/system-resource/",
            ],
            "diarium": "unknown",
            "diarium_url": "/kommun-och-politik/arkiv-och-allmanna-handlingar/allmanna-handlingar-och-diarium",
            "doc_sections": [
                {
                    "path": "/kommun-och-politik/arkiv-och-allmanna-handlingar",
                    "type": "diarium",
                    "accessible": True,
                }
            ],
            "doc_count_estimate": None,
            "priority_score": 4,
            "requests_made": 5,
            "notes": "SiteVision CMS. Diarium path found. Good digital infrastructure.",
        },
    },
    {
        "id": "1380",
        "status": "done",
        "result": {
            "kommun": "Halmstad",
            "kommun_kod": "1380",
            "url": "https://halmstad.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "cms_indicators": ["SiteVisionLTM cookie", "/sitevision/system-resource/"],
            "diarium": "unknown",
            "diarium_url": None,
            "doc_sections": [
                {
                    "path": "/kommunochpolitik/diariumocharkiv/sokidiariet.n329.html",
                    "type": "diarium",
                    "accessible": True,
                }
            ],
            "doc_count_estimate": None,
            "priority_score": 3,
            "requests_made": 5,
            "notes": "SiteVision CMS. Contact: ks.diarium@halmstad.se",
        },
    },
    {
        "id": "1490",
        "status": "done",
        "result": {
            "kommun": "Borås",
            "kommun_kod": "1490",
            "url": "https://boras.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "cms_indicators": ["SiteVisionLTM cookie", "sv-* classes", "AppRegistry"],
            "diarium": "unknown",
            "diarium_url": "https://www.boras.se/kommunochpolitik/motenhandlingarochbeslut/webbdiarium",
            "doc_sections": [
                {
                    "path": "/kommunochpolitik/motenhandlingarochbeslut",
                    "type": "protokoll",
                    "accessible": True,
                }
            ],
            "doc_count_estimate": 185,
            "priority_score": 4,
            "requests_made": 5,
            "notes": "SiteVision CMS. Web diarium integrated. ~185 events.",
        },
    },
    {
        "id": "1780",
        "status": "done",
        "result": {
            "kommun": "Karlstad",
            "kommun_kod": "1780",
            "url": "https://karlstad.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "cms_indicators": ["SiteVisionLTM cookie", "JSESSIONID", "sv-* classes"],
            "diarium": "unknown",
            "diarium_url": None,
            "doc_sections": [
                {
                    "path": "/kommun-och-politik/diarium-arkiv-och-sekretess",
                    "type": "diarium",
                    "accessible": True,
                }
            ],
            "doc_count_estimate": None,
            "priority_score": 4,
            "requests_made": 5,
            "notes": "SiteVision CMS. Good diarium-arkiv-sekretess section.",
        },
    },
    {
        "id": "2180",
        "status": "done",
        "result": {
            "kommun": "Gävle",
            "kommun_kod": "2180",
            "url": "https://gavle.se",
            "cms": "wordpress",
            "cms_confidence": "high",
            "cms_indicators": ["wp-content/themes/", "wp-includes/", "wp-json API"],
            "diarium": "unknown",
            "diarium_url": None,
            "doc_sections": [
                {
                    "path": "/kommun-och-politik/politisk-organisation/namnder/kallelser-och-protokoll/",
                    "type": "protokoll",
                    "accessible": True,
                }
            ],
            "doc_count_estimate": None,
            "priority_score": 4,
            "requests_made": 5,
            "notes": "WordPress CMS with custom theme. May use separate diarium system.",
        },
    },
    {
        "id": "2281",
        "status": "done",
        "result": {
            "kommun": "Sundsvall",
            "kommun_kod": "2281",
            "url": "https://sundsvall.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "cms_indicators": ["SiteVisionLTM cookie", "JSESSIONID", "marketplace.sitevision"],
            "diarium": "unknown",
            "diarium_url": None,
            "doc_sections": [
                {
                    "path": "/kommun/kommun-och-politik/diarium-arkiv-och-sekretess",
                    "type": "diarium",
                    "accessible": True,
                }
            ],
            "doc_count_estimate": None,
            "priority_score": 4,
            "requests_made": 5,
            "notes": "SiteVision CMS. E-services at e-tjanster.sundsvall.se",
        },
    },
    {
        "id": "2480",
        "status": "done",
        "result": {
            "kommun": "Umeå",
            "kommun_kod": "2480",
            "url": "https://umea.se",
            "cms": "sitevision",
            "cms_confidence": "high",
            "cms_indicators": [
                "/sitevision/system-resource/",
                "sv-* classes",
                "AppRegistry",
                "Soleil webapps",
            ],
            "diarium": "unknown",
            "diarium_url": None,
            "doc_sections": [
                {
                    "path": "/kommunochpolitik/diariumarkivochsekretess",
                    "type": "diarium",
                    "accessible": True,
                }
            ],
            "doc_count_estimate": None,
            "priority_score": 4,
            "requests_made": 4,
            "notes": "SiteVision CMS. Good structure with anslagstavla.",
        },
    },
]


def store_results():
    conn = sqlite3.connect(DB_PATH)
    for item in BATCH2_RESULTS:
        conn.execute(
            """
            UPDATE kommuner
            SET status = 'done',
                batch_id = 2,
                completed_at = ?,
                result = ?
            WHERE id = ?
        """,
            (datetime.now().isoformat(), json.dumps(item["result"]), item["id"]),
        )
    conn.commit()
    conn.close()
    print(f"Stored {len(BATCH2_RESULTS)} batch 2 results")


def get_progress():
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
    return row


if __name__ == "__main__":
    store_results()
    total, done, failed, pending = get_progress()
    print(f"\nProgress: {done}/{total} done ({done / total * 100:.1f}%)")
    print(f"Failed: {failed}, Pending: {pending}")
