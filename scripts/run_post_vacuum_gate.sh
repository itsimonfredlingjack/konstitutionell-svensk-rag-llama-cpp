#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

LOG_DIR="logs"
RUN_ID="$(date '+%Y%m%d_%H%M%S')"
MASTER_LOG="${MASTER_LOG:-$LOG_DIR/post_vacuum_gate_${RUN_ID}.log}"

CHROMA_PATH="${CHROMA_PATH:-chromadb_data}"
VENV_PY="${VENV_PY:-backend/venv/bin/python}"

GATE_COLLECTIONS="${GATE_COLLECTIONS:-swedish_gov_docs_jina_v3_1024,diva_research_jina_v3_1024}"
GATE_LOOPS="${GATE_LOOPS:-10}"
GATE_N_RESULTS="${GATE_N_RESULTS:-5}"
GATE_SLEEP_MS="${GATE_SLEEP_MS:-200}"

GATE_LOG="${GATE_LOG:-$LOG_DIR/chroma_integrity_gate_${RUN_ID}.log}"
GATE_JSON="${GATE_JSON:-$LOG_DIR/chroma_integrity_report_${RUN_ID}.json}"

SMOKE_LOG="${SMOKE_LOG:-$LOG_DIR/smoke_test_post_vacuum_${RUN_ID}.log}"
SMOKE_JSON="${SMOKE_JSON:-$LOG_DIR/smoke_test_post_vacuum_${RUN_ID}.json}"
QUALITY_LOG="${QUALITY_LOG:-$LOG_DIR/retrieval_quality_post_vacuum_${RUN_ID}.log}"
QUALITY_JSON="${QUALITY_JSON:-$LOG_DIR/retrieval_quality_post_vacuum_${RUN_ID}.json}"

TRUTH_LOG="${TRUTH_LOG:-$LOG_DIR/runtime_truth_post_vacuum_${RUN_ID}.log}"
TRUTH_JSON="${TRUTH_JSON:-$LOG_DIR/runtime_truth_post_vacuum_${RUN_ID}.json}"

RUN_STARTED_AT="$(date '+%Y-%m-%d %H:%M:%S')"

mkdir -p "$LOG_DIR"

log() {
  local ts
  ts="$(date '+%Y-%m-%d %H:%M:%S')"
  echo "[$ts] $*" | tee -a "$MASTER_LOG"
}

have_rg() {
  command -v rg >/dev/null 2>&1
}

scan_text_for_patterns() {
  # Usage: scan_text_for_patterns "<text>" "<pattern1|pattern2|...>"
  local text="$1"
  local patterns="$2"

  if have_rg; then
    echo "$text" | rg -i "$patterns" >/dev/null 2>&1
  else
    echo "$text" | grep -Eiq "$patterns"
  fi
}

extract_last_matching_line() {
  # Usage: extract_last_matching_line "<text>" "<pattern>"
  local text="$1"
  local pattern="$2"

  if have_rg; then
    echo "$text" | rg "$pattern" | tail -n 1 || true
  else
    echo "$text" | grep -E "$pattern" | tail -n 1 || true
  fi
}

die() {
  log "ERROR: $*"
  exit 1
}

wait_for_http_ok_json_status() {
  local url="$1"
  local expect="$2"
  local max_attempts="$3"
  local sleep_s="$4"

  local i=0
  while (( i < max_attempts )); do
    local body
    body="$(curl -sS "$url" || true)"
    if python3 - "$body" "$expect" <<'PY'
import json
import sys

raw = sys.argv[1]
expected = sys.argv[2].lower().strip()
try:
    data = json.loads(raw)
except Exception:
    raise SystemExit(1)
status = str(data.get("status", "")).lower().strip()
raise SystemExit(0 if status == expected else 1)
PY
    then
      return 0
    fi
    i=$((i+1))
    sleep "$sleep_s"
  done
  return 1
}

assert_no_vacuum_running() {
  # Use [c] to avoid matching our own pgrep in some environments.
  if pgrep -af "[c]hroma vacuum" >/dev/null 2>&1; then
    log "Detected running vacuum process:"
    pgrep -af "[c]hroma vacuum" | tee -a "$MASTER_LOG" || true
    die "Vacuum still running. Wait for it to finish before starting integrity gate."
  fi
}

run_integrity_gate() {
  log "Running Chroma integrity gate (fail-closed)"
  log "  path=$CHROMA_PATH"
  log "  collections=$GATE_COLLECTIONS"
  log "  loops=$GATE_LOOPS n_results=$GATE_N_RESULTS sleep_ms=$GATE_SLEEP_MS"

  set +e
  "$VENV_PY" scripts/chroma_integrity_check.py \
    --path "$CHROMA_PATH" \
    --collections "$GATE_COLLECTIONS" \
    --loops "$GATE_LOOPS" \
    --n-results "$GATE_N_RESULTS" \
    --sleep-ms "$GATE_SLEEP_MS" \
    --log "$GATE_LOG" \
    --output-json "$GATE_JSON" \
    2>&1 | tee -a "$MASTER_LOG"
  local rc="${PIPESTATUS[0]}"
  set -e

  if [[ "$rc" != "0" ]]; then
    log "GATE=FAIL (exit_code=$rc)"
    log "NEXT ACTION: Isolated rebuild of failing collections only."
    log "Collections attempted: $GATE_COLLECTIONS"
    log "See: $GATE_LOG and $GATE_JSON"
    exit "$rc"
  fi

  log "GATE=PASS"
}

