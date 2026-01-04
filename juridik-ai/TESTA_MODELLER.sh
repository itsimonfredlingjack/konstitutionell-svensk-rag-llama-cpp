#!/bin/bash
# Script för att testa olika modeller

echo "=== Testar modeller för svenska ==="
echo ""

# Testa Phi 4 Mini om den finns
echo "1. Testar Phi 4 Mini..."
if ollama show phi4-mini >/dev/null 2>&1; then
    echo "   Phi 4 Mini finns! Testar..."
    ollama run phi4-mini "Hej, kan du svara kort på svenska? Hur mår du?"
    echo ""
else
    echo "   Phi 4 Mini finns inte lokalt. Ladda ner med: ollama pull phi4-mini"
    echo ""
fi

# Testa Phi 3 Mini
echo "2. Testar Phi 3 Mini..."
if ollama show phi3:mini >/dev/null 2>&1; then
    echo "   Phi 3 Mini finns! Testar..."
    ollama run phi3:mini "Hej, kan du svara kort på svenska? Hur mår du?"
    echo ""
else
    echo "   Phi 3 Mini finns inte lokalt. Ladda ner med: ollama pull phi3:mini"
    echo ""
fi

# Testa Llama 3.1
echo "3. Testar Llama 3.1:8b..."
if ollama show llama3.1:8b >/dev/null 2>&1; then
    echo "   Llama 3.1:8b finns! Testar..."
    ollama run llama3.1:8b "Hej, kan du svara kort på svenska? Hur mår du?"
    echo ""
else
    echo "   Llama 3.1:8b finns inte lokalt. Ladda ner med: ollama pull llama3.1:8b"
    echo ""
fi

# Testa nuvarande DeepSeek
echo "4. Testar nuvarande DeepSeek R1:7b..."
ollama run deepseek-r1:7b "Hej, kan du svara kort på svenska? Hur mår du?"
echo ""

echo "=== Klart! ==="
echo "Vilken modell svarade bäst på svenska?"
