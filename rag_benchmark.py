#!/usr/bin/env python3
"""
RAG Benchmark - Validate search quality for Constitutional AI

Tests:
1. Latency (search time, answer generation time)
2. Relevance (average similarity scores)
3. Answer quality (length, source coverage)
4. Coverage (unique sources hit)

Usage:
  python rag_benchmark.py                    # Full benchmark
  python rag_benchmark.py --quick            # Quick test (5 questions)
  python rag_benchmark.py --no-answers       # Skip LLM generation
  python rag_benchmark.py --output results.json
"""

import argparse
import asyncio
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

import httpx

# Configuration
API_URL = "http://localhost:8900"
DEFAULT_TOP_K = 10
TIMEOUT_SEARCH = 30.0
TIMEOUT_ANSWER = 120.0

# Swedish government document test queries
TEST_QUERIES = [
    # GDPR & Privacy
    {
        "id": "gdpr_01",
        "query": "Vad säger GDPR om personuppgifter?",
        "category": "privacy",
        "expected_sources": ["datainspektionen", "gdpr"],
        "keywords": ["personuppgift", "behandling", "samtycke"],
    },
    {
        "id": "gdpr_02",
        "query": "Vilka rättigheter har jag enligt dataskyddsförordningen?",
        "category": "privacy",
        "expected_sources": ["datainspektionen"],
        "keywords": ["rättighet", "radera", "tillgång", "invändning"],
    },
    # Public Procurement
    {
        "id": "upphandling_01",
        "query": "Vilka regler gäller för offentlig upphandling?",
        "category": "procurement",
        "expected_sources": ["upphandlingsmyndigheten", "konkurrensverket"],
        "keywords": ["upphandling", "anbudsförfarande", "LOU"],
    },
    {
        "id": "upphandling_02",
        "query": "Hur fungerar direktupphandling?",
        "category": "procurement",
        "expected_sources": ["upphandlingsmyndigheten"],
        "keywords": ["direktupphandling", "beloppsgräns", "undantag"],
    },
    # Municipal Administration
    {
        "id": "kommun_01",
        "query": "Hur fungerar kommunal budget?",
        "category": "municipal",
        "expected_sources": ["kommun", "skr"],
        "keywords": ["budget", "skatteintäkt", "nämnd"],
    },
    {
        "id": "kommun_02",
        "query": "Vad är kommunfullmäktiges uppgifter?",
        "category": "municipal",
        "expected_sources": ["kommun"],
        "keywords": ["kommunfullmäktige", "beslut", "val", "ledamot"],
    },
    {
        "id": "kommun_03",
        "query": "Hur överklagas kommunala beslut?",
        "category": "municipal",
        "expected_sources": ["kommun", "förvaltningsrätt"],
        "keywords": ["överklaga", "laglighetsprövning", "förvaltningsbesvär"],
    },
    # Building & Construction
    {
        "id": "bygg_01",
        "query": "Vilka regler finns för bygglov?",
        "category": "construction",
        "expected_sources": ["boverket"],
        "keywords": ["bygglov", "plan", "detaljplan", "ansökan"],
    },
    {
        "id": "bygg_02",
        "query": "Vad säger BBR om tillgänglighet?",
        "category": "construction",
        "expected_sources": ["boverket"],
        "keywords": ["tillgänglighet", "BBR", "funktionshinder", "hiss"],
    },
    {
        "id": "bygg_03",
        "query": "Hur fungerar energikrav för nya byggnader?",
        "category": "construction",
        "expected_sources": ["boverket", "energimyndigheten"],
        "keywords": ["energi", "klimatdeklaration", "kWh", "isolering"],
    },
    # Administrative Law
    {
        "id": "forvaltning_01",
        "query": "Vad innehåller förvaltningslagen?",
        "category": "administrative",
        "expected_sources": ["riksdagen", "regeringen"],
        "keywords": ["förvaltningslagen", "myndighet", "beslut", "part"],
    },
    {
        "id": "forvaltning_02",
        "query": "Vilka krav finns på myndigheters handläggning?",
        "category": "administrative",
        "expected_sources": ["riksdagen"],
        "keywords": ["handläggning", "skyndsamhet", "kommunicering"],
    },
    # Social Services
    {
        "id": "social_01",
        "query": "Vad säger socialtjänstlagen om bistånd?",
        "category": "social",
        "expected_sources": ["socialstyrelsen"],
        "keywords": ["bistånd", "socialtjänst", "försörjningsstöd"],
    },
    {
        "id": "social_02",
        "query": "Vilka regler gäller för äldreomsorg?",
        "category": "social",
        "expected_sources": ["socialstyrelsen", "kommun"],
        "keywords": ["äldreomsorg", "hemtjänst", "särskilt boende"],
    },
    # Environment
    {
        "id": "miljo_01",
        "query": "Vad kräver miljöbalken för verksamheter?",
        "category": "environment",
        "expected_sources": ["naturvardsverket"],
        "keywords": ["miljöbalken", "tillstånd", "miljöprövning"],
    },
    {
        "id": "miljo_02",
        "query": "Hur fungerar strandskydd?",
        "category": "environment",
        "expected_sources": ["naturvardsverket", "boverket"],
        "keywords": ["strandskydd", "dispens", "100 meter"],
    },
    # Education
    {
        "id": "skola_01",
        "query": "Vilka rättigheter har elever enligt skollagen?",
        "category": "education",
        "expected_sources": ["skolverket"],
        "keywords": ["skollag", "elev", "undervisning", "stöd"],
    },
    # Tax
    {
        "id": "skatt_01",
        "query": "Hur beräknas kommunalskatt?",
        "category": "tax",
        "expected_sources": ["skatteverket", "kommun"],
        "keywords": ["kommunalskatt", "skattesats", "inkomst"],
    },
    # Health & Safety
    {
        "id": "halsa_01",
        "query": "Vilka regler finns för arbetsmiljö?",
        "category": "health",
        "expected_sources": ["arbetsmiljoverket"],
        "keywords": ["arbetsmiljö", "skyddsombud", "risk"],
    },
    # Public Access
    {
        "id": "offentlighet_01",
        "query": "Hur fungerar offentlighetsprincipen?",
        "category": "transparency",
        "expected_sources": ["riksdagen"],
        "keywords": ["offentlighet", "allmän handling", "sekretess"],
    },
]


