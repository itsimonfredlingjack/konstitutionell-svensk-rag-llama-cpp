#!/bin/bash
# Test script for Constitutional AI Dashboard API endpoints

BASE_URL="http://localhost:8000/api/constitutional"

echo "=== Constitutional AI Dashboard API Test ==="
echo ""

echo "1. Testing Health Check..."
curl -s "${BASE_URL}/health" | jq '.status, .chromadb_connected, .collections'
echo ""

echo "2. Testing Overview Stats..."
curl -s "${BASE_URL}/stats/overview" | jq '.total_documents, .storage_size_mb'
echo ""

echo "3. Testing Collections..."
curl -s "${BASE_URL}/collections" | jq 'length, .[0].name, .[0].document_count'
echo ""

echo "4. Testing Admin Status..."
curl -s "${BASE_URL}/admin/status" | jq '.chromadb_status, .pdf_cache_files'
echo ""

echo "5. Testing Search..."
curl -s -X POST "${BASE_URL}/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "riksdag", "limit": 3}' | jq '.total, .results | length'
echo ""

echo "6. Testing Timeline (first 5 days)..."
curl -s "${BASE_URL}/stats/timeline" | jq '.[0:5] | map(.date)'
echo ""

echo "=== All Tests Complete ==="