start_services_and_wait_ready() {
  log "Starting constitutional-ai-llm.service"
  systemctl --user start constitutional-ai-llm.service
  if ! wait_for_http_ok_json_status "http://localhost:8080/health" "ok" 120 5; then
    die "LLM health check did not become OK in time."
  fi
  log "LLM health: OK"

  log "Starting constitutional-ai-backend.service"
  systemctl --user start constitutional-ai-backend.service
  if ! wait_for_http_ok_json_status "http://localhost:8900/api/constitutional/health" "healthy" 90 2; then
    die "Backend health check did not become healthy in time."
  fi
  log "Backend health: OK"
}

run_enforced_benchmarks() {
  log "Running smoke test pipeline (--enforce-gates)"
  "$VENV_PY" scripts/smoke_test_pipeline.py \
    --enforce-gates \
    --output-json "$SMOKE_JSON" \
    2>&1 | tee "$SMOKE_LOG" | tee -a "$MASTER_LOG"

  log "Running retrieval quality benchmark (--enforce-gates)"
  "$VENV_PY" scripts/compare_retrieval_quality.py \
    --enforce-gates \
    --output-json "$QUALITY_JSON" \
    2>&1 | tee "$QUALITY_LOG" | tee -a "$MASTER_LOG"
}

runtime_truth_snapshot() {
  log "Capturing runtime truth snapshot (resolved_collection + fallback_used + HNSW scan)"

  # Trigger one canonical query so observability has a fresh entry.
  curl -sS -X POST "http://localhost:8900/api/constitutional/agent/query" \
    -H "Content-Type: application/json" \
    -H "X-Retrieval-Strategy: adaptive" \
    -d '{"question":"Vad säger arbetsmiljölagen om arbetsgivarens ansvar?","mode":"evidence","use_agent":false}' \
    >/dev/null || true

  local journal_out
  journal_out="$(journalctl --user -u constitutional-ai-backend.service --since "$RUN_STARTED_AT" --no-pager || true)"

  # Fail if any known HNSW/compactor error occurred during this run window.
  local hnsw_patterns="Error sending backfill request to compactor|Error loading hnsw index|hnsw segment reader"
  if scan_text_for_patterns "$journal_out" "$hnsw_patterns"; then
    if have_rg; then
      echo "$journal_out" | rg -i "$hnsw_patterns" | tee -a "$MASTER_LOG" >"$TRUTH_LOG"
    else
      echo "$journal_out" | grep -Ei "$hnsw_patterns" | tee -a "$MASTER_LOG" >"$TRUTH_LOG"
    fi
    die "Detected HNSW/compactor errors during post-vacuum run. Aborting."
  fi

  local last_line
  last_line="$(extract_last_matching_line "$journal_out" "retrieval_request_observability")"
  if [[ -z "$last_line" ]]; then
    die "No retrieval_request_observability log line found in journal window."
  fi

  python3 - "$last_line" "$TRUTH_JSON" <<'PY'
import json
import sys

line = sys.argv[1]
out_path = sys.argv[2]

json_start = line.find("{")
if json_start < 0:
    raise SystemExit("No JSON payload found in observability log line")

payload = json.loads(line[json_start:])

pairs = payload.get("resolved_collection", [])
violations = []
for pair in pairs:
    requested = str(pair.get("requested") or "")
    resolved = str(pair.get("resolved") or "")
    if not resolved.endswith("_jina_v3_1024"):
        violations.append({"requested": requested, "resolved": resolved, "reason": "not_jina_suffix"})
    if pair.get("fallback_used") is True:
        violations.append({"requested": requested, "resolved": resolved, "reason": "fallback_used_true"})

bm25 = payload.get("bm25") or {}
bm25_doc_count = int(bm25.get("doc_count") or 0)
if bm25_doc_count <= 0:
    violations.append({"component": "bm25", "doc_count": bm25_doc_count, "reason": "doc_count_not_positive"})

snapshot = {
    "observability": payload,
    "violations": violations,
    "ok": len(violations) == 0,
}

with open(out_path, "w", encoding="utf-8") as f:
    json.dump(snapshot, f, ensure_ascii=False, indent=2)

if violations:
    raise SystemExit("Runtime truth-check failed: " + json.dumps(violations, ensure_ascii=False))
PY

  echo "$last_line" >"$TRUTH_LOG"
  log "Runtime truth snapshot: PASS ($TRUTH_JSON)"
}

main() {
  log "Post-vacuum gate runner starting (run_id=$RUN_ID since='$RUN_STARTED_AT')"
  log "Master log: $MASTER_LOG"

  assert_no_vacuum_running
  run_integrity_gate

  start_services_and_wait_ready
  run_enforced_benchmarks
  runtime_truth_snapshot

  log "Post-vacuum gate runner complete: PASS"
}

main "$@"
