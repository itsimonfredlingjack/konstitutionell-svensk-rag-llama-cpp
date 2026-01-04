# Testing Quick Start Guide

**TL;DR:** Constitutional AI has ~15-20% test coverage. This document shows you exactly what's tested, what's missing, and how to add tests.

---

## What's Currently Tested ✅

### Backend Output Formatter (100% covered)
```bash
cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/juridik-ai
pytest tests/test_output_formatter.py -v
# Result: 56 tests, ALL PASSING
```

### Frontend Query Routing (95% covered)
```bash
cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/apps/constitutional-gpt
npm run test:acceptance
# Result: Query pattern matching validated
```

---

## What's NOT Tested ❌

| Module | Lines | Tests | Priority |
|--------|-------|-------|----------|
| constitutional_cli.py | 991 | 0 | P0 |
| API Endpoints | 300+ | 0 | P0 |
| Frontend Components | 2,500 | 0 | P1 |
| RAG Orchestration | 500+ | 0 | P1 |
| Search Logic | 400+ | 0 | P1 |
| Database Layer | 500+ | 0 | P1 |

**Total gap:** 1,000+ lines untested

---

## Run Existing Tests

### All tests
```bash
cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI
pytest juridik-ai/tests/ -v          # Backend tests
npm run test --prefix apps/constitutional-gpt  # Frontend acceptance tests
```

### Specific tests
```bash
# Output formatter only
pytest juridik-ai/tests/test_output_formatter.py -v

# Riksdagen client only
pytest juridik-ai/tests/test_riksdagen_client.py -v

# Frontend query acceptance
npm run test:acceptance --prefix apps/constitutional-gpt
```

---

## Add New Tests: 3-Step Process

### Step 1: Create test file

```python
# File: juridik-ai/tests/test_your_module.py
import pytest
from unittest.mock import Mock, patch
from your_module import function_to_test

class TestYourFunction:
    """Test suite for your_function"""

    def test_happy_path(self):
        """Test with valid input"""
        # ARRANGE
        input_data = {"key": "value"}

        # ACT
        result = function_to_test(input_data)

        # ASSERT
        assert result["status"] == "success"
```

### Step 2: Run the test

```bash
cd juridik-ai
pytest tests/test_your_module.py -v
```

### Step 3: Commit

```bash
git add tests/test_your_module.py
git commit -m "test: add your_module unit tests"
```

---

## Testing Checklist: By Module

### [ ] CLI System (constitutional_cli.py)
**Effort:** 1 week | **Tests needed:** 30+

**Test cases to add:**
```
[ ] test_search_command_valid_query
[ ] test_search_command_empty_query
[ ] test_status_command
[ ] test_harvest_command_start
[ ] test_harvest_command_stop
[ ] test_embed_command
[ ] test_eval_command
[ ] test_env_variable_loading
[ ] test_config_validation
[ ] test_help_text
```

### [ ] API Endpoints (FastAPI)
**Effort:** 1 week | **Tests needed:** 25+

**Test cases to add:**
```
[ ] test_search_endpoint_valid_query
[ ] test_search_endpoint_timeout
[ ] test_status_endpoint_health
[ ] test_query_endpoint_streaming
[ ] test_ingest_endpoint_valid_file
[ ] test_websocket_connection
[ ] test_api_rate_limiting
[ ] test_invalid_endpoint_404
```

### [ ] RAG Evaluation (eval_runner.py)
**Effort:** 3 days | **Tests needed:** 15+

**Test cases to add:**
```
[ ] test_metrics_calculation
[ ] test_result_json_format
[ ] test_api_timeout_handling
[ ] test_comparison_with_baseline
```

### [ ] Frontend Components
**Effort:** 2 weeks | **Tests needed:** 100+

**Test cases to add:**
```
[ ] test_render_query_input
[ ] test_submit_query
[ ] test_display_response
[ ] test_stream_handling
[ ] test_cite_sources
[ ] test_conversation_history
[ ] test_mode_selection
[ ] test_error_display
```

### [ ] Search Logic
**Effort:** 1 week | **Tests needed:** 40+

**Test cases to add:**
```
[ ] test_semantic_search
[ ] test_bm25_search
[ ] test_hybrid_ranking
[ ] test_result_deduplication
[ ] test_citation_extraction
```

---

## Common Testing Patterns

### Pattern 1: Mock HTTP calls
```python
@patch('httpx.AsyncClient.post')
def test_api_call(mock_post):
    mock_post.return_value = Mock(json=lambda: {"status": "ok"})
    result = function_making_http_call()
    assert result["status"] == "ok"
```

### Pattern 2: Test with different inputs
```python
@pytest.mark.parametrize("input,expected", [
    ("query1", "result1"),
    ("query2", "result2"),
])
def test_various_inputs(input, expected):
    assert function(input) == expected
```

### Pattern 3: Test error handling
```python
def test_handles_error():
    with pytest.raises(ValueError):
        function_that_raises_error()
```

---

## Coverage: Before & After

### Before (Today)
```
Total Lines: 8,000+
Tests: ~56
Coverage: ~15%
Critical Path: ~5% ❌ CRITICAL
```

