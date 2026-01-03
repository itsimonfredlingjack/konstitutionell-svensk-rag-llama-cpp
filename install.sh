#!/usr/bin/env bash
#
# SIMONS AI - KOMPLETT INSTALLATION
# Kör detta script EN GÅNG för att installera allt
#

set -e

# Färger
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║         SIMONS AI - ETERNAL DREAMS INSTALLATION              ║"
echo "║                                                              ║"
echo "║  Detta script installerar:                                   ║"
echo "║  • Python dependencies                                       ║"
echo "║  • Ollama + modeller (THINK/CHILL)                          ║"
echo "║  • Systemd services för automatisk start                    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""

# ============================================================
# STEG 1: Python Virtual Environment
# ============================================================
echo -e "${CYAN}[1/5] Skapar Python virtual environment...${NC}"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo -e "${GREEN}  ✓ Virtual environment skapad${NC}"
else
    echo -e "${YELLOW}  → Virtual environment finns redan${NC}"
fi

source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo -e "${GREEN}  ✓ Python dependencies installerade${NC}"

# ============================================================
# STEG 2: Ollama Installation
# ============================================================
echo ""
echo -e "${CYAN}[2/5] Kontrollerar Ollama...${NC}"

if ! command -v ollama &> /dev/null; then
    echo -e "${YELLOW}  Ollama är inte installerat. Installerar...${NC}"
    curl -fsSL https://ollama.ai/install.sh | sh
    echo -e "${GREEN}  ✓ Ollama installerat${NC}"
else
    echo -e "${GREEN}  ✓ Ollama redan installerat${NC}"
fi

# ============================================================
# STEG 3: Ladda ner modeller
# ============================================================
echo ""
echo -e "${CYAN}[3/5] Laddar ner AI-modeller...${NC}"
echo -e "${YELLOW}  OBS: Detta kan ta lång tid första gången (~10-15 minuter)${NC}"

# Starta Ollama temporärt om det inte körs
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "  Startar Ollama..."
    ollama serve &
    OLLAMA_PID=$!
    sleep 5
fi

# THINK-modell (14B)
echo -e "  Laddar THINK-modell (qwen3:14b)..."
if ollama list 2>/dev/null | grep -q "qwen3:14b"; then
    echo -e "${GREEN}  ✓ THINK-modell finns redan${NC}"
else
    ollama pull qwen3:14b
    echo -e "${GREEN}  ✓ THINK-modell nedladdad${NC}"
fi

# CHILL-modell (3B)
echo -e "  Laddar CHILL-modell (qwen3:14b)..."
if ollama list 2>/dev/null | grep -q "qwen3:14b"; then
    echo -e "${GREEN}  ✓ CHILL-modell finns redan${NC}"
else
    ollama pull qwen3:14b
    echo -e "${GREEN}  ✓ CHILL-modell nedladdad${NC}"
fi

# Stoppa temporär Ollama
if [ ! -z "$OLLAMA_PID" ]; then
    kill $OLLAMA_PID 2>/dev/null || true
fi

# ============================================================
# STEG 4: Installera Systemd Services
# ============================================================
echo ""
echo -e "${CYAN}[4/5] Installerar systemd services...${NC}"

# Skapa user systemd directory
mkdir -p ~/.config/systemd/user

# Kopiera service-filer
cp "$SCRIPT_DIR/systemd/simons-ai-backend.service" ~/.config/systemd/user/
cp "$SCRIPT_DIR/systemd/simons-ai-frontend.service" ~/.config/systemd/user/

# Ladda om systemd
systemctl --user daemon-reload

# Aktivera services (startar automatiskt vid login)
systemctl --user enable simons-ai-backend.service
systemctl --user enable simons-ai-frontend.service

# Aktivera lingering (så services körs även utan login)
loginctl enable-linger "$USER" 2>/dev/null || true

echo -e "${GREEN}  ✓ Systemd services installerade och aktiverade${NC}"

# ============================================================
# STEG 5: Gör scripts körbara
# ============================================================
echo ""
echo -e "${CYAN}[5/5] Slutför installation...${NC}"

chmod +x "$SCRIPT_DIR/start.sh" 2>/dev/null || true
chmod +x "$SCRIPT_DIR/stop.sh" 2>/dev/null || true
chmod +x "$SCRIPT_DIR/status.sh" 2>/dev/null || true
chmod +x "$SCRIPT_DIR/fix.sh" 2>/dev/null || true
chmod +x "$SCRIPT_DIR/frontend/server.py" 2>/dev/null || true

echo -e "${GREEN}  ✓ Scripts konfigurerade${NC}"

# ============================================================
# KLAR!
# ============================================================
echo ""
echo -e "${GREEN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    INSTALLATION KLAR!                        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo -e "  ${CYAN}Starta systemet:${NC}"
echo "    ./start.sh"
echo ""
echo -e "  ${CYAN}Eller med systemd (rekommenderas):${NC}"
echo "    systemctl --user start simons-ai-backend"
echo "    systemctl --user start simons-ai-frontend"
echo ""
echo -e "  ${CYAN}Öppna i webbläsaren:${NC}"
echo "    http://localhost:3000"
echo ""
echo -e "  ${CYAN}Vid problem:${NC}"
echo "    ./fix.sh"
echo "    ./status.sh"
echo ""
