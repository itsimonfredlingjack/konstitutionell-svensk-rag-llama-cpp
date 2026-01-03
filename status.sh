#!/usr/bin/env bash
#
# SIMONS AI - STATUS SCRIPT
# Visar status för alla komponenter
#

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║              SIMONS AI - SYSTEM STATUS                       ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================
# GPU STATUS
# ============================================================
echo -e "${CYAN}[GPU]${NC}"
if command -v nvidia-smi &> /dev/null; then
    GPU_INFO=$(nvidia-smi --query-gpu=name,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits 2>/dev/null)
    if [ ! -z "$GPU_INFO" ]; then
        IFS=',' read -r NAME USED TOTAL TEMP <<< "$GPU_INFO"
        echo -e "  ${GREEN}✓${NC} $NAME"
        echo -e "    VRAM: ${USED}MB / ${TOTAL}MB"
        echo -e "    Temp: ${TEMP}°C"
    else
        echo -e "  ${RED}✕${NC} GPU ej tillgänglig"
    fi
else
    echo -e "  ${YELLOW}?${NC} nvidia-smi ej installerat"
fi
echo ""

# ============================================================
# OLLAMA STATUS
# ============================================================
echo -e "${CYAN}[OLLAMA]${NC}"
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} Ollama körs på port 11434"

    # Visa modeller
    MODELS=$(ollama list 2>/dev/null | tail -n +2)
    if [ ! -z "$MODELS" ]; then
        echo "    Modeller:"
        echo "$MODELS" | while read line; do
            echo "      - $line"
        done
    fi

    # Visa laddade modeller
    RUNNING=$(curl -s http://localhost:11434/api/ps 2>/dev/null | grep -o '"name":"[^"]*"' | cut -d'"' -f4)
    if [ ! -z "$RUNNING" ]; then
        echo -e "    ${GREEN}Aktiv modell: $RUNNING${NC}"
    fi
else
    echo -e "  ${RED}✕${NC} Ollama körs INTE"
    echo "    Starta med: ollama serve"
fi
echo ""

# ============================================================
# BACKEND STATUS
# ============================================================
echo -e "${CYAN}[BACKEND]${NC}"
if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    HEALTH=$(curl -s http://localhost:8000/api/health)
    STATUS=$(echo "$HEALTH" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    echo -e "  ${GREEN}✓${NC} Backend körs på port 8000 (status: $STATUS)"
else
    echo -e "  ${RED}✕${NC} Backend körs INTE"

    # Kontrollera systemd
    if systemctl --user is-active simons-ai-backend.service &>/dev/null; then
        echo "    Systemd service aktiv men svarar inte"
    else
        echo "    Starta med: systemctl --user start simons-ai-backend"
    fi
fi
echo ""

# ============================================================
# FRONTEND STATUS
# ============================================================
echo -e "${CYAN}[FRONTEND]${NC}"
if curl -s http://localhost:3000 > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} Frontend körs på port 3000"
    echo "    Öppna: http://localhost:3000"
else
    echo -e "  ${RED}✕${NC} Frontend körs INTE"
    echo "    Starta med: systemctl --user start simons-ai-frontend"
fi
echo ""

# ============================================================
# SYSTEMD SERVICES
# ============================================================
echo -e "${CYAN}[SYSTEMD SERVICES]${NC}"

check_service() {
    local service=$1
    local status=$(systemctl --user is-active "$service" 2>/dev/null || echo "inactive")
    local enabled=$(systemctl --user is-enabled "$service" 2>/dev/null || echo "disabled")

    if [ "$status" = "active" ]; then
        echo -e "  ${GREEN}✓${NC} $service ($status, $enabled)"
    else
        echo -e "  ${RED}✕${NC} $service ($status, $enabled)"
    fi
}

check_service "simons-ai-backend.service"
check_service "simons-ai-frontend.service"
echo ""

# ============================================================
# SAMMANFATTNING
# ============================================================
echo -e "${CYAN}[SNABBKOMMANDON]${NC}"
echo "  Starta allt:    ./start.sh"
echo "  Stoppa allt:    ./stop.sh"
echo "  Fixa problem:   ./fix.sh"
echo "  Visa loggar:    journalctl --user -u simons-ai-backend -f"
echo ""
