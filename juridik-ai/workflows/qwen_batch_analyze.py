#!/usr/bin/env python3
"""
Batch-analysera juridiska dokument med Qwen 2.5 3B via Ollama.
Kör sekventiellt för att respektera GPU-begränsningar på RTX 2060.
"""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Försök importera ollama, annars använd curl
try:
    import ollama

    USE_OLLAMA_LIB = True
except ImportError:
    USE_OLLAMA_LIB = False
    print("⚠️ ollama-python ej installerat, använder curl")


# Konfiguration
MODEL = "qwen-myndighet"  # Custom model för myndighetssverige
FALLBACK_MODEL = "qwen2.5:3b-instruct"
SYSTEM_PROMPT_PATH = Path("/home/dev/juridik-ai/system-prompts/qwen-myndighet.txt")

# RTX 2060 optimerade inställningar
OPTIONS = {
    "num_ctx": 4096,
    "num_predict": 2048,
    "temperature": 0.3,
    "top_p": 0.9,
    "repeat_penalty": 1.1,
}


def load_system_prompt() -> str:
    """Ladda system prompt från fil."""
    if SYSTEM_PROMPT_PATH.exists():
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return "Du är en svensk juridisk assistent."


def analyze_with_ollama(content: str, task: str = "loggbok") -> dict:
    """Analysera dokument med ollama-python biblioteket."""
    system_prompt = load_system_prompt()

    task_prompts = {
        "loggbok": "Analysera dokumentet och skapa en myndighetsloggbok enligt standardformatet.",
        "risk": "Identifiera risker och brister i myndighetens hantering. Lista varje risk med nivå (Låg/Medel/Hög).",
        "sammanfatta": "Sammanfatta dokumentets innehåll ur ett medborgarperspektiv på max 200 ord.",
        "brister": "Lista dokumentationsbrister, handläggningsfel och saknade handlingar.",
    }

    prompt = f"""
{task_prompts.get(task, task_prompts['loggbok'])}

DOKUMENT:
{content}

OUTPUT:
"""

    try:
        # Försök med custom model först
        response = ollama.generate(model=MODEL, prompt=prompt, options=OPTIONS)
        return {
            "success": True,
            "model": MODEL,
            "response": response["response"],
            "tokens": response.get("eval_count", 0),
        }
    except Exception as e:
        if "not found" in str(e).lower():
            # Fallback till bas-modell
            response = ollama.chat(
                model=FALLBACK_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                options=OPTIONS,
            )
            return {
                "success": True,
                "model": FALLBACK_MODEL,
                "response": response["message"]["content"],
                "tokens": response.get("eval_count", 0),
            }
        raise


def analyze_with_curl(content: str, task: str = "loggbok") -> dict:
    """Analysera dokument med curl (fallback om ollama-python saknas)."""
    system_prompt = load_system_prompt()

    task_prompts = {
        "loggbok": "Analysera dokumentet och skapa en myndighetsloggbok enligt standardformatet.",
        "risk": "Identifiera risker och brister i myndighetens hantering.",
        "sammanfatta": "Sammanfatta dokumentets innehåll ur ett medborgarperspektiv på max 200 ord.",
        "brister": "Lista dokumentationsbrister, handläggningsfel och saknade handlingar.",
    }

    prompt = f"{task_prompts.get(task, task_prompts['loggbok'])}\n\nDOKUMENT:\n{content}\n\nOUTPUT:"

    payload = {
        "model": FALLBACK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": OPTIONS,
    }

    result = subprocess.run(
        ["curl", "-s", "-X", "POST", "http://localhost:11434/api/chat", "-d", json.dumps(payload)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return {"success": False, "error": result.stderr}

    response = json.loads(result.stdout)
    return {
        "success": True,
        "model": FALLBACK_MODEL,
        "response": response.get("message", {}).get("content", ""),
        "tokens": response.get("eval_count", 0),
    }


def analyze_document(content: str, task: str = "loggbok") -> dict:
    """Analysera dokument med tillgänglig metod."""
    if USE_OLLAMA_LIB:
        return analyze_with_ollama(content, task)
    else:
        return analyze_with_curl(content, task)


def batch_analyze(input_dir: Path, output_dir: Path, task: str = "loggbok"):
    """Batch-analysera alla dokument i en katalog."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Hitta alla textfiler
    files = list(input_dir.glob("*.txt")) + list(input_dir.glob("*.md"))

    if not files:
        print(f"Inga dokument hittades i {input_dir}")
        return

    print(f"🔍 Hittade {len(files)} dokument att analysera")
    print(f"📝 Analystyp: {task}")
    print(f"🤖 Modell: {MODEL} (fallback: {FALLBACK_MODEL})")
    print("-" * 50)

    results = []
    start_time = time.time()

    for i, file in enumerate(files, 1):
        print(f"\n[{i}/{len(files)}] Analyserar: {file.name}")

        # Läs dokument
        content = file.read_text(encoding="utf-8")
        print(f"  📄 Storlek: {len(content)} tecken (~{len(content)//4} tokens)")

        # Analysera
        doc_start = time.time()
        result = analyze_document(content, task)
        doc_time = time.time() - doc_start

        if result["success"]:
            # Spara resultat
            output_file = output_dir / f"{file.stem}_analys.md"

            output_content = f"""# Juridisk Analys: {file.name}

**Genererad:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Modell:** {result['model']}
**Analystyp:** {task}
**Tokens:** ~{result['tokens']}

---

{result['response']}

---
*Analyserad med juridik-ai pipeline*
"""
            output_file.write_text(output_content, encoding="utf-8")

            print(f"  ✅ Klar ({doc_time:.1f}s) → {output_file.name}")
            results.append(
                {"file": file.name, "success": True, "time": doc_time, "output": output_file.name}
            )
        else:
            print(f"  ❌ Fel: {result.get('error', 'Okänt fel')}")
            results.append({"file": file.name, "success": False, "error": result.get("error")})

    # Sammanfattning
    total_time = time.time() - start_time
    successful = sum(1 for r in results if r["success"])

    print("\n" + "=" * 50)
    print("BATCH-ANALYS KLAR")
    print("=" * 50)
    print(f"✅ Lyckade: {successful}/{len(files)}")
    print(f"⏱️ Total tid: {total_time:.1f}s")
    print(f"📁 Output: {output_dir}/")

    # Spara sammanfattning
    summary_file = output_dir / "_batch_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": datetime.now().isoformat(),
                "task": task,
                "total_files": len(files),
                "successful": successful,
                "total_time_seconds": total_time,
                "results": results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    return results


def main():
    """CLI för batch-analys."""
    if len(sys.argv) < 2:
        print("Användning: python qwen_batch_analyze.py <input_dir> [output_dir] [task]")
        print("\nTasks: loggbok, risk, sammanfatta, brister")
        print("\nExempel:")
        print("  python qwen_batch_analyze.py ./sections ./output loggbok")
        sys.exit(1)

    input_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("./output")
    task = sys.argv[3] if len(sys.argv) > 3 else "loggbok"

    if not input_dir.exists():
        print(f"Fel: Katalogen {input_dir} finns inte")
        sys.exit(1)

    batch_analyze(input_dir, output_dir, task)


if __name__ == "__main__":
    main()