### After (8 weeks)
```
Total Lines: 8,000+
Tests: 400+ ✅
Coverage: 75%+
Critical Path: 95% ✅
```

---

## Files to Modify/Create

### Configuration (Week 1)
- [ ] Create `juridik-ai/pytest.ini`
- [ ] Create `juridik-ai/tests/conftest.py`
- [ ] Create `.github/workflows/test.yml` (CI/CD)

### Phase 1 (Week 1-2)
- [ ] Create `juridik-ai/tests/test_cli.py` (30+ tests)
- [ ] Create `tests/test_api_endpoints.py` (25+ tests)
- [ ] Create `eval/tests/test_ragas_wrapper.py` (15+ tests)

### Phase 2 (Week 3-4)
- [ ] Create `juridik-ai/tests/test_cli_app.py`
- [ ] Create `juridik-ai/tests/test_ollama_client.py`
- [ ] Create `juridik-ai/tests/test_system_monitor.py`
- [ ] Create `apps/constitutional-gpt/__tests__/` directory
- [ ] Create `apps/constitutional-gpt/jest.config.js`

### Phase 3 (Week 5-8)
- [ ] Create `tests/test_chromadb_integration.py`
- [ ] Create `tests/test_e2e_workflows.py`
- [ ] Create `tests/test_performance.py`
- [ ] Create `tests/test_security.py`

---

## Testing Commands Cheat Sheet

```bash
# Run all tests
pytest tests/ -v
npm run test

# Run with coverage
pytest tests/ --cov=. --cov-report=html
npm run test:coverage

# Run specific file
pytest tests/test_output_formatter.py -v
npm run test -- --testNamePattern="SearchComponent"

# Run and watch for changes
pytest --watch
npm run test:watch

# Show coverage report
open htmlcov/index.html

# Run only fast tests (exclude slow)
pytest -m "not slow"

# Run specific test by name
pytest -k "test_search_valid"
npm run test -- -t "test_render_query_input"
```

---

## Success Criteria

### Week 1: CLI & API
- [ ] 55+ new tests written
- [ ] pytest.ini configured
- [ ] conftest.py with fixtures
- [ ] All tests passing
- [ ] Coverage >70% for tested modules

### Week 2: Evaluation & Services
- [ ] 40+ new tests written
- [ ] RAG evaluation tested
- [ ] CLI services covered
- [ ] CI/CD pipeline active

### Week 4: Frontend & Integration
- [ ] 100+ component tests
- [ ] Jest configured
- [ ] Coverage reports generated
- [ ] Regression testing enabled

### Week 8: Complete
- [ ] 400+ total tests
- [ ] 75%+ coverage
- [ ] 95% critical path coverage
- [ ] Performance baselines
- [ ] Security tests passing

---

## Troubleshooting

### Tests not discovering
```bash
# Check pytest can find tests
pytest --collect-only tests/

# Ensure file is named test_*.py or *_test.py
# Ensure functions are named test_*
```

### Async test failures
```bash
# Add to conftest.py:
import pytest_asyncio
pytestmark = pytest.mark.asyncio

# Then use:
@pytest.mark.asyncio
async def test_async_function():
    result = await async_function()
```

### Mock not working
```python
# Must patch where it's USED, not where it's DEFINED
@patch('module.where_its_imported.function')  # NOT 'original_module.function'
```

### Coverage reports not showing
```bash
# Install coverage tool
pip install pytest-cov

# Run with coverage
pytest --cov=. --cov-report=html

# View report
open htmlcov/index.html
```

---

## Key Files for Reference

| File | Purpose |
|------|---------|
| `TEST_COVERAGE_ANALYSIS.md` | Detailed analysis of what's tested/untested |
| `TESTING_ROADMAP.md` | Week-by-week implementation plan |
| `TEST_SUMMARY_REPORT.md` | Executive summary with statistics |
| `juridik-ai/tests/test_output_formatter.py` | Example of high-quality tests |
| `apps/constitutional-gpt/test-acceptance.js` | Example of frontend tests |

---

## Next Steps (Today!)

1. **Read** `TEST_COVERAGE_ANALYSIS.md` (10 min)
2. **Review** existing tests in `juridik-ai/tests/test_output_formatter.py` (15 min)
3. **Create** `juridik-ai/pytest.ini` (5 min)
4. **Create** `juridik-ai/tests/conftest.py` (10 min)
5. **Start** writing CLI tests (2-3 hours)

**Total time to get started:** ~1 hour

---

## Questions?

- **What should I test first?** → CLI system (constitutional_cli.py)
- **How many tests should I write?** → 30+ for CLI, 25+ for API
- **How long does it take?** → ~1 hour per 10 tests (with mocking)
- **Where do I put tests?** → `juridik-ai/tests/` for Python, `__tests__/` for TypeScript
- **What if tests fail?** → Fix the code first, then the test

---

**Generated:** 2025-12-31
**Status:** Ready for implementation
**Effort Estimate:** 8 weeks, ~40 hours/week for full coverage

Start with Phase 1: CLI + API (Week 1-2)
