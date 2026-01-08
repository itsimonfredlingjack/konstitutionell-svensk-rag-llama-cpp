#!/bin/bash
# RAG Server using Ollama (fallback if custom build fails)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║       CONSTITUTIONAL AI RAG - OLLAMA FALLBACK               ║"
echo "║          12GB VRAM - OpenAI Compatible API                 ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Model name
MODEL="ministral-3:14b"
PORT=8080

echo -e "${YELLOW}Model: $MODEL${NC}"
echo -e "${YELLOW}Port: $PORT${NC}"

# Stop existing servers
echo -e "${YELLOW}Stopping existing servers...${NC}"
pkill -f "ollama.*serve" 2>/dev/null || true
pkill -f "llama-server" 2>/dev/null || true
sleep 2

# Check if port is free
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${RED}❌ Port $PORT is still in use${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}🚀 Starting Ollama server...${NC}"

OLLAMA_HOST=0.0.0.0 \
OLLAMA_PORT=$PORT \
OLLAMA_ORIGINS="*" \
OLLAMA_KEEP_ALIVE=-1 \
OLLAMA_NUM_GPU=99 \
OLLAMA_LOAD_TIMEOUT=5m \
OLLAMA_NUM_THREAD=4 \
OLLAMA_FLASH_ATTENTION=1 \
ollama serve > /tmp/ollama_server.log 2>&1 &

SERVER_PID=$!

# Wait for server to start
echo -e "${YELLOW}Waiting for server to start...${NC}"
TIMEOUT=30
ELAPSED=0
while ! curl -s http://localhost:$PORT/v1/models >/dev/null 2>&1; do
    if [ $ELAPSED -ge $TIMEOUT ]; then
        echo -e "${RED}❌ Server failed to start within ${TIMEOUT}s${NC}"
        kill $SERVER_PID 2>/dev/null || true
        exit 1
    fi
    sleep 1
    ELAPSED=$((ELAPSED + 1))
    echo -n "."
done

echo ""
echo -e "${GREEN}✅ Server is running!${NC}"
echo -e "${CYAN}   PID: $SERVER_PID${NC}"
echo -e "${CYAN}   API: http://localhost:$PORT/v1${NC}"
echo ""
echo -e "${GREEN}══════════════════════════════════════════════════════════════${NC}"

wait $SERVER_PID
