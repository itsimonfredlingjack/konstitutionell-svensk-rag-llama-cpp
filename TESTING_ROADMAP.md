# Constitutional AI - Testing Roadmap & Implementation Guide

## Quick Reference: What Needs Testing

### By Priority & Effort

| Priority | Module | Files to Test | Est. Tests | Est. Effort | Timeline |
|----------|--------|---------------|-----------|------------|----------|
| P0 | CLI System | constitutional_cli.py | 30+ | 1 week | Week 1 |
| P0 | API Endpoints | Backend FastAPI | 25+ | 1 week | Week 1-2 |
| P0 | RAG Evaluation | eval_runner.py, ragas_wrapper.py | 15+ | 3 days | Week 2 |
| P1 | CLI Modules | app.py, brain.py, config.py | 50+ | 1 week | Week 3 |
| P1 | Service Layer | ollama_client.py, system_monitor.py, tools.py | 60+ | 1 week | Week 3 |
| P1 | Frontend Components | React components (74 files) | 100+ | 2 weeks | Week 4-5 |
| P2 | Search Logic | hybrid-search.ts, agent-loop.ts | 40+ | 1 week | Week 6 |
| P2 | Database Integration | ChromaDB/Qdrant | 30+ | 1 week | Week 7 |
| P3 | Scrapers | jo_*.py harvest files | 35+ | 1 week | Week 8 |

**Total Effort:** ~8 weeks, ~400+ tests

---

## Phase 1: Critical Path (Weeks 1-2)

### Week 1: CLI & API Testing

#### Task 1.1: CLI System Tests (30+ tests)
**File to create:** `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/juridik-ai/tests/test_cli.py`

**Tests to write:**
```python
# Command parsing and validation
- test_search_command_valid_query
- test_search_command_empty_query
- test_search_command_invalid_flags
- test_status_command
- test_harvest_command_start
- test_harvest_command_stop
- test_harvest_command_status
- test_embed_command_with_source
- test_embed_command_invalid_source
- test_benchmark_command_quick
- test_benchmark_command_full
- test_ingest_command_valid_file
- test_ingest_command_missing_file
- test_eval_command_quick
- test_eval_command_full

# Configuration management
- test_env_variable_loading
- test_config_defaults
- test_config_overrides
- test_config_validation

# Error handling
- test_search_api_timeout
- test_search_network_error
- test_search_malformed_response
- test_command_help_text
- test_command_version
- test_invalid_command

# Exit codes
- test_success_exit_code
- test_error_exit_code
- test_help_exit_code
```

**Mocking strategy:**
```python
@patch('httpx.AsyncClient.post')
@patch('httpx.AsyncClient.get')
@patch.dict(os.environ, {'CONSTITUTIONAL_RAG_API': 'http://test:8000'})
```

---

#### Task 1.2: API Endpoint Tests (25+ tests)
**File to create:** `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/tests/test_api_endpoints.py`

**Tests to write:**
```python
from fastapi.testclient import TestClient

# Search endpoint tests
- test_search_endpoint_valid_query
- test_search_endpoint_empty_query
- test_search_endpoint_special_characters
- test_search_endpoint_swedish_characters
- test_search_endpoint_long_query
- test_search_endpoint_rate_limit
- test_search_endpoint_timeout
- test_search_endpoint_malformed_request

# Status endpoint tests
- test_status_endpoint_health
- test_status_endpoint_db_connection
- test_status_endpoint_ollama_connection
- test_status_response_schema

# Query endpoint tests
- test_query_endpoint_post
- test_query_endpoint_response_streaming
- test_query_endpoint_error_handling

# Document endpoint tests
- test_get_documents_endpoint
- test_get_document_by_id
- test_ingest_documents_endpoint
- test_ingest_invalid_format

# WebSocket tests
- test_ws_connection
- test_ws_message_handling
- test_ws_disconnect
```

**Setup:**
```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
```

---

### Week 2: RAG Evaluation & Service Tests

#### Task 2.1: RAG Evaluation Unit Tests (15+ tests)
**File to create:** `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/eval/tests/test_ragas_wrapper.py`

