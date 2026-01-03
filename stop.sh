#!/usr/bin/env bash
#
# SIMONS AI - STOPP SCRIPT
# Stoppar alla tjänster
#

CYAN='\033[0;36m'
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${CYAN}Stoppar Simons AI...${NC}"

# Stoppa systemd services
systemctl --user stop simons-ai-frontend.service 2>/dev/null || true
systemctl --user stop simons-ai-backend.service 2>/dev/null || true

# Stoppa eventuella manuella processer
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "frontend/server.py" 2>/dev/null || true

echo -e "${GREEN}✓ Simons AI stoppad${NC}"
