#!/usr/bin/env python3
"""
Code Pattern Extractor
======================
Extraherar kod från Python/TypeScript filer och skapar träningsexempel.
"""

import ast
import json
import re
from pathlib import Path


def extract_python_functions(content: str, filepath: str) -> list[dict]:
    """Extrahera funktioner från Python-fil."""
    examples = []

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return examples

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            # Hämta docstring
            docstring = ast.get_docstring(node) or ""

            # Hoppa över privata funktioner utan docstring
            if node.name.startswith("_") and not docstring:
                continue

            # Hämta funktionskod
            try:
                start_line = node.lineno - 1
                end_line = node.end_lineno
                lines = content.split("\n")[start_line:end_line]
                func_code = "\n".join(lines)
            except Exception:
                continue

            # Skapa instruktion baserat på funktionsnamn och docstring
            if docstring:
                instruction = f"Implementera en Python-funktion: {docstring.split('.')[0]}"
            else:
                # Generera beskrivning från funktionsnamn
                name_words = re.sub(r"([A-Z])", r" \1", node.name).replace("_", " ").strip()
                is_async = isinstance(node, ast.AsyncFunctionDef)
                prefix = "async " if is_async else ""
                instruction = f"Skapa en {prefix}Python-funktion som {name_words.lower()}"

            examples.append(
                {
                    "instruction": instruction,
                    "output": f"```python\n{func_code}\n```\n\nDenna funktion finns i `{filepath}`.",
                }
            )

    return examples


def extract_python_classes(content: str, filepath: str) -> list[dict]:
    """Extrahera klasser från Python-fil."""
    examples = []

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return examples

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            docstring = ast.get_docstring(node) or ""

            # Hämta klasskod (begränsa till 100 rader)
            try:
                start_line = node.lineno - 1
                end_line = min(node.end_lineno, start_line + 100)
                lines = content.split("\n")[start_line:end_line]
                class_code = "\n".join(lines)
                if node.end_lineno > start_line + 100:
                    class_code += "\n    # ... (truncated)"
            except Exception:
                continue

            if docstring:
                instruction = f"Implementera en Python-klass: {docstring.split('.')[0]}"
            else:
                name_words = re.sub(r"([A-Z])", r" \1", node.name).strip()
                instruction = f"Skapa en Python-klass för {name_words.lower()}"

            examples.append(
                {
                    "instruction": instruction,
                    "output": f"```python\n{class_code}\n```\n\nKlassen finns i `{filepath}`.",
                }
            )

    return examples


def extract_typescript_patterns(content: str, filepath: str) -> list[dict]:
    """Extrahera patterns från TypeScript/React filer."""
    examples = []

    # React komponenter
    component_pattern = (
        r"(?:export\s+)?(?:const|function)\s+(\w+)\s*[=:]\s*(?:\([^)]*\)|[^=]*)\s*(?:=>|{)"
    )
    for match in re.finditer(component_pattern, content):
        name = match.group(1)
        if name[0].isupper():  # React komponenter börjar med stor bokstav
            # Hitta hela komponenten (förenklad)
            start = match.start()
            # Hitta matchande bracket
            depth = 0
            end = start
            in_string = False
            for i, char in enumerate(content[start:]):
                if char in "\"'`" and content[start + i - 1] != "\\":
                    in_string = not in_string
                if not in_string:
                    if char == "{":
                        depth += 1
                    elif char == "}":
                        depth -= 1
                        if depth == 0:
                            end = start + i + 1
                            break

            if end > start:
                component_code = content[start:end]
                if len(component_code) < 3000:  # Max storlek
                    name_formatted = re.sub(r"([A-Z])", r" \1", name).strip().lower()
                    examples.append(
                        {
                            "instruction": f"Skapa en React-komponent för {name_formatted}",
                            "output": f"```typescript\n{component_code}\n```\n\nKomponenten finns i `{filepath}`.",
                        }
                    )

    # TypeScript interfaces
    interface_pattern = r"(?:export\s+)?interface\s+(\w+)\s*{([^}]+)}"
    for match in re.finditer(interface_pattern, content):
        name, body = match.groups()
        name_formatted = re.sub(r"([A-Z])", r" \1", name).strip().lower()
        examples.append(
            {
                "instruction": f"Definiera ett TypeScript interface för {name_formatted}",
                "output": f"```typescript\ninterface {name} {{{body}}}\n```",
            }
        )

    # Custom hooks
    hook_pattern = r"export\s+function\s+(use\w+)\s*\([^)]*\)[^{]*{"
    for match in re.finditer(hook_pattern, content):
        name = match.group(1)
        # Extrahera hook (förenklad)
        start = match.start()
        end = content.find("\n\n", start + 100) or start + 500
        hook_code = content[start:end]

        name_formatted = re.sub(r"([A-Z])", r" \1", name[3:]).strip().lower()
        examples.append(
            {
                "instruction": f"Implementera en React hook: {name_formatted}",
                "output": f"```typescript\n{hook_code}\n```",
            }
        )

    return examples


def process_directory(base_dir: str, patterns: list[str]) -> list[dict]:
    """Process alla filer i katalogen."""
    all_examples = []
    base_path = Path(base_dir)

    for pattern in patterns:
        for filepath in base_path.glob(pattern):
            if not filepath.is_file():
                continue

            try:
                content = filepath.read_text(encoding="utf-8")
            except Exception as e:
                print(f"  Skip: {filepath} ({e})")
                continue

            rel_path = str(filepath.relative_to(base_path))

            if filepath.suffix == ".py":
                examples = extract_python_functions(content, rel_path)
                examples.extend(extract_python_classes(content, rel_path))
            elif filepath.suffix in [".ts", ".tsx"]:
                examples = extract_typescript_patterns(content, rel_path)
            else:
                continue

            if examples:
                print(f"  {rel_path}: {len(examples)} examples")
                all_examples.extend(examples)

    return all_examples


def main():
    base_dir = "/home/ai-server/01_PROJECTS/01_AI-VIBE-WORLD"
    output_file = f"{base_dir}/data/code_patterns_training.jsonl"

    print("=" * 60)
    print("Code Pattern Extractor")
    print("=" * 60)

    # Python patterns
    print("\nExtracting Python patterns...")
    py_examples = process_directory(
        base_dir,
        [
            "app/**/*.py",
        ],
    )

    # TypeScript patterns
    print("\nExtracting TypeScript patterns...")
    ts_examples = process_directory(
        base_dir,
        [
            "frontend/src/**/*.ts",
            "frontend/src/**/*.tsx",
        ],
    )

    all_examples = py_examples + ts_examples

    # Filtrera duplicat och för korta
    seen = set()
    unique_examples = []
    for ex in all_examples:
        key = ex["instruction"][:50]
        if key not in seen and len(ex["output"]) > 100:
            seen.add(key)
            unique_examples.append(ex)

    # Spara
    print(f"\nSaving {len(unique_examples)} examples to {output_file}")
    with open(output_file, "w", encoding="utf-8") as f:
        for ex in unique_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print("Done!")


if __name__ == "__main__":
    main()
