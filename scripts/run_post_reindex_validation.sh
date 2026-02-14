#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_PY="backend/venv/bin/python"
CHECKPOINT_FILE="migration_checkpoints/reindex_checkpoint.json"
LOG_DIR="logs"
MASTER_LOG="$LOG_DIR/post_reindex_validation.log"
SMOKE_LOG="$LOG_DIR/smoke_test_post_reindex.log"
QUALITY_LOG="$LOG_DIR/retrieval_quality_benchmark.log"
QUALITY_JSON="$LOG_DIR/retrieval_quality_benchmark.json"
BENCH_LOG="$LOG_DIR/benchmark_post_migration.log"
RUNTIME_LOG="$LOG_DIR/runtime_post_reindex_check.log"
CUTOVER_ENFORCE_NO_FALLBACK="${CUTOVER_ENFORCE_NO_FALLBACK:-1}"
CHECKPOINT_STALE_SECONDS="${CHECKPOINT_STALE_SECONDS:-600}"
RUN_STARTED_AT="$(date '+%Y-%m-%d %H:%M:%S')"

# Chroma repair gate controls
CHROMA_PATH="${CHROMA_PATH:-chromadb_data}"
CHROMA_VACUUM_TIMEOUT_SECONDS="${CHROMA_VACUUM_TIMEOUT_SECONDS:-14400}"
CHROMA_SKIP_VACUUM="${CHROMA_SKIP_VACUUM:-0}"
CHROMA_INTEGRITY_RETRIES="${CHROMA_INTEGRITY_RETRIES:-20}"
CHROMA_INTEGRITY_SLEEP_MS="${CHROMA_INTEGRITY_SLEEP_MS:-200}"
CHROMA_INTEGRITY_TOP_K="${CHROMA_INTEGRITY_TOP_K:-5}"

mkdir -p "$LOG_DIR"

log() {
  local ts
  ts="$(date '+%Y-%m-%d %H:%M:%S')"
  echo "[$ts] $*" | tee -a "$MASTER_LOG"
}

checkpoint_status() {
  "$VENV_PY" - <<'PY'
import json
import time
from pathlib import Path

path = Path("migration_checkpoints/reindex_checkpoint.json")
if not path.exists():
    print("missing,0,0,0,false,-1")
    raise SystemExit

payload = json.loads(path.read_text(encoding="utf-8"))
processed = int(payload.get("processed_total", 0))
written = int(payload.get("written_total", 0))
errors = int(payload.get("error_count", 0))
completed = bool(payload.get("completed", False))

updated_at = payload.get("updated_at", "")
freshness_age = -1
if updated_at:
    try:
        updated_epoch = int(time.mktime(time.strptime(updated_at, "%Y-%m-%d %H:%M:%S")))
        freshness_age = int(time.time()) - updated_epoch
    except Exception:
        freshness_age = -1
print(f"ok,{processed},{written},{errors},{str(completed).lower()},{freshness_age}")
PY
}

is_reindex_process_alive() {
  pgrep -f "reindex_corpus.py" >/dev/null
}

stop_services_for_repair() {
  log "Stopping services for Chroma repair gate (backend + llm)"
  systemctl --user stop constitutional-ai-backend.service >/dev/null 2>&1 || true
  systemctl --user stop constitutional-ai-llm.service >/dev/null 2>&1 || true
}

run_chroma_vacuum_if_enabled() {
  if [[ "$CHROMA_SKIP_VACUUM" == "1" ]]; then
    log "Skipping Chroma vacuum (CHROMA_SKIP_VACUUM=1)."
    return 0
  fi
  log "Running Chroma vacuum (path=$CHROMA_PATH, timeout=$CHROMA_VACUUM_TIMEOUT_SECONDS)"
  backend/venv/bin/chroma vacuum --path "$CHROMA_PATH" --force --timeout "$CHROMA_VACUUM_TIMEOUT_SECONDS"
}

run_chroma_integrity_gate() {
  log "Running Chroma integrity gate"
  "$VENV_PY" scripts/chroma_integrity_check.py \
    --path "$CHROMA_PATH" \
    --device cpu \
    --retries "$CHROMA_INTEGRITY_RETRIES" \
    --sleep-ms "$CHROMA_INTEGRITY_SLEEP_MS" \
    --top-k "$CHROMA_INTEGRITY_TOP_K" \
    --fail-fast \
    --output-json "$LOG_DIR/chroma_integrity_report.json"
}

health_is_ok() {
  local body="$1"
  python3 - "$body" <<'PY'
import json
import sys

raw = sys.argv[1]
if not raw:
    raise SystemExit(1)
try:
    data = json.loads(raw)
except Exception:
    raise SystemExit(1)
status = str(data.get("status", "")).lower()
if status in {"ok", "healthy"}:
    raise SystemExit(0)
services = data.get("services")
if isinstance(services, dict):
    orch = str(services.get("orchestrator", "")).lower()
    if orch in {"initialized", "uninitialized"}:
        raise SystemExit(0)
raise SystemExit(1)
PY
}

