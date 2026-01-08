#!/bin/bash

# --- KONFIGURATION ---
LLAMA_BIN="./llama.cpp/build/bin/llama-server"
MODEL_PATH="models/Mistral-Nemo-Instruct-2407-Q5_K_M.gguf"
DRAFT_PATH="models/Qwen2.5-0.5B-Instruct-Q8_0.gguf"
BACKEND_PORT=8900
LLM_PORT=8080
FRONTEND_PORT=3001
LOG_DIR="logs"
FRONTEND_DIR="apps/constitutional-retardedantigravity"

# Skapa loggmapp om den inte finns
mkdir -p $LOG_DIR

echo "🚀 INITIALIZING RAG SYSTEM..."
echo "--------------------------------"

# Validera att alla nödvändiga filer finns
if [ ! -f "$LLAMA_BIN" ]; then
  echo "❌ ERROR: llama-server not found at $LLAMA_BIN"
  exit 1
fi

if [ ! -f "$MODEL_PATH" ]; then
  echo "❌ ERROR: Main model not found at $MODEL_PATH"
  exit 1
fi

if [ ! -f "$DRAFT_PATH" ]; then
  echo "❌ ERROR: Draft model not found at $DRAFT_PATH"
  exit 1
fi

if [ ! -d "$FRONTEND_DIR" ]; then
  echo "❌ ERROR: Frontend directory not found at $FRONTEND_DIR"
  exit 1
fi

echo "✅ All required files found"

# 1. STÄDNING: Döda gamla processer
echo "🧹 Cleaning up old processes..."
fuser -k $LLM_PORT/tcp > /dev/null 2>&1
fuser -k $BACKEND_PORT/tcp > /dev/null 2>&1
fuser -k $FRONTEND_PORT/tcp > /dev/null 2>&1
sleep 2

# 2. STARTA LLAMA SERVER (RAG ENGINE)
echo "🧠 Starting Mistral-Nemo Engine (Port $LLM_PORT)..."
# Vi använder inställningarna vi testade fram: 16k context, 60 GPU-lager, Q8 cache
$LLAMA_BIN \
  -m "$MODEL_PATH" \
  --model-draft "$DRAFT_PATH" \
  -c 16384 \
  -ngl 60 \
  -ctk q8_0 -ctv q8_0 \
  --port $LLM_PORT \
  --host 0.0.0.0 \
  --ctx-size 16384 \
  --parallel 2 \
  -fa on \
  > "$LOG_DIR/llama_server.log" 2>&1 &

LLM_PID=$!
echo "   PID: $LLM_PID - Logs: $LOG_DIR/llama_server.log"

# 3. VÄNTA PÅ ATT MOTORN ÄR REDO
echo "⏳ Waiting for LLM to load (this takes ~30-60s)..."
MAX_WAIT=120  # Max 2 minuter
WAIT_COUNT=0
while ! grep -q "server is listening" "$LOG_DIR/llama_server.log" 2>/dev/null; do
  if ! kill -0 $LLM_PID 2>/dev/null; then
    echo -e "\n❌ LLM Server crashed! Check logs: $LOG_DIR/llama_server.log"
    tail -20 "$LOG_DIR/llama_server.log" 2>/dev/null || echo "Log file not found"
    exit 1
  fi
  WAIT_COUNT=$((WAIT_COUNT + 2))
  if [ $WAIT_COUNT -ge $MAX_WAIT ]; then
    echo -e "\n❌ Timeout waiting for LLM server. Check logs: $LOG_DIR/llama_server.log"
    tail -20 "$LOG_DIR/llama_server.log" 2>/dev/null || echo "Log file not found"
    exit 1
  fi
  echo -ne "."
  sleep 2
done
echo -e "\n✅ LLM Engine is READY!"

# 4. STARTA BACKEND (ORCHESTRATOR)
echo "🤖 Starting Python Backend (Port $BACKEND_PORT)..."
export LLM_API_BASE="http://localhost:$LLM_PORT/v1"
export LLM_MODEL="Mistral-Nemo-Instruct-2407-Q5_K_M.gguf"

cd backend
python3 -m uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT > "../$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
cd ..

echo "   PID: $BACKEND_PID - Logs: $LOG_DIR/backend.log"

# 5. VÄNTA PÅ ATT BACKEND ÄR REDO
echo "⏳ Waiting for Backend to start..."
sleep 3

# 6. STARTA FRONTEND
echo "🎨 Starting Frontend (Port $FRONTEND_PORT)..."
cd "$FRONTEND_DIR"
npm run dev > "../../$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
cd ../..

echo "   PID: $FRONTEND_PID - Logs: $LOG_DIR/frontend.log"
echo "--------------------------------"
echo "🎉 SYSTEM FULLY OPERATIONAL"
echo "   Backend API: http://localhost:$BACKEND_PORT"
echo "   Frontend UI: http://localhost:$FRONTEND_PORT"
echo "   Network UI: http://192.168.x.x:$FRONTEND_PORT"
echo "   To stop system: ./stop_system.sh"