**Tests to write:**
```python
# RAGAS wrapper tests
- test_metrics_provider_initialization
- test_get_metrics_valid_query
- test_get_metrics_invalid_query
- test_get_metrics_timeout_handling
- test_metrics_calculation_accuracy
- test_metrics_calculation_precision
- test_metrics_calculation_recall

# Result formatting tests
- test_result_json_schema
- test_result_timestamp_format
- test_result_aggregation

# Error handling tests
- test_ragas_api_unreachable
- test_ragas_parsing_error
- test_ragas_timeout
- test_ragas_invalid_response

# Benchmark runner tests
- test_eval_runner_quick_mode
- test_eval_runner_full_mode
```

---

#### Task 2.2: Pytest Configuration
**File to create:** `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/juridik-ai/pytest.ini`

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    --strict-markers
    --cov=..
    --cov-report=html
    --cov-report=term-missing
    --cov-fail-under=70
filterwarnings =
    ignore::DeprecationWarning
    ignore::PendingDeprecationWarning
markers =
    unit: Unit tests (no external dependencies)
    integration: Integration tests (may require services)
    slow: Slow tests (>1s execution time)
    e2e: End-to-end tests
```

---

#### Task 2.3: Pytest Fixtures
**File to create:** `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/juridik-ai/tests/conftest.py`

```python
import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock
import tempfile

@pytest.fixture
def constitutional_config():
    """Test configuration"""
    return {
        "rag_api": "http://localhost:8900",
        "qdrant_host": "localhost",
        "qdrant_port": 6333,
        "ollama_api": "http://localhost:11434",
        "n8n_api": "http://localhost:5678",
    }

@pytest.fixture
def mock_http_client():
    """Mock HTTP client for API testing"""
    return AsyncMock()

