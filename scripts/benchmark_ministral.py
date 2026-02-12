#!/usr/bin/env python3
"""
Benchmark smoke-test for Ministral-3-14B via llama-server.

Validates end-to-end: health, GBNF grammar grading, n-gram speculation,
and RAG-like throughput baseline. Self-contained — only requires httpx.

Usage:
    python scripts/benchmark_ministral.py
    python scripts/benchmark_ministral.py --base-url http://localhost:8080 --timeout 180
"""

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# GBNF grammar — identical to grader_service.py
# ---------------------------------------------------------------------------
GRADING_GRAMMAR = r"""root ::= "{" ws "\"relevance\"" ws ":" ws value ws "}"
value ::= "\"yes\"" | "\"no\""
ws ::= " "?"""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str
    metrics: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def chat_completion(
    client: httpx.AsyncClient,
    base_url: str,
    messages: list[dict[str, str]],
    *,
    stream: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Send a chat completion request and return unified result dict.

    Returns:
        {content, tokens, ttft_ms, total_ms, timings, usage}
    """
    url = f"{base_url}/v1/chat/completions"
    payload: dict[str, Any] = {
        "messages": messages,
        "stream": stream,
        **kwargs,
    }

    t0 = time.perf_counter()
    ttft_ms: float | None = None

    if not stream:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        total_ms = (time.perf_counter() - t0) * 1000
        body = resp.json()
        content = body["choices"][0]["message"]["content"]
        usage = body.get("usage", {})
        timings = body.get("timings", {})
        tokens = usage.get("completion_tokens", 0)
        return {
            "content": content,
            "tokens": tokens,
            "ttft_ms": total_ms,  # non-stream: ttft ≈ total
            "total_ms": total_ms,
            "timings": timings,
            "usage": usage,
        }

    # Streaming path
    content_parts: list[str] = []
    tokens = 0
    timings: dict[str, Any] = {}
    usage: dict[str, Any] = {}

    async with client.stream("POST", url, json=payload) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            # Extract delta content
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            text = delta.get("content", "")
            if text:
                if ttft_ms is None:
                    ttft_ms = (time.perf_counter() - t0) * 1000
                content_parts.append(text)
                tokens += 1  # approximate: 1 SSE chunk ≈ 1 token

            # Last chunk often has timings/usage
            if "timings" in chunk:
                timings = chunk["timings"]
            if "usage" in chunk:
                usage = chunk["usage"]

    total_ms = (time.perf_counter() - t0) * 1000

    # Prefer server-reported token count
    if usage.get("completion_tokens"):
        tokens = usage["completion_tokens"]

    return {
        "content": "".join(content_parts),
        "tokens": tokens,
        "ttft_ms": ttft_ms or total_ms,
        "total_ms": total_ms,
        "timings": timings,
        "usage": usage,
    }


# ---------------------------------------------------------------------------
# Test 1: LLM Health
# ---------------------------------------------------------------------------
async def test_llm_health(client: httpx.AsyncClient, base_url: str) -> TestResult:
    name = "LLM Health"
    try:
        result = await chat_completion(
            client,
            base_url,
            messages=[
                {"role": "user", "content": "Svara med exakt ett ord: fungerar det?"},
            ],
            stream=False,
            temperature=0.1,
            max_tokens=16,
        )
        content = result["content"].strip()
        latency = result["total_ms"]

        if not content:
            return TestResult(name, False, "Empty response")
        if latency > 10_000:
            return TestResult(name, False, f"{latency:.0f}ms (>10s)", {"latency_ms": latency})
        short = content[:40].replace("\n", " ")
        return TestResult(name, True, f'{latency:.0f}ms, "{short}"', {"latency_ms": latency})
    except Exception as e:
        return TestResult(name, False, str(e)[:80])


# ---------------------------------------------------------------------------
# Test 2: GBNF Grading
# ---------------------------------------------------------------------------
async def test_gbnf_grading(client: httpx.AsyncClient, base_url: str) -> list[TestResult]:
    results: list[TestResult] = []

    cases = [
        {
            "label": "GBNF Grading (relevant)",
            "question": "Vad innebär yttrandefrihet?",
            "doc_title": "Regeringsformen",
            "doc_type": "grundlag",
            "doc_text": (
                "Enligt 2 kap. 1 § regeringsformen är varje medborgare gentemot det "
                "allmänna tillförsäkrad yttrandefrihet: frihet att i tal, skrift eller "
                "bild eller på annat sätt meddela upplysningar samt uttrycka tankar, "
                "åsikter och känslor."
            ),
            "expected": '{"relevance":"yes"}',
        },
        {
            "label": "GBNF Grading (irrelevant)",
            "question": "Vad innebär yttrandefrihet?",
            "doc_title": "Kommunal avfallshantering",
            "doc_type": "kommun",
            "doc_text": (
                "Kommunen ansvarar för insamling och transport av hushållsavfall "
                "enligt 15 kap. miljöbalken. Sophämtning sker varannan vecka och "
                "brännbart avfall behandlas vid kommunens energianläggning."
            ),
            "expected": '{"relevance":"no"}',
        },
    ]

    for case in cases:
        name = case["label"]
        prompt = (
            f"Är detta dokument relevant för frågan? Svara ENDAST med JSON.\n\n"
            f"FRÅGA: {case['question']}\n\n"
            f"DOKUMENT: {case['doc_title']} ({case['doc_type']})\n"
            f"{case['doc_text']}\n\n"
            f"Relevant = dokumentet besvarar eller direkt relaterar till frågan.\n"
            f"Irrelevant = dokumentet handlar om något annat.\n\n"
            f"Svara med EXAKT ett av dessa:\n"
            f'{{"relevance":"yes"}}\n'
            f'{{"relevance":"no"}}'
        )

        try:
            result = await chat_completion(
                client,
                base_url,
                messages=[
                    {
                        "role": "system",
                        "content": "Du är en dokumentgraderare. Bedöm relevans med hög precision.",
                    },
                    {"role": "user", "content": prompt},
                ],
                stream=False,
                temperature=0.1,
                max_tokens=32,
                grammar=GRADING_GRAMMAR,
            )
            content = result["content"].strip()
            latency = result["total_ms"]
            passed = content == case["expected"]
            detail = f"{latency:.0f}ms, {content}"
            if not passed:
                detail += f" (expected {case['expected']})"
            results.append(TestResult(name, passed, detail, {"latency_ms": latency}))
        except Exception as e:
            results.append(TestResult(name, False, str(e)[:80]))

    return results


# ---------------------------------------------------------------------------
# Test 3: N-gram Speculation
# ---------------------------------------------------------------------------
async def test_ngram_speculation(client: httpx.AsyncClient, base_url: str) -> TestResult:
    name = "N-gram Speculation"
    # Repetitive legal text designed to benefit from n-gram speculation
    legal_prompt = (
        "Skriv en kort juridisk paragraf i SFS-stil. Använd formuleringar som "
        "'den som', 'ska', 'enligt', 'med stöd av' upprepade gånger:\n\n"
        "1 § Den som uppsåtligen eller av grov oaktsamhet bryter mot bestämmelserna "
        "i denna lag ska dömas till böter eller fängelse i högst sex månader. "
        "Den som medverkar till sådant brott ska dömas enligt 23 kap. brottsbalken. "
        "Den som anstiftar eller medverkar ska anses ha begått brottet enligt vad "
        "som föreskrivs i 23 kap. 4 § brottsbalken.\n\n"
        "2 § Den som i strid med 3 § första stycket underlåter att fullgöra sin "
        "anmälningsskyldighet ska dömas till böter. Den som lämnar oriktig uppgift "
        "ska dömas till böter eller fängelse i högst ett år. Den som bryter mot "
        "förbudet i 5 § ska dömas enligt vad som sägs i 1 §.\n\n"
        "Fortsätt med 3 § och 4 § i samma stil."
    )

    try:
        result = await chat_completion(
            client,
            base_url,
            messages=[{"role": "user", "content": legal_prompt}],
            stream=True,
            temperature=0.3,
            max_tokens=256,
        )
        content = result["content"]
        tokens = result["tokens"]
        ttft_ms = result["ttft_ms"]
        total_ms = result["total_ms"]

        if not content:
            return TestResult(name, False, "Empty response")

        tok_per_s = (tokens / (total_ms / 1000)) if total_ms > 0 else 0

        # Log server-side timings if available
        timings = result.get("timings", {})
        server_tps = timings.get("predicted_per_second")
        tps_str = f"{server_tps:.1f}" if server_tps else f"{tok_per_s:.1f}"

        detail = f"{tps_str} tok/s, TTFT {ttft_ms:.0f}ms"
        return TestResult(
            name,
            tok_per_s > 0,
            detail,
            {
                "tokens": tokens,
                "tok_per_s": tok_per_s,
                "ttft_ms": ttft_ms,
                "total_ms": total_ms,
                "server_timings": timings,
            },
        )
    except Exception as e:
        return TestResult(name, False, str(e)[:80])


# ---------------------------------------------------------------------------
# Test 4: Throughput Baseline
# ---------------------------------------------------------------------------
RAG_PROMPTS = [
    {
        "system": (
            "Du är en juridisk AI-assistent specialiserad på svensk grundlag. "
            "Svara sakligt och hänvisa till relevanta lagrum. Basera ditt svar "
            "på de dokument som ges som kontext."
        ),
        "context": (
            "Regeringsformen (1974:152) 1 kap. 1 §: All offentlig makt i Sverige "
            "utgår från folket. Den svenska folkstyrelsen bygger på fri åsiktsbildning "
            "och på allmän och lika rösträtt. Den förverkligas genom ett representativt "
            "och parlamentariskt statsskick och genom kommunal självstyrelse."
        ),
        "question": "Vilka grundprinciper fastslår regeringsformen om den svenska demokratin?",
    },
    {
        "system": (
            "Du är en juridisk AI-assistent specialiserad på dataskydd. "
            "Svara sakligt och hänvisa till relevanta artiklar."
        ),
        "context": (
            "Dataskyddsförordningen (GDPR) artikel 5: Personuppgifter ska behandlas "
            "på ett lagligt, korrekt och öppet sätt i förhållande till den registrerade. "
            "De ska samlas in för särskilda, uttryckligt angivna och berättigade ändamål "
            "och inte senare behandlas på ett sätt som är oförenligt med dessa ändamål."
        ),
        "question": "Vilka grundläggande principer gäller för behandling av personuppgifter?",
    },
    {
        "system": (
            "Du är en juridisk AI-assistent specialiserad på kommunalrätt. "
            "Svara sakligt baserat på kontexten."
        ),
        "context": (
            "Kommunallagen (2017:725) 2 kap. 1 §: Kommuner och regioner får själva "
            "ha hand om angelägenheter av allmänt intresse som har anknytning till "
            "kommunens eller regionens område eller deras medlemmar. 2 §: Kommuner "
            "och regioner ska behandla sina medlemmar lika, om det inte finns sakliga "
            "skäl för något annat."
        ),
        "question": "Vad säger kommunallagen om kommunal kompetens och likabehandling?",
    },
    {
        "system": (
            "Du är en juridisk AI-assistent specialiserad på riksdagsordningen. "
            "Svara sakligt baserat på kontexten."
        ),
        "context": (
            "Riksdagsordningen (2014:801) 4 kap. 1 §: Riksdagen sammanträder till "
            "riksmöte varje år. Riksmötet öppnas vid en särskild ceremoni i rikssalen. "
            "11 kap. 1 §: Riksdagen kan besluta att hänskjuta ärenden till utskott "
            "för beredning."
        ),
        "question": "Hur organiseras riksdagens arbete enligt riksdagsordningen?",
    },
    {
        "system": (
            "Du är en juridisk AI-assistent specialiserad på offentlighet och sekretess. "
            "Svara sakligt baserat på kontexten."
        ),
        "context": (
            "Offentlighets- och sekretesslagen (2009:400) 1 kap. 1 §: Denna lag "
            "innehåller bestämmelser om myndigheters och vissa andra organs hantering "
            "av allmänna handlingar, om tystnadsplikt i det allmännas verksamhet och "
            "om förbud att lämna ut allmänna handlingar. 2 kap. TF: Varje svensk "
            "medborgare ska ha rätt att ta del av allmänna handlingar."
        ),
        "question": "Vad reglerar offentlighetsprincipen och vilka undantag finns?",
    },
]


async def test_throughput_baseline(client: httpx.AsyncClient, base_url: str) -> TestResult:
    name = "Throughput (avg of 5)"
    ttfts: list[float] = []
    tok_rates: list[float] = []
    failures: list[str] = []

    for i, p in enumerate(RAG_PROMPTS):
        try:
            result = await chat_completion(
                client,
                base_url,
                messages=[
                    {"role": "system", "content": p["system"]},
                    {
                        "role": "user",
                        "content": f"Kontext:\n{p['context']}\n\nFråga: {p['question']}",
                    },
                ],
                stream=True,
                temperature=0.4,
                max_tokens=512,
            )
            if not result["content"]:
                failures.append(f"Prompt {i + 1}: empty")
                continue

            total_ms = result["total_ms"]
            tokens = result["tokens"]
            tok_s = (tokens / (total_ms / 1000)) if total_ms > 0 else 0
            ttfts.append(result["ttft_ms"])
            tok_rates.append(tok_s)
        except Exception as e:
            failures.append(f"Prompt {i + 1}: {str(e)[:40]}")

    if failures:
        return TestResult(name, False, f"{len(failures)} failed: {'; '.join(failures)}")

    avg_tok_s = sum(tok_rates) / len(tok_rates)
    avg_ttft = sum(ttfts) / len(ttfts)
    passed = avg_tok_s > 5
    detail = f"{avg_tok_s:.1f} tok/s, TTFT {avg_ttft:.0f}ms avg"
    if not passed:
        detail += " (<5 tok/s)"
    return TestResult(
        name,
        passed,
        detail,
        {"avg_tok_s": avg_tok_s, "avg_ttft_ms": avg_ttft, "per_prompt": tok_rates},
    )


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------
def print_summary_table(results: list[TestResult]) -> None:
    col1, col2, col3 = 34, 6, 42

    def pad(s: str, w: int) -> str:
        return s[:w].ljust(w)

    print()
    # Top border
    print(f"\u2554{'═' * (col1 + 1)}╤{'═' * (col2 + 2)}╤{'═' * (col3 + 1)}╗")
    # Header
    print(f"║ {pad('Test', col1)}│ {pad('Result', col2)} │ {pad('Details', col3)}║")
    # Header separator
    print(f"╠{'═' * (col1 + 1)}╪{'═' * (col2 + 2)}╪{'═' * (col3 + 1)}╣")
    # Rows
    for r in results:
        tag = "PASS" if r.passed else "FAIL"
        print(f"║ {pad(r.name, col1)}│ {pad(tag, col2)} │ {pad(r.detail, col3)}║")
    # Bottom border
    print(f"╚{'═' * (col1 + 1)}╧{'═' * (col2 + 2)}╧{'═' * (col3 + 1)}╝")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark smoke-test for Ministral-3-14B via llama-server"
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8080",
        help="llama-server base URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Request timeout in seconds (default: 120)",
    )
    args = parser.parse_args()

    print(f"Benchmark: Ministral-3-14B @ {args.base_url}")
    print(f"Timeout: {args.timeout}s")
    print("─" * 50)

    results: list[TestResult] = []

    async with httpx.AsyncClient(timeout=httpx.Timeout(args.timeout)) as client:
        # Test 1: Health
        print("Running: LLM Health ...", end=" ", flush=True)
        r = await test_llm_health(client, args.base_url)
        results.append(r)
        print("PASS" if r.passed else "FAIL")

        # Test 2: GBNF Grading (2 sub-tests)
        print("Running: GBNF Grading ...", end=" ", flush=True)
        grading_results = await test_gbnf_grading(client, args.base_url)
        results.extend(grading_results)
        all_pass = all(gr.passed for gr in grading_results)
        print("PASS" if all_pass else "FAIL")

        # Test 3: N-gram Speculation
        print("Running: N-gram Speculation ...", end=" ", flush=True)
        r = await test_ngram_speculation(client, args.base_url)
        results.append(r)
        print("PASS" if r.passed else "FAIL")

        # Test 4: Throughput Baseline
        print("Running: Throughput Baseline (5 prompts) ...", end=" ", flush=True)
        r = await test_throughput_baseline(client, args.base_url)
        results.append(r)
        print("PASS" if r.passed else "FAIL")

    # Summary
    print_summary_table(results)

    all_passed = all(r.passed for r in results)
    if all_passed:
        print("All tests PASSED.")
    else:
        failed = [r.name for r in results if not r.passed]
        print(f"FAILED: {', '.join(failed)}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
