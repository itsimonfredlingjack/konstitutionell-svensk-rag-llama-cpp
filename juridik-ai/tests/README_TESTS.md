# Unit Tests for output_formatter.py

## Quick Start

```bash
# Navigate to project root
cd /home/dev/juridik-ai

# Run all tests
python -m pytest tests/test_output_formatter.py -v

# Run with minimal output
python -m pytest tests/test_output_formatter.py

# Run specific test class
python -m pytest tests/test_output_formatter.py::TestExtractSections -v

# Run specific test
python -m pytest tests/test_output_formatter.py::TestJuridiskLoggbok::test_create_default_loggbok -v
```

## What's Tested

### 1. JuridiskLoggbok Dataclass (4 tests)
The legal log book data structure used to store formatted legal review information.

**Key test scenarios:**
- Default field initialization
- Custom value assignment
- Date formatting validation
- Mutable field independence between instances

### 2. extract_sections() Function (21 tests)
Extracts structured information from raw AI output using regex patterns.

**Tested extraction types:**
- **Bedömning/Assessment:** BEDÖMNING, ANALYS, or 🔍 headers
- **Risker/Risks:** RISK or ⚠️ headers with severity levels
  - Low (Låg) = Green risk
  - Medium (Medel) = Yellow risk  
  - High (Hög) = Red risk
- **Lagrum/Law References:** § patterns with law names (SoL, LSS, etc.)
- **Saknas/Missing:** Documents or items missing (- bullet lists)
- **Åtgärder/Actions:** Numbered action items (1. 2. 3. format)

### 3. format_loggbok() Function (16 tests)
Formats extracted data into a readable Swedish legal log book output.

**Tested formatting:**
- Complete loggbooks with all sections
- Minimal loggbooks with defaults
- Emoji risk indicators (🟢 🟡 🔴)
- Optional sections (JO-beslut, dokumentation)
- Default actions when none provided
- Proper section headers and separators

### 4. process_raw_output() Function (6 tests)
End-to-end processing from raw AI output to formatted loggbook.

**Tested scenarios:**
- With metadata (arende, kalla, myndighet)
- Without metadata
- Partial metadata
- Complete realistic legal review text

### 5. Edge Cases (9 tests)
Robustness and boundary condition testing.

**Tested edge cases:**
- Swedish characters: åäö
- Case-insensitive headers
- Extra whitespace
- Missing closing markers
- Very long text strings
- Multi-line descriptions
- Mixed bullet point styles

## Test Structure

Each test follows the **Arrange-Act-Assert** pattern:

```python
def test_example():
    """Clear test description."""
    # ARRANGE - Set up test data
    raw_text = "BEDÖMNING:\nTest content."
    
    # ACT - Execute function
    result = extract_sections(raw_text)
    
    # ASSERT - Verify expected behavior
    assert "Test content" in result['bedomning']
```

## Swedish Content in Tests

All tests include Swedish legal terminology to ensure the formatter works correctly with Swedish documents:

- **Terms:** lagrum (law), risknivå (risk level), bedömning (assessment)
- **Levels:** Låg (Low), Medel (Medium), Hög (High)
- **Headers:** BEDÖMNING, ANALYS, SAKNAS, NÄSTA STEG, ÅTGÄRD
- **Legal references:** SoL (Sociallagen), LSS, Förvaltningslagen, JO-beslut

## Test Isolation

- Tests are independent and order-independent
- No shared state between tests
- Each test sets up its own fixtures
- No external dependencies (file I/O, network, databases)

## Coverage Summary

| Component | Tests | Status |
|-----------|-------|--------|
| JuridiskLoggbok | 4 | PASS |
| extract_sections() | 21 | PASS |
| format_loggbok() | 16 | PASS |
| process_raw_output() | 6 | PASS |
| Edge Cases | 9 | PASS |
| **TOTAL** | **56** | **PASS** |

## Requirements

- Python 3.14.0 or compatible
- pytest 9.0.1 or compatible
- No additional dependencies (uses standard library only)

## File Locations

- Source: `/home/dev/juridik-ai/workflows/output_formatter.py`
- Tests: `/home/dev/juridik-ai/tests/test_output_formatter.py`
- Summary: `/home/dev/juridik-ai/tests/TEST_SUMMARY.md`
