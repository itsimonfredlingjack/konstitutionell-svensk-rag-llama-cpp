#!/usr/bin/env bash
#
# SIMONS AI - FIX SCRIPT
# Automatisk felsökning och reparation
#
# Kör detta om något inte fungerar!
#

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║              SIMONS AI - AUTOMATISK FELSÖKNING               ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

FIXED=0
PROBLEMS=0

# ============================================================
# FIX 1: Stoppa eventuella hängande processer
# ============================================================
echo -e "${CYAN}[1/7] Rensar gamla processer...${NC}"
pkill -f "uvicorn app.main:app" 2>/dev/null && echo "  Stoppade gammal backend" || true
pkill -f "frontend/server.py" 2>/dev/null && echo "  Stoppade gammal frontend" || true
sleep 2
echo -e "${GREEN}  ✓ Klart${NC}"

# ============================================================
# FIX 2: Kontrollera virtual environment
# ============================================================
echo -e "${CYAN}[2/7] Kontrollerar Python environment...${NC}"
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}  Skapar virtual environment...${NC}"
    python3 -m venv .venv
    FIXED=$((FIXED+1))
fi

source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo -e "${GREEN}  ✓ Python environment OK${NC}"

# ============================================================
# FIX 3: Kontrollera Ollama
# ============================================================
echo -e "${CYAN}[3/7] Kontrollerar Ollama...${NC}"
if ! command -v ollama &> /dev/null; then
    echo -e "${RED}  ✕ Ollama är inte installerat!${NC}"
    echo -e "${YELLOW}    Installera med: curl -fsSL https://ollama.ai/install.sh | sh${NC}"
    PROBLEMS=$((PROBLEMS+1))
else
    # Starta Ollama om det inte körs
    if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo -e "${YELLOW}  Startar Ollama...${NC}"
        nohup ollama serve > /dev/null 2>&1 &
        sleep 5
        FIXED=$((FIXED+1))
    fi

    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo -e "${GREEN}  ✓ Ollama körs${NC}"
    else
        echo -e "${RED}  ✕ Kunde inte starta Ollama${NC}"
        PROBLEMS=$((PROBLEMS+1))
    fi
fi

# ============================================================
# FIX 4: Kontrollera modeller
# ============================================================
echo -e "${CYAN}[4/7] Kontrollerar AI-modeller...${NC}"
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    MODELS=$(ollama list 2>/dev/null || echo "")

    # GPT-OSS 20B (Arkitekten)
    if echo "$MODELS" | grep -q "gpt-oss"; then
        echo -e "${GREEN}  ✓ GPT-OSS 20B (Arkitekten) finns${NC}"
    else
        echo -e "${YELLOW}  GPT-OSS saknas - kör 'ollama create gpt-oss -f ~/Modelfile-GPTOSS'${NC}"
        PROBLEMS=$((PROBLEMS+1))
    fi

    # Devstral 24B (Kodaren)
    if echo "$MODELS" | grep -q "devstral"; then
        echo -e "${GREEN}  ✓ Devstral 24B (Kodaren) finns${NC}"
    else
        echo -e "${YELLOW}  Devstral saknas - kör 'ollama create devstral -f ~/Modelfile-Devstral'${NC}"
        PROBLEMS=$((PROBLEMS+1))
    fi
else
    echo -e "${RED}  ✕ Kan inte kontrollera modeller - Ollama körs inte${NC}"
    PROBLEMS=$((PROBLEMS+1))
fi

# ============================================================
# FIX 5: Kontrollera portar
# ============================================================
echo -e "${CYAN}[5/7] Kontrollerar portar...${NC}"

check_port() {
    local port=$1
    local name=$2
    if lsof -i :$port > /dev/null 2>&1; then
        PID=$(lsof -t -i :$port 2>/dev/null | head -1)
        PROC=$(ps -p $PID -o comm= 2>/dev/null || echo "unknown")
        if [[ "$PROC" != *"uvicorn"* ]] && [[ "$PROC" != *"python"* ]]; then
            echo -e "${YELLOW}  Port $port används av $PROC (PID: $PID)${NC}"
            echo -e "${YELLOW}  Försöker frigöra...${NC}"
            kill $PID 2>/dev/null || true
            sleep 1
            FIXED=$((FIXED+1))
        fi
    fi
}

check_port 8000 "Backend"
check_port 3000 "Frontend"
echo -e "${GREEN}  ✓ Portar kontrollerade${NC}"

# ============================================================
# FIX 6: Uppdatera systemd services
# ============================================================
echo -e "${CYAN}[6/7] Uppdaterar systemd services...${NC}"
mkdir -p ~/.config/systemd/user

cp "$SCRIPT_DIR/systemd/simons-ai-backend.service" ~/.config/systemd/user/ 2>/dev/null || true
cp "$SCRIPT_DIR/systemd/simons-ai-frontend.service" ~/.config/systemd/user/ 2>/dev/null || true

systemctl --user daemon-reload
systemctl --user enable simons-ai-backend.service 2>/dev/null || true
systemctl --user enable simons-ai-frontend.service 2>/dev/null || true
echo -e "${GREEN}  ✓ Systemd uppdaterat${NC}"

# ============================================================
# FIX 7: Starta tjänster
# ============================================================
echo -e "${CYAN}[7/7] Startar tjänster...${NC}"

# Starta backend
systemctl --user restart simons-ai-backend.service 2>/dev/null || {
    echo -e "${YELLOW}  Startar backend manuellt...${NC}"
    cd "$SCRIPT_DIR"
    source .venv/bin/activate
    nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/simons-ai-backend.log 2>&1 &
}
sleep 3

# Starta frontend
systemctl --user restart simons-ai-frontend.service 2>/dev/null || {
    echo -e "${YELLOW}  Startar frontend manuellt...${NC}"
    nohup python3 "$SCRIPT_DIR/frontend/server.py" > /tmp/simons-ai-frontend.log 2>&1 &
}
sleep 2

# Verifiera
echo ""
echo -e "${CYAN}Verifierar...${NC}"

if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo -e "${GREEN}  ✓ Backend körs på port 8000${NC}"
else
    echo -e "${RED}  ✕ Backend svarar inte${NC}"
    PROBLEMS=$((PROBLEMS+1))
fi

if curl -s http://localhost:3000 > /dev/null 2>&1; then
    echo -e "${GREEN}  ✓ Frontend körs på port 3000${NC}"
else
    echo -e "${RED}  ✕ Frontend svarar inte${NC}"
    PROBLEMS=$((PROBLEMS+1))
fi

# ============================================================
# RESULTAT
# ============================================================
echo ""
echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"

if [ $PROBLEMS -eq 0 ]; then
    echo -e "${GREEN}✓ ALLT FUNGERAR!${NC}"
    echo ""
    echo -e "  Öppna i webbläsaren: ${CYAN}http://localhost:3000${NC}"
    echo ""
    if [ $FIXED -gt 0 ]; then
        echo -e "  (Fixade $FIXED problem automatiskt)"
    fi
else
    echo -e "${RED}✕ $PROBLEMS problem kvarstår${NC}"
    echo ""
    echo "  Försök:"
    echo "    1. Starta om datorn"
    echo "    2. Kör ./fix.sh igen"
    echo "    3. Kontrollera loggar: journalctl --user -u simons-ai-backend -n 50"
fi
echo ""
