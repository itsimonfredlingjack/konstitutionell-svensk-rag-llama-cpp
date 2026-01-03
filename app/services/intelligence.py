"""
Intelligence Layer - Backend smarts for elite-class data delivery

Features:
1. Project Awareness Injection - Dynamic context from file structure
2. Pre-Flight Syntax Check - AST validation with self-correction loop
3. Structured Output Enforcement - Force JSON responses when needed
"""

import ast
import os
import re
import json
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Directories and patterns to ignore when building project structure
IGNORE_DIRS = {
    'node_modules', '.git', '__pycache__', '.venv', 'venv',
    '.idea', '.vscode', 'dist', 'build', '.next', '.cache',
    'coverage', '.pytest_cache', '.mypy_cache', 'egg-info',
    '.eggs', '*.egg-info'
}

IGNORE_FILES = {
    '.DS_Store', 'Thumbs.db', '*.pyc', '*.pyo', '*.so',
    '*.lock', 'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml'
}

# Code block regex for extracting from model output
CODE_BLOCK_PATTERN = re.compile(
    r'```(\w+)?\s*\n(.*?)```',
    re.DOTALL
)

# JSON extraction pattern
JSON_PATTERN = re.compile(
    r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}|\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]',
    re.DOTALL
)


class OutputFormat(str, Enum):
    """Supported output formats"""
    TEXT = "text"
    JSON = "json"
    CODE = "code"


@dataclass
class SyntaxCheckResult:
    """Result of syntax validation"""
    is_valid: bool
    language: str
    code: str
    error_message: Optional[str] = None
    error_line: Optional[int] = None
    corrected_code: Optional[str] = None


@dataclass
class ProjectContext:
    """Project structure context for model injection"""
    root_path: str
    file_tree: str
    file_count: int
    directory_count: int
    languages_detected: List[str] = field(default_factory=list)
    key_files: List[str] = field(default_factory=list)


# =============================================================================
# 1. PROJECT AWARENESS INJECTION
# =============================================================================

def get_project_structure(
    root_path: str = "/home/ai-server/local-llm-backend",
    max_depth: int = 4,
    include_sizes: bool = False
) -> ProjectContext:
    """
    Generate a filtered file tree for model context injection.

    Args:
        root_path: Root directory to scan
        max_depth: Maximum directory depth
        include_sizes: Include file sizes in output

    Returns:
        ProjectContext with file tree and metadata
    """
    root = Path(root_path)
    if not root.exists():
        logger.warning(f"Project root not found: {root_path}")
        return ProjectContext(
            root_path=root_path,
            file_tree="[Project not found]",
            file_count=0,
            directory_count=0
        )

    lines = []
    file_count = 0
    dir_count = 0
    languages = set()
    key_files = []

    # Language detection by extension
    lang_map = {
        '.py': 'Python',
        '.js': 'JavaScript',
        '.ts': 'TypeScript',
        '.tsx': 'TypeScript/React',
        '.jsx': 'JavaScript/React',
        '.html': 'HTML',
        '.css': 'CSS',
        '.scss': 'SCSS',
        '.json': 'JSON',
        '.yaml': 'YAML',
        '.yml': 'YAML',
        '.md': 'Markdown',
        '.sh': 'Shell',
        '.sql': 'SQL',
        '.rs': 'Rust',
        '.go': 'Go',
    }

    # Key file patterns
    key_patterns = [
        'main.py', 'app.py', 'index.ts', 'index.js',
        'package.json', 'requirements.txt', 'pyproject.toml',
        'Dockerfile', 'docker-compose.yml', '.env.example',
        'README.md', 'Makefile', 'setup.py'
    ]

    def should_ignore(name: str, is_dir: bool) -> bool:
        """Check if path should be ignored"""
        if is_dir:
            return name in IGNORE_DIRS or name.startswith('.')
        return any(
            name == pat or (pat.startswith('*') and name.endswith(pat[1:]))
            for pat in IGNORE_FILES
        )

    def build_tree(path: Path, prefix: str = "", depth: int = 0):
        nonlocal file_count, dir_count

        if depth > max_depth:
            return

        try:
            entries = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except PermissionError:
            return

        # Filter entries
        entries = [e for e in entries if not should_ignore(e.name, e.is_dir())]

        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            new_prefix = prefix + ("    " if is_last else "│   ")

            if entry.is_dir():
                dir_count += 1
                lines.append(f"{prefix}{connector}{entry.name}/")
                build_tree(entry, new_prefix, depth + 1)
            else:
                file_count += 1
                suffix = entry.suffix.lower()

                # Detect language
                if suffix in lang_map:
                    languages.add(lang_map[suffix])

                # Check for key files
                if entry.name in key_patterns:
                    key_files.append(str(entry.relative_to(root)))

                # Format line
                size_str = ""
                if include_sizes:
                    try:
                        size = entry.stat().st_size
                        if size > 1024 * 1024:
                            size_str = f" ({size / 1024 / 1024:.1f}MB)"
                        elif size > 1024:
                            size_str = f" ({size / 1024:.1f}KB)"
                    except OSError:
                        pass

                lines.append(f"{prefix}{connector}{entry.name}{size_str}")

    # Build the tree
    lines.append(f"{root.name}/")
    build_tree(root)

    return ProjectContext(
        root_path=root_path,
        file_tree="\n".join(lines),
        file_count=file_count,
        directory_count=dir_count,
        languages_detected=sorted(languages),
        key_files=key_files
    )


