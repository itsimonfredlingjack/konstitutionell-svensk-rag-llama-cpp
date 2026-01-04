#!/usr/bin/env python3
"""
Simple HTTP server for harvest stats - n8n can poll this endpoint
Run: python harvest_stats_server.py
Endpoint: http://localhost:8899/stats
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from harvest_stats_api import get_harvest_stats

PORT = 8899


class StatsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/stats" or self.path == "/":
            stats = get_harvest_stats()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(stats, ensure_ascii=False).encode("utf-8"))
        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress logging


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), StatsHandler)
    print(f"Harvest Stats Server running on http://0.0.0.0:{PORT}/stats")
    server.serve_forever()
