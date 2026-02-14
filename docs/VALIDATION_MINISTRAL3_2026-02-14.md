# Ministral 3 14B RAG Validation Report
**Date**: 2026-02-14
**Model**: Ministral-3-14B-Instruct-2512-Q4_K_M.gguf
**Commit**: 6144da0

## Test Suite
- Total: 0 passed, 0 failed, 0 skipped, 1 error (collection/import)
- Command: `pytest tests/ -v -x -m "not integration and not ollama and not slow"`
- Result summary (tail): `ModuleNotFoundError: No module named 'langgraph'` while importing `app/services/graph_service.py` via `app/services/agentic_service.py`.

## ChromaDB Integrity Gate
- Result: FAIL
- Command: `bash scripts/run_post_vacuum_gate.sh`
- Failure: `backend/venv/bin/python: No such file or directory` (exit code 127). The gate runner could not execute the integrity check in this worktree.

## Live RAG Query 1: Regeringsformen om yttrandefrihet
- Evidence level: NONE
- Sources returned: 0
- Answer quality: Failed. Returned generic error message instead of RF/2 kap.
- Response time: ~0.02s
- Backend journal: `DefaultCPUAllocator: can't allocate memory` while attempting retrieval.

## Live RAG Query 2: Jämförelse svensk/norsk grundlag (CRAG edge case)
- Behavior: error
- Assessment: Incorrect behavior for CRAG edge-case. Expected either refusal or grounded comparison; instead got generic error.
- Response time: ~0.01s

## Remote Configuration
- Canonical: origin → github.com/itsimonfredlingjack/KONSTITUTIONELL-SVENSK-AI
- Legacy: legacy-rag-project → github.com/itsimonfredlingjack/rag-project
- Reference: llama-cpp → github.com/itsimonfredlingjack/konstitutionell-svensk-rag-llama-cpp