def build_context_prompt(project: ProjectContext) -> str:
    """
    Build a context-aware system prompt addition.

    Args:
        project: ProjectContext from get_project_structure()

    Returns:
        String to append to system prompt
    """
    return f"""
## PROJECT CONTEXT

Du arbetar med följande projektstruktur:

```
{project.file_tree}
```

**Projektöversikt:**
- Filer: {project.file_count}
- Mappar: {project.directory_count}
- Språk: {', '.join(project.languages_detected) if project.languages_detected else 'Okänt'}
- Viktiga filer: {', '.join(project.key_files) if project.key_files else 'Inga hittade'}

När du skriver kod, använd denna struktur för att:
1. Referera till rätt filsökvägar
2. Följa projektets konventioner
3. Förstå var ny kod ska placeras
"""


# =============================================================================
# 2. PRE-FLIGHT SYNTAX CHECK
# =============================================================================

def extract_code_blocks(text: str) -> List[Tuple[str, str]]:
    """
    Extract code blocks from markdown-formatted text.

    Args:
        text: Text containing ```language\ncode``` blocks

    Returns:
        List of (language, code) tuples
    """
    blocks = []
    for match in CODE_BLOCK_PATTERN.finditer(text):
        language = match.group(1) or "unknown"
        code = match.group(2).strip()
        blocks.append((language.lower(), code))
    return blocks


def validate_python_syntax(code: str) -> SyntaxCheckResult:
    """
    Validate Python code syntax using AST parser.

    Args:
        code: Python code string

    Returns:
        SyntaxCheckResult with validation details
    """
    try:
        ast.parse(code)
        return SyntaxCheckResult(
            is_valid=True,
            language="python",
            code=code
        )
    except SyntaxError as e:
        return SyntaxCheckResult(
            is_valid=False,
            language="python",
            code=code,
            error_message=str(e.msg) if e.msg else str(e),
            error_line=e.lineno
        )


def build_correction_prompt(result: SyntaxCheckResult) -> str:
    """
    Build a prompt for self-correction when syntax error is detected.

    Args:
        result: Failed SyntaxCheckResult

    Returns:
        Prompt for model to correct the code
    """
    return f"""
## SYNTAX ERROR DETECTED

Din kod innehåller ett syntaxfel som måste korrigeras:

**Fel:** {result.error_message}
**Rad:** {result.error_line}

**Felaktig kod:**
```python
{result.code}
```

Korrigera koden och returnera ENDAST den korrigerade versionen utan förklaringar.
Svara med:
```python
[korrigerad kod här]
```
"""


def validate_code_in_response(text: str) -> Tuple[bool, List[SyntaxCheckResult], str]:
    """
    Validate all code blocks in a response.

    Args:
        text: Full response text with potential code blocks

    Returns:
        Tuple of (all_valid, results, corrected_text)
    """
    blocks = extract_code_blocks(text)
    results = []
    all_valid = True
    corrections_needed = []

    for language, code in blocks:
        if language == "python":
            result = validate_python_syntax(code)
            results.append(result)
            if not result.is_valid:
                all_valid = False
                corrections_needed.append((code, result))

    # For now, return original text - correction happens in orchestrator
    return all_valid, results, text


# =============================================================================
# 3. STRUCTURED OUTPUT ENFORCEMENT
# =============================================================================

def build_json_enforcement_prompt(schema_hint: Optional[Dict] = None) -> str:
    """
    Build prompt addition to enforce JSON output.

    Args:
        schema_hint: Optional JSON schema for structure guidance

    Returns:
        Prompt addition for JSON enforcement
    """
    schema_str = ""
    if schema_hint:
        schema_str = f"""
Använd följande struktur:
```json
{json.dumps(schema_hint, indent=2, ensure_ascii=False)}
```
"""

    return f"""
## OUTPUT FORMAT: JSON

VIKTIGT: Svara ENDAST med valid JSON. Ingen annan text.
{schema_str}
Regler:
- Börja med {{ eller [
- Sluta med }} eller ]
- Använd dubbla citattecken för strängar
- Inga trailing commas
- Inga kommentarer
"""


