#!/usr/bin/env bash
#
# Simons AI Backend - Start Script
# Startar backend-servern för THINK/CHILL dual-modell system
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Färger
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║            SIMONS AI - DUAL EXPERT SYSTEM                    ║"
echo "║         GPT-OSS 20B (Arkitekt) + Devstral 24B (Kodare)       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Kontrollera virtual environment
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Skapar virtual environment...${NC}"
    python3 -m venv .venv
fi

source .venv/bin/activate

# Kontrollera dependencies
echo -e "${CYAN}Kontrollerar dependencies...${NC}"
pip install -q -r requirements.txt

# Kontrollera Ollama
echo -e "${CYAN}Kontrollerar Ollama...${NC}"
if ! command -v ollama &> /dev/null; then
    echo -e "${RED}Ollama är inte installerat!${NC}"
    echo "Installera med: curl -fsSL https://ollama.ai/install.sh | sh"
    exit 1
fi

if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "${YELLOW}Ollama körs inte. Startar...${NC}"
    ollama serve &
    sleep 3
fi

# Kontrollera modeller
echo -e "${CYAN}Kontrollerar modeller...${NC}"
MODELS=$(ollama list 2>/dev/null || echo "")

if ! echo "$MODELS" | grep -q "gpt-oss"; then
    echo -e "${YELLOW}GPT-OSS saknas. Kör: ollama create gpt-oss -f ~/Modelfile-GPTOSS${NC}"
fi

if ! echo "$MODELS" | grep -q "devstral"; then
    echo -e "${YELLOW}Devstral saknas. Kör: ollama create devstral -f ~/Modelfile-Devstral${NC}"
fi

# Kontrollera GPU
echo -e "${CYAN}Kontrollerar GPU...${NC}"
if command -v nvidia-smi &> /dev/null; then
    GPU_INFO=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>/dev/null || echo "Unknown")
    echo -e "${GREEN}GPU: $GPU_INFO${NC}"
else
    echo -e "${YELLOW}nvidia-smi inte tillgänglig${NC}"
fi

# Starta frontend i bakgrunden
echo -e "${CYAN}Startar frontend...${NC}"
python3 "$SCRIPT_DIR/frontend/server.py" &
FRONTEND_PID=$!
sleep 1

if kill -0 $FRONTEND_PID 2>/dev/null; then
    echo -e "${GREEN}Frontend startad på http://localhost:3000${NC}"
else
    echo -e "${YELLOW}Frontend kunde inte startas${NC}"
fi

# Starta backend
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Backend: http://localhost:8000${NC}"
echo -e "${GREEN}Frontend: http://localhost:3000  ← ÖPPNA DENNA I WEBBLÄSAREN${NC}"
echo -e "${GREEN}API Docs: http://localhost:8000/docs${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${CYAN}Tryck Ctrl+C för att stoppa${NC}"
echo ""

# Fånga Ctrl+C och stoppa allt
trap "echo ''; echo 'Stoppar...'; kill $FRONTEND_PID 2>/dev/null; exit 0" INT TERM

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