@pytest.fixture
def temp_dir():
    """Temporary directory for file operations"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

@pytest.fixture
def mock_qdrant_client():
    """Mock Qdrant client"""
    client = Mock()
    client.search.return_value = [
        Mock(id=1, score=0.95, payload={"text": "Sample document"})
    ]
    return client

@pytest.fixture
def sample_query():
    """Sample query for testing"""
    return "Vad säger Regeringsformen om yttrandefrihet?"
```

---

## Phase 2: Service Layer Testing (Weeks 3-4)

### Week 3: CLI Service Tests

#### Task 3.1: CLI App Tests (25+ tests)
**File to create:** `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/juridik-ai/tests/test_cli_app.py`

**Tests to write:**
```python
from juridik-ai.cli.app import ConstitutionalApp

# Initialization tests
- test_app_initialization
- test_app_load_config
- test_app_validate_dependencies

# Command routing tests
- test_route_search_command
- test_route_status_command
- test_route_harvest_command
- test_route_invalid_command

# Error handling tests
- test_handle_missing_config
- test_handle_api_unavailable
- test_handle_malformed_args
```

---

#### Task 3.2: Ollama Client Tests (20+ tests)
**File to create:** `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/juridik-ai/tests/test_ollama_client.py`

**Tests to write:**
```python
from juridik-ai.cli.ollama_client import OllamaClient

# Connection tests
- test_ollama_client_initialization
- test_ollama_connection_success
- test_ollama_connection_timeout
- test_ollama_connection_refused

# Model tests
- test_list_available_models
- test_load_model
- test_model_already_loaded
- test_load_model_failure

# Generation tests
- test_generate_simple_prompt
- test_generate_with_context
- test_generate_timeout
- test_generate_invalid_model
- test_generate_streaming

# Cleanup tests
- test_unload_model
- test_cleanup_on_shutdown
```

---

#### Task 3.3: System Monitor Tests (15+ tests)
**File to create:** `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/juridik-ai/tests/test_system_monitor.py`

**Tests to write:**
```python
from juridik-ai.cli.system_monitor import SystemMonitor

# CPU monitoring
- test_get_cpu_usage
- test_cpu_threshold_warning
- test_cpu_over_threshold

# Memory monitoring
- test_get_memory_usage
- test_memory_threshold_warning
- test_memory_over_threshold

# GPU monitoring
- test_get_gpu_usage
- test_gpu_memory_available
- test_gpu_not_available
- test_gpu_threshold_warning

# Health reporting
- test_system_health_report
- test_health_status_ok
- test_health_status_warning
```

---

### Week 4: Frontend Component Tests

#### Task 4.1: Jest Configuration
**File to create:** `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/apps/constitutional-gpt/jest.config.js`

```javascript
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'jsdom',
  roots: ['<rootDir>'],
  testMatch: ['**/__tests__/**/*.test.ts?(x)', '**/?(*.)+(spec|test).ts?(x)'],
  setupFilesAfterEnv: ['<rootDir>/jest.setup.js'],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/$1',
  },
  collectCoverageFrom: [
    'app/**/*.{ts,tsx}',
    'lib/**/*.{ts,tsx}',
    'components/**/*.{ts,tsx}',
    '!**/*.d.ts',
    '!**/node_modules/**',
  ],
  coverageThreshold: {
    global: {
      statements: 70,
      branches: 70,
      functions: 70,
      lines: 70,
    },
  },
};
```

---

#### Task 4.2: Core Component Tests (50+ tests)
**File to create:** `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/apps/constitutional-gpt/__tests__/components.test.tsx`

**Tests to write:**
```typescript
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Query Input Component
- test_render_query_input
- test_submit_empty_query
- test_submit_valid_query
- test_clear_input
- test_character_limit_enforcement
- test_submit_button_disabled_when_empty

// Response Display Component
- test_render_response
- test_stream_response_rendering
- test_error_response_display
- test_cite_sources_link
- test_copy_response_button

// Conversation History
- test_render_message_list
- test_add_new_message
- test_clear_history
- test_history_persistence
- test_scroll_to_latest_message

// Mode Selection
- test_chat_mode_button
- test_assist_mode_button
- test_evidence_mode_button
- test_mode_switch_preserves_history
```

---

## Phase 3: Integration & Advanced Testing (Weeks 5-8)

### Week 5: Search Logic & Hybrid Search

#### Task 5.1: Hybrid Search Tests (25+ tests)
**File to create:** `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/apps/constitutional-gpt/__tests__/hybrid-search.test.ts`

**Tests to write:**
```typescript
import { hybridSearch } from '@/lib/agentic-rag/hybrid-search';

// Semantic search tests
- test_semantic_search_valid_query
- test_semantic_search_empty_results
- test_semantic_search_with_filters
- test_semantic_search_timeout

// BM25 search tests
- test_bm25_search_exact_match
- test_bm25_search_partial_match
- test_bm25_search_phrase_match
- test_bm25_search_case_insensitive

// Hybrid ranking tests
- test_hybrid_ranking_semantic_first
- test_hybrid_ranking_bm25_first
- test_hybrid_ranking_combined_score
- test_hybrid_ranking_deduplication

// Results processing
- test_results_formatting
- test_results_truncation
- test_results_with_metadata
- test_results_with_citations
```

---

### Week 6: Database Integration

#### Task 6.1: ChromaDB Integration Tests (20+ tests)
**File to create:** `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/tests/test_chromadb_integration.py`

**Tests to write:**
```python
import chromadb
from chromadb.config import Settings

# Connection & Collection
- test_chromadb_connection
- test_collection_creation
- test_collection_retrieval
- test_collection_deletion

# Document Ingestion
- test_add_documents
- test_add_bulk_documents
- test_add_documents_with_metadata
- test_add_documents_validation
- test_add_duplicate_detection

# Embedding Tests
- test_document_embedding
- test_embedding_consistency
- test_embedding_dimension
- test_embedding_normalization

# Search Tests
- test_vector_similarity_search
- test_search_with_filters
- test_search_limit
- test_search_offset
```

---

### Week 7-8: Performance & Security

#### Task 7.1: Performance Benchmarks
**File to create:** `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/tests/test_performance.py`

```python
# Search latency benchmarks
- test_search_latency_p50
- test_search_latency_p95
- test_search_latency_p99
- test_batch_search_throughput

# Generation performance
- test_generation_latency
- test_generation_throughput
- test_streaming_latency

# Memory profiling
- test_memory_usage_search
- test_memory_usage_generation
- test_memory_leak_detection
```

---

#### Task 7.2: Security Tests
**File to create:** `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/tests/test_security.py`

```python
# Input validation
- test_sql_injection_prevention
- test_prompt_injection_prevention
- test_xss_prevention
- test_path_traversal_prevention
- test_command_injection_prevention

# Rate limiting
- test_api_rate_limit
- test_rate_limit_headers
- test_rate_limit_recovery

# Authentication
- test_api_key_validation
- test_unauthorized_access
- test_token_expiry

# Data privacy
- test_sensitive_data_filtering
- test_pii_removal
- test_swedish_personnummer_removal
```

---

## Test Execution & CI/CD Integration

### GitHub Actions Workflow
**File to create:** `.github/workflows/test.yml`

```yaml
name: Test Suite

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  python-tests:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.11', '3.12']
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt pytest pytest-cov pytest-asyncio
      - name: Run tests
        run: |
          cd juridik-ai
          pytest tests/ -v --cov=.. --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3

  frontend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '18'
      - name: Install dependencies
        run: |
          cd apps/constitutional-gpt
          npm ci
      - name: Run tests
        run: npm run test:coverage
      - name: Upload coverage
        uses: codecov/codecov-action@v3

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
      - run: pip install ruff
      - run: ruff check .
      - run: ruff format --check .
```

---

## Test Execution Checklist

### Before starting each phase:
- [ ] Review the task description
- [ ] Create test file with proper structure
- [ ] Write tests using Arrange-Act-Assert pattern
- [ ] Run tests locally to ensure they work
- [ ] Run with coverage to verify new tests are executed
- [ ] Commit with clear message: "test: add {module} unit tests"

### Weekly review:
- [ ] Check total test count
- [ ] Review coverage percentage
- [ ] Identify any failing tests
- [ ] Update documentation if needed
- [ ] Plan next week's tests

### Monthly review:
- [ ] Analyze test quality (assertion density, edge cases)
- [ ] Identify untested critical paths
- [ ] Update roadmap if needed
- [ ] Plan next quarter's improvements

---

## Quick Command Reference

```bash
# Run specific phase tests
cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI

# Phase 1
pytest juridik-ai/tests/test_cli.py -v
pytest tests/test_api_endpoints.py -v
pytest eval/tests/test_ragas_wrapper.py -v

# Phase 2
pytest juridik-ai/tests/test_cli_app.py -v
pytest juridik-ai/tests/test_ollama_client.py -v
pytest juridik-ai/tests/test_system_monitor.py -v

# Phase 3
cd apps/constitutional-gpt
npm run test:coverage

# All tests
pytest tests/ -v --cov
npm run test

# Generate coverage report
pytest tests/ --cov --cov-report=html
open htmlcov/index.html
```

---

## Success Metrics

### End of Phase 1 (Week 2)
- [x] 70+ new unit tests written
- [x] pytest.ini and conftest.py configured
- [x] CLI and API endpoints covered
- [x] Coverage report shows >70% for critical modules

### End of Phase 2 (Week 4)
- [x] 130+ new unit tests written
- [x] Service layer fully covered
- [x] Frontend component tests started
- [x] CI/CD pipeline configured

### End of Phase 3 (Week 8)
- [x] 400+ total tests
- [x] >75% coverage for all critical modules
- [x] All acceptance tests passing
- [x] Performance baselines established
- [x] Security tests passing

---

## Appendix: Test Template

### Python Unit Test Template
```python
import pytest
from unittest.mock import Mock, patch
from your_module import function_to_test

class TestFunctionName:
    """Test suite for function_name"""

    def test_happy_path(self):
        """Test expected behavior with valid input"""
        # ARRANGE
        input_data = {"key": "value"}

        # ACT
        result = function_to_test(input_data)

        # ASSERT
        assert result["status"] == "success"
        assert result["data"] is not None

    def test_error_handling(self):
        """Test error handling with invalid input"""
        # ARRANGE
        invalid_input = None

        # ACT & ASSERT
        with pytest.raises(ValueError):
            function_to_test(invalid_input)

    @pytest.mark.parametrize("input,expected", [
        ("value1", "result1"),
        ("value2", "result2"),
    ])
    def test_parametrized(self, input, expected):
        """Test with multiple inputs"""
        result = function_to_test(input)
        assert result == expected
```

### TypeScript Component Test Template
```typescript
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ComponentName } from '@/components/ComponentName';

describe('ComponentName', () => {
  it('renders correctly', () => {
    render(<ComponentName />);
    expect(screen.getByText(/expected text/i)).toBeInTheDocument();
  });

  it('handles user interaction', async () => {
    const user = userEvent.setup();
    render(<ComponentName />);

    const button = screen.getByRole('button');
    await user.click(button);

    expect(screen.getByText(/result/i)).toBeInTheDocument();
  });
});
```

---
