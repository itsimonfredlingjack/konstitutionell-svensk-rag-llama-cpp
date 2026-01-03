#!/usr/bin/env bash
#
# SIMONS AI - DUAL MODEL SETUP
# Konfigurerar Ollama för att hålla båda modellerna laddade samtidigt
#

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          SIMONS AI - DUAL MODEL CONFIGURATION                ║"
echo "║                                                              ║"
echo "║  QWEN_NEXUS (14B) + GEMMA_SAGE (9B) = ~12 GB VRAM           ║"
echo "║  Båda laddade samtidigt för instant switching               ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ============================================================
# STEG 1: Skapa Ollama environment config
# ============================================================
echo -e "${CYAN}[1/4] Konfigurerar Ollama för dual-model...${NC}"

# Skapa systemd override för Ollama
sudo mkdir -p /etc/systemd/system/ollama.service.d/

sudo tee /etc/systemd/system/ollama.service.d/dual-model.conf > /dev/null << 'EOF'
[Service]
# Dual Model Configuration for RTX 4070 (12GB VRAM)
# Keep both models loaded in VRAM
Environment="OLLAMA_MAX_LOADED_MODELS=2"
# Allow parallel requests
Environment="OLLAMA_NUM_PARALLEL=4"
# Keep models loaded longer (10 minutes)
Environment="OLLAMA_KEEP_ALIVE=10m"
# Increase context size
Environment="OLLAMA_MAX_QUEUE=512"
EOF

echo -e "${GREEN}  ✓ Ollama konfigurerad för dual-model${NC}"

# ============================================================
# STEG 2: Ladda om Ollama
# ============================================================
echo -e "${CYAN}[2/4] Startar om Ollama med ny konfiguration...${NC}"

sudo systemctl daemon-reload
sudo systemctl restart ollama

sleep 3

if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "${GREEN}  ✓ Ollama körs${NC}"
else
    echo -e "${RED}  ✕ Ollama startade inte korrekt${NC}"
    exit 1
fi

# ============================================================
# STEG 3: Ladda ner modeller
# ============================================================
echo -e "${CYAN}[3/4] Laddar ner modeller...${NC}"

# QWEN 14B
echo -e "  Laddar QWEN 2.5 Coder 14B (~9 GB)..."
if ollama list 2>/dev/null | grep -q "qwen3:14b"; then
    echo -e "${GREEN}  ✓ QWEN redan nedladdad${NC}"
else
    ollama pull qwen3:14b
    echo -e "${GREEN}  ✓ QWEN nedladdad${NC}"
fi

# GEMMA 9B
echo -e "  Laddar Gemma 2 9B..."
if ollama list 2>/dev/null | grep -q "gemma2:9b"; then
    echo -e "${GREEN}  ✓ GEMMA redan nedladdad${NC}"
else
    ollama pull gemma2:9b
    echo -e "${GREEN}  ✓ GEMMA nedladdad${NC}"
fi

# ============================================================
# STEG 4: Pre-load båda modellerna
# ============================================================
echo -e "${CYAN}[4/4] Förladdar båda modellerna i VRAM...${NC}"
echo -e "${YELLOW}  Detta tar ~30 sekunder...${NC}"

# Pre-load QWEN
echo -e "  Loading QWEN 14B..."
curl -s http://localhost:11434/api/generate -d '{
  "model": "qwen3:14b",
  "prompt": "Hi",
  "options": {"num_predict": 1}
}' > /dev/null 2>&1

# Pre-load GEMMA
echo -e "  Loading GEMMA..."
curl -s http://localhost:11434/api/generate -d '{
  "model": "gemma2:9b",
  "prompt": "Hi",
  "options": {"num_predict": 1}
}' > /dev/null 2>&1

sleep 3

# Verifiera
echo ""
echo -e "${CYAN}Verifierar laddade modeller...${NC}"
LOADED=$(curl -s http://localhost:11434/api/ps 2>/dev/null)

if echo "$LOADED" | grep -q "qwen3"; then
    echo -e "${GREEN}  ✓ QWEN laddad i VRAM${NC}"
else
    echo -e "${YELLOW}  ? QWEN status okänd${NC}"
fi

if echo "$LOADED" | grep -q "gemma2"; then
    echo -e "${GREEN}  ✓ GEMMA laddad i VRAM${NC}"
else
    echo -e "${YELLOW}  ? GEMMA status okänd${NC}"
fi

# Visa VRAM-användning
echo ""
echo -e "${CYAN}VRAM-användning:${NC}"
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader

# ============================================================
# KLAR!
# ============================================================
echo ""
echo -e "${GREEN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║              DUAL MODEL SETUP KLAR!                          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo -e "  Modeller laddade:"
echo -e "    ${CYAN}QWEN_NEXUS${NC} - qwen3:14b (~7.5 GB)"
echo -e "    ${CYAN}GEMMA_SAGE${NC} - gemma2:9b (~4.5 GB)"
echo ""
echo -e "  Nästa steg:"
echo -e "    ./start.sh"
echo ""