def extract_json_from_response(text: str) -> Tuple[bool, Any, str]:
    """
    Extract and validate JSON from model response.

    Args:
        text: Response text that should contain JSON

    Returns:
        Tuple of (success, parsed_json_or_error, raw_json_string)
    """
    # First, try to parse the entire text as JSON
    try:
        parsed = json.loads(text.strip())
        return True, parsed, text.strip()
    except json.JSONDecodeError:
        pass

    # Try to find JSON in code blocks
    blocks = extract_code_blocks(text)
    for lang, code in blocks:
        if lang in ('json', 'unknown', ''):
            try:
                parsed = json.loads(code)
                return True, parsed, code
            except json.JSONDecodeError:
                continue

    # Try regex extraction
    matches = JSON_PATTERN.findall(text)
    for match in matches:
        try:
            parsed = json.loads(match)
            return True, parsed, match
        except json.JSONDecodeError:
            continue

    return False, "No valid JSON found in response", ""


def validate_json_against_schema(
    data: Any,
    required_fields: List[str]
) -> Tuple[bool, List[str]]:
    """
    Simple validation of JSON against required fields.

    Args:
        data: Parsed JSON data
        required_fields: List of required field names

    Returns:
        Tuple of (is_valid, missing_fields)
    """
    if not isinstance(data, dict):
        return False, required_fields

    missing = [f for f in required_fields if f not in data]
    return len(missing) == 0, missing


# =============================================================================
# INTELLIGENCE MANAGER
# =============================================================================

class IntelligenceManager:
    """
    Central manager for all intelligence features.
    Integrates with the orchestrator for enhanced responses.
    """

    def __init__(self, project_root: str = "/home/ai-server/local-llm-backend"):
        self.project_root = project_root
        self._project_context: Optional[ProjectContext] = None
        self._context_prompt: Optional[str] = None

    def get_project_context(self, force_refresh: bool = False) -> ProjectContext:
        """Get cached or fresh project context"""
        if self._project_context is None or force_refresh:
            self._project_context = get_project_structure(self.project_root)
            self._context_prompt = build_context_prompt(self._project_context)
            logger.info(
                f"Project context loaded: {self._project_context.file_count} files, "
                f"{self._project_context.directory_count} dirs"
            )
        return self._project_context

    def get_enhanced_system_prompt(
        self,
        base_prompt: str,
        include_project: bool = True,
        output_format: OutputFormat = OutputFormat.TEXT,
        json_schema: Optional[Dict] = None
    ) -> str:
        """
        Build enhanced system prompt with intelligence features.

        Args:
            base_prompt: Original system prompt
            include_project: Include project structure context
            output_format: Desired output format
            json_schema: Schema hint for JSON output

        Returns:
            Enhanced system prompt
        """
        parts = [base_prompt]

        if include_project:
            self.get_project_context()
            if self._context_prompt:
                parts.append(self._context_prompt)

        if output_format == OutputFormat.JSON:
            parts.append(build_json_enforcement_prompt(json_schema))

        return "\n\n".join(parts)

    def process_response(
        self,
        response: str,
        validate_python: bool = True,
        expect_json: bool = False,
        required_json_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Process model response with intelligence checks.

        Args:
            response: Raw model response
            validate_python: Check Python syntax in code blocks
            expect_json: Parse and validate JSON output
            required_json_fields: Required fields for JSON validation

        Returns:
            Dict with processed response and metadata
        """
        result = {
            "original": response,
            "processed": response,
            "syntax_valid": True,
            "syntax_errors": [],
            "json_valid": None,
            "json_data": None,
            "needs_correction": False,
            "correction_prompt": None
        }

        # Python syntax validation
        if validate_python:
            all_valid, checks, _ = validate_code_in_response(response)
            result["syntax_valid"] = all_valid

            for check in checks:
                if not check.is_valid:
                    result["syntax_errors"].append({
                        "error": check.error_message,
                        "line": check.error_line,
                        "code_snippet": check.code[:100] + "..." if len(check.code) > 100 else check.code
                    })
                    result["needs_correction"] = True
                    result["correction_prompt"] = build_correction_prompt(check)

        # JSON validation
        if expect_json:
            success, data, raw = extract_json_from_response(response)
            result["json_valid"] = success

            if success:
                result["json_data"] = data
                result["processed"] = raw

                if required_json_fields:
                    fields_valid, missing = validate_json_against_schema(data, required_json_fields)
                    if not fields_valid:
                        result["json_valid"] = False
                        result["json_data"] = {"error": f"Missing fields: {missing}"}
            else:
                result["json_data"] = {"error": data}

        return result


# Global intelligence manager instance
intelligence = IntelligenceManager()


def get_intelligence() -> IntelligenceManager:
    """Dependency injection helper"""
    return intelligence