wait_for_reindex_completion() {
  log "Waiting for re-index completion via $CHECKPOINT_FILE"
  while true; do
    local status
    status="$(checkpoint_status)"
    IFS=',' read -r state processed written errors completed freshness_age <<<"$status"

    if [[ "$state" == "missing" ]]; then
      log "Checkpoint not found yet; sleeping 60s."
      sleep 60
      continue
    fi

    log "Re-index progress: processed=$processed written=$written errors=$errors completed=$completed freshness_age_s=$freshness_age"

    if [[ "$completed" == "true" ]]; then
      log "Re-index completed."
      break
    fi

    if is_reindex_process_alive; then
      sleep 60
      continue
    fi

    if [[ "$freshness_age" =~ ^[0-9]+$ ]] && (( freshness_age <= CHECKPOINT_STALE_SECONDS )); then
      log "Re-index process not visible, but checkpoint is fresh ($freshness_age s). Continuing."
      sleep 60
      continue
    fi

    log "ERROR: re-index appears stalled (no process + stale checkpoint)."
    exit 1
  done
}

wait_for_backend_health() {
  log "Starting constitutional-ai-backend.service"
  systemctl --user start constitutional-ai-backend.service

  local attempts=0
  local max_attempts=60
  while (( attempts < max_attempts )); do
    local body
    body="$(curl -sS "http://localhost:8900/api/constitutional/health" || true)"
    if health_is_ok "$body"; then
      log "Backend health check passed."
      return 0
    fi
    attempts=$((attempts + 1))
    sleep 2
  done
  log "ERROR: Backend health check did not pass within timeout."
  return 1
}

wait_for_llm_health() {
  log "Starting constitutional-ai-llm.service"
  systemctl --user start constitutional-ai-llm.service

  local attempts=0
  local max_attempts=120
  while (( attempts < max_attempts )); do
    local body
    body="$(curl -sS "http://localhost:8080/health" || true)"
    if health_is_ok "$body"; then
      log "LLM health check passed."
      return 0
    fi
    attempts=$((attempts + 1))
    sleep 5
  done

  log "ERROR: LLM health check did not pass within timeout."
  return 1
}

run_post_reindex_checks() {
  log "Running smoke test pipeline (with gates)"
  "$VENV_PY" scripts/smoke_test_pipeline.py --enforce-gates 2>&1 | tee "$SMOKE_LOG"

  log "Running retrieval quality benchmark (with gates)"
  "$VENV_PY" scripts/compare_retrieval_quality.py --enforce-gates --output-json "$QUALITY_JSON" 2>&1 | tee "$QUALITY_LOG"

  log "Running Ministral benchmark"
  "$VENV_PY" scripts/benchmark_ministral.py 2>&1 | tee "$BENCH_LOG"
}

runtime_truth_check() {
  log "Running runtime truth-check (collections and backend logs)"
  {
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') Runtime truth-check ==="
    echo "--- Jina collection counts ---"
    "$VENV_PY" - <<'PY'
import chromadb
from pathlib import Path
client = chromadb.PersistentClient(path=str(Path("chromadb_data").resolve()))
for name in sorted([c.name for c in client.list_collections() if c.name.endswith("_jina_v3_1024")]):
    print(f"{name}\t{client.get_collection(name).count()}")
PY
    echo "--- Backend health ---"
    curl -fsS "http://localhost:8900/api/constitutional/health" || true
    echo
    echo "--- Last resolved_collection logs ---"
    journalctl --user -u constitutional-ai-backend.service -n 400 --no-pager | rg "resolved_collection|embedding_model_name|reranker_model_name|bm25_index_size|query_expansions|expansion_parsing_method" || true
  } | tee "$RUNTIME_LOG"
}

check_runtime_fallbacks() {
  if [[ "$CUTOVER_ENFORCE_NO_FALLBACK" != "1" ]]; then
    log "Fallback enforcement disabled (CUTOVER_ENFORCE_NO_FALLBACK=$CUTOVER_ENFORCE_NO_FALLBACK)."
    return 0
  fi

  RUN_STARTED_AT="$RUN_STARTED_AT" python3 - <<'PY'
import json
import os
import subprocess
import sys

run_started_at = os.environ.get("RUN_STARTED_AT", "")
cmd = [
    "journalctl",
    "--user",
    "-u",
    "constitutional-ai-backend.service",
    "--no-pager",
]
if run_started_at:
    cmd.extend(["--since", run_started_at])
cmd.extend(["-n", "1200"])
proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
violations = []
for line in proc.stdout.splitlines():
    if "retrieval_request_observability" not in line:
        continue
    json_start = line.find("{")
    if json_start < 0:
        continue
    chunk = line[json_start:]
    try:
        payload = json.loads(chunk)
    except Exception:
        continue
    for pair in payload.get("resolved_collection", []):
        if pair.get("fallback_used"):
            violations.append(
                {
                    "query": payload.get("query", ""),
                    "requested": pair.get("requested"),
                    "resolved": pair.get("resolved"),
                }
            )

if violations:
    print("CUTOVER fallback violations detected:")
    for item in violations[:20]:
        print(
            f"- query='{item['query'][:80]}' requested={item['requested']} resolved={item['resolved']}"
        )
    sys.exit(2)

sys.exit(0)
PY
}

main() {
  log "Post-reindex validation runner started."
  wait_for_reindex_completion
  stop_services_for_repair
  run_chroma_vacuum_if_enabled
  run_chroma_integrity_gate
  wait_for_backend_health
  wait_for_llm_health
  run_post_reindex_checks
  runtime_truth_check
  if check_runtime_fallbacks; then
    log "Cutover fallback check passed (no fallback observed)."
  else
    rc=$?
    log "ERROR: Cutover fallback check failed with rc=$rc."
    exit "$rc"
  fi
  log "Post-reindex validation completed successfully."
}

main "$@"