class RAGBenchmark:
    """Benchmark suite for RAG Search API."""

    def __init__(self, api_url: str = API_URL, generate_answers: bool = True):
        self.api_url = api_url
        self.generate_answers = generate_answers
        self.results = []

    async def check_health(self) -> dict:
        """Check API health before running benchmark."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"{self.api_url}/health", timeout=10.0)
                return resp.json()
            except Exception as e:
                return {"status": "error", "message": str(e)}

    async def run_query(self, query_info: dict, top_k: int = DEFAULT_TOP_K) -> dict:
        """Run a single test query and measure performance."""
        query_id = query_info["id"]
        query = query_info["query"]
        expected_sources = query_info.get("expected_sources", [])
        keywords = query_info.get("keywords", [])

        result = {
            "id": query_id,
            "query": query,
            "category": query_info.get("category", "unknown"),
            "timestamp": datetime.now().isoformat(),
            "success": False,
            "error": None,
        }

        try:
            async with httpx.AsyncClient() as client:
                # Run search
                timeout = TIMEOUT_ANSWER if self.generate_answers else TIMEOUT_SEARCH
                start_time = datetime.now()

                resp = await client.post(
                    f"{self.api_url}/search",
                    json={"query": query, "top_k": top_k, "generate_answer": self.generate_answers},
                    timeout=timeout,
                )

                elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

                if resp.status_code != 200:
                    result["error"] = f"HTTP {resp.status_code}"
                    return result

                data = resp.json()

                # Extract metrics
                result["success"] = True
                result["latency_ms"] = round(elapsed_ms, 2)
                result["api_took_ms"] = data.get("took_ms", 0)
                result["num_results"] = len(data.get("results", []))

                # Relevance scores
                scores = [r["score"] for r in data.get("results", [])]
                if scores:
                    result["relevance"] = {
                        "top_score": round(scores[0], 4),
                        "avg_score": round(statistics.mean(scores), 4),
                        "min_score": round(min(scores), 4),
                        "score_spread": round(max(scores) - min(scores), 4),
                    }

                # Source coverage
                sources = data.get("sources", [])
                result["sources"] = sources
                result["source_coverage"] = {
                    "unique_sources": len(set(sources)),
                    "expected_hit": any(
                        any(exp.lower() in src.lower() for src in sources)
                        for exp in expected_sources
                    )
                    if expected_sources
                    else None,
                }

                # Keyword matching in results
                all_text = " ".join(r.get("text", "") for r in data.get("results", [])).lower()
                keyword_hits = sum(1 for kw in keywords if kw.lower() in all_text)
                result["keyword_coverage"] = {
                    "total_keywords": len(keywords),
                    "hits": keyword_hits,
                    "hit_rate": round(keyword_hits / len(keywords), 2) if keywords else 0,
                }

                # Answer quality (if generated)
                answer = data.get("answer")
                if answer:
                    result["answer"] = {
                        "length": len(answer),
                        "word_count": len(answer.split()),
                        "has_content": len(answer) > 50,
                        "preview": answer[:200] + "..." if len(answer) > 200 else answer,
                    }
                else:
                    result["answer"] = None

                # Top results preview
                result["top_results"] = [
                    {
                        "source": r.get("source"),
                        "score": round(r.get("score", 0), 4),
                        "text_preview": r.get("text", "")[:100] + "...",
                    }
                    for r in data.get("results", [])[:3]
                ]

        except httpx.TimeoutException:
            result["error"] = "Timeout"
        except Exception as e:
            result["error"] = str(e)

        return result

    async def run_benchmark(self, queries: list[dict] = None, progress_callback=None) -> dict:
        """Run full benchmark suite."""
        queries = queries or TEST_QUERIES
        self.results = []

        print(f"\n{'='*60}")
        print(f"  RAG BENCHMARK - {len(queries)} queries")
        print(f"  API: {self.api_url}")
        print(f"  Answers: {'Yes' if self.generate_answers else 'No'}")
        print(f"{'='*60}\n")

        # Check health
        health = await self.check_health()
        if health.get("status") != "healthy":
            print(f"⚠️  API not healthy: {health}")
            return {"error": "API not healthy", "health": health}

        print(f"✅ API healthy - {health.get('docs_count', 0):,} docs indexed\n")

        # Run queries
        for i, query_info in enumerate(queries, 1):
            if progress_callback:
                progress_callback(i, len(queries), query_info["query"])
            else:
                print(f"[{i}/{len(queries)}] {query_info['query'][:50]}...", end=" ", flush=True)

            result = await self.run_query(query_info)
            self.results.append(result)

            if result["success"]:
                latency = result.get("latency_ms", 0)
                top_score = result.get("relevance", {}).get("top_score", 0)
                print(f"✓ {latency:.0f}ms (score: {top_score:.3f})")
            else:
                print(f"✗ {result.get('error', 'Unknown error')}")

            # Small delay between queries
            await asyncio.sleep(0.5)

        return self.generate_report()

    def generate_report(self) -> dict:
        """Generate benchmark report from results."""
        successful = [r for r in self.results if r["success"]]
        failed = [r for r in self.results if not r["success"]]

        report = {
            "benchmark_info": {
                "timestamp": datetime.now().isoformat(),
                "api_url": self.api_url,
                "total_queries": len(self.results),
                "successful": len(successful),
                "failed": len(failed),
                "generate_answers": self.generate_answers,
            },
            "summary": {},
            "by_category": {},
            "results": self.results,
        }

        if not successful:
            report["summary"]["error"] = "No successful queries"
            return report

        # Latency stats
        latencies = [r["latency_ms"] for r in successful]
        report["summary"]["latency"] = {
            "mean_ms": round(statistics.mean(latencies), 2),
            "median_ms": round(statistics.median(latencies), 2),
            "min_ms": round(min(latencies), 2),
            "max_ms": round(max(latencies), 2),
            "p95_ms": round(
                sorted(latencies)[int(len(latencies) * 0.95)]
                if len(latencies) > 1
                else latencies[0],
                2,
            ),
        }

        # Relevance stats
        top_scores = [r["relevance"]["top_score"] for r in successful if r.get("relevance")]
        avg_scores = [r["relevance"]["avg_score"] for r in successful if r.get("relevance")]

        if top_scores:
            report["summary"]["relevance"] = {
                "mean_top_score": round(statistics.mean(top_scores), 4),
                "mean_avg_score": round(statistics.mean(avg_scores), 4),
                "min_top_score": round(min(top_scores), 4),
                "max_top_score": round(max(top_scores), 4),
            }

        # Keyword coverage
        keyword_rates = [
            r["keyword_coverage"]["hit_rate"] for r in successful if r.get("keyword_coverage")
        ]
        if keyword_rates:
            report["summary"]["keyword_coverage"] = {
                "mean_hit_rate": round(statistics.mean(keyword_rates), 2),
                "queries_with_hits": sum(1 for r in keyword_rates if r > 0),
                "perfect_coverage": sum(1 for r in keyword_rates if r == 1.0),
            }

        # Source coverage
        expected_hits = [
            r["source_coverage"]["expected_hit"]
            for r in successful
            if r.get("source_coverage") and r["source_coverage"]["expected_hit"] is not None
        ]
        if expected_hits:
            report["summary"]["source_coverage"] = {
                "expected_source_hit_rate": round(sum(expected_hits) / len(expected_hits), 2)
            }

        # Answer stats (if enabled)
        answers = [r["answer"] for r in successful if r.get("answer")]
        if answers:
            word_counts = [a["word_count"] for a in answers]
            report["summary"]["answers"] = {
                "generated": len(answers),
                "mean_word_count": round(statistics.mean(word_counts), 1),
                "min_word_count": min(word_counts),
                "max_word_count": max(word_counts),
            }

        # By category
        categories = set(r["category"] for r in successful)
        for cat in categories:
            cat_results = [r for r in successful if r["category"] == cat]
            cat_latencies = [r["latency_ms"] for r in cat_results]
            cat_scores = [r["relevance"]["top_score"] for r in cat_results if r.get("relevance")]

            report["by_category"][cat] = {
                "count": len(cat_results),
                "mean_latency_ms": round(statistics.mean(cat_latencies), 2),
                "mean_top_score": round(statistics.mean(cat_scores), 4) if cat_scores else 0,
            }

        # Quality grade
        avg_score = report["summary"].get("relevance", {}).get("mean_top_score", 0)
        keyword_rate = report["summary"].get("keyword_coverage", {}).get("mean_hit_rate", 0)

        if avg_score >= 0.7 and keyword_rate >= 0.6:
            grade = "A"
        elif avg_score >= 0.5 and keyword_rate >= 0.4:
            grade = "B"
        elif avg_score >= 0.3 and keyword_rate >= 0.2:
            grade = "C"
        else:
            grade = "D"

        report["summary"]["quality_grade"] = grade

        return report


def print_report(report: dict):
    """Pretty print benchmark report."""
    print(f"\n{'='*60}")
    print("  BENCHMARK RESULTS")
    print(f"{'='*60}")

    info = report["benchmark_info"]
    print(f"\nQueries: {info['successful']}/{info['total_queries']} successful")

    summary = report.get("summary", {})

    if "latency" in summary:
        lat = summary["latency"]
        print("\n📊 LATENCY")
        print(f"   Mean:   {lat['mean_ms']:.0f}ms")
        print(f"   Median: {lat['median_ms']:.0f}ms")
        print(f"   P95:    {lat['p95_ms']:.0f}ms")
        print(f"   Range:  {lat['min_ms']:.0f}ms - {lat['max_ms']:.0f}ms")

    if "relevance" in summary:
        rel = summary["relevance"]
        print("\n🎯 RELEVANCE")
        print(f"   Mean Top Score:  {rel['mean_top_score']:.4f}")
        print(f"   Mean Avg Score:  {rel['mean_avg_score']:.4f}")
        print(f"   Score Range:     {rel['min_top_score']:.4f} - {rel['max_top_score']:.4f}")

    if "keyword_coverage" in summary:
        kw = summary["keyword_coverage"]
        print("\n🔑 KEYWORD COVERAGE")
        print(f"   Mean Hit Rate:    {kw['mean_hit_rate']*100:.0f}%")
        print(f"   Queries w/ Hits:  {kw['queries_with_hits']}")
        print(f"   Perfect Coverage: {kw['perfect_coverage']}")

    if "answers" in summary:
        ans = summary["answers"]
        print("\n💬 ANSWERS")
        print(f"   Generated:       {ans['generated']}")
        print(f"   Mean Word Count: {ans['mean_word_count']:.0f}")

    if "quality_grade" in summary:
        print(f"\n📈 QUALITY GRADE: {summary['quality_grade']}")

    # By category
    if report.get("by_category"):
        print("\n📁 BY CATEGORY")
        for cat, stats in sorted(report["by_category"].items()):
            print(
                f"   {cat}: {stats['count']} queries, "
                f"score={stats['mean_top_score']:.3f}, "
                f"latency={stats['mean_latency_ms']:.0f}ms"
            )

    print(f"\n{'='*60}\n")


async def main():
    parser = argparse.ArgumentParser(description="RAG Benchmark for Constitutional AI")
    parser.add_argument("--quick", action="store_true", help="Quick test (5 queries)")
    parser.add_argument("--no-answers", action="store_true", help="Skip LLM answer generation")
    parser.add_argument("--output", "-o", default="benchmark_results.json", help="Output file")
    parser.add_argument("--api", default=API_URL, help="API URL")
    args = parser.parse_args()

    # Select queries
    queries = TEST_QUERIES[:5] if args.quick else TEST_QUERIES

    # Run benchmark
    benchmark = RAGBenchmark(api_url=args.api, generate_answers=not args.no_answers)

    report = await benchmark.run_benchmark(queries)

    # Print results
    print_report(report)

    # Save to file
    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"📄 Results saved to: {output_path}")

    # Return exit code based on quality
    grade = report.get("summary", {}).get("quality_grade", "F")
    return 0 if grade in ["A", "B"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
