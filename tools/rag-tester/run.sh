#!/bin/bash
# RAG-Eval Terminal - Startup Script
# Run this to launch the interactive CLI

cd "$(dirname "$0")"

# Check if venv exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

# Run the app
echo "🚀 Starting RAG-Eval Terminal..."
.venv/bin/python main.py
