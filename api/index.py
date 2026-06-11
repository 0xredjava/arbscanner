"""Vercel landing page for the arb scanner repo.

The full scanner (Playwright scrapers, long-running loops, Streamlit UI)
must run locally or on Streamlit Cloud — not on Vercel serverless.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Arb Scanner</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 720px; margin: 3rem auto; padding: 0 1.5rem; line-height: 1.6; color: #111; }
    code, pre { background: #f4f4f5; border-radius: 6px; }
    code { padding: 0.15rem 0.35rem; }
    pre { padding: 1rem; overflow-x: auto; }
    a { color: #0969da; }
    .note { background: #fff8c5; border: 1px solid #d4a72c; padding: 1rem; border-radius: 8px; }
  </style>
</head>
<body>
  <h1>Sports Betting Arbitrage Scanner</h1>
  <p>This Vercel deployment is a project landing page only. The scanner itself is a Python CLI and is not hosted here.</p>
  <div class="note">
    <strong>Run locally</strong>
    <pre>git clone https://github.com/CryptoDungeonMaster/arbscanner.git
cd arbscanner
python -m venv venv
venv\\Scripts\\activate
pip install -r requirements.txt
copy .env.example .env
python scan.py --once --platforms polymarket,cloudbet
streamlit run dashboard.py</pre>
  </div>
  <p><a href="https://github.com/CryptoDungeonMaster/arbscanner">View source on GitHub</a></p>
</body>
</html>"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            body = HTML.encode("utf-8")
            content_type = "text/html; charset=utf-8"
        elif self.path == "/api/health":
            body = json.dumps(
                {
                    "status": "ok",
                    "service": "arb-scanner",
                    "note": "Scanner runs locally; this endpoint is informational only.",
                    "github": "https://github.com/CryptoDungeonMaster/arbscanner",
                }
            ).encode("utf-8")
            content_type = "application/json"
        else:
            body = json.dumps({"error": "not_found"}).encode("utf-8")
            content_type = "application/json"
            self.send_response(404)
            self.send_header("Content-type", content_type)
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(200)
        self.send_header("Content-type", content_type)
        self.end_headers()
        self.wfile.write(body)
