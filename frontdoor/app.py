"""Hybrid cloud demo storefront.

One tiny container that shows WHERE it is running, so a non-technical
audience can see the same app in two places.

Configure with environment variables:
  STORE_NAME     - shop name shown on the page (default: Maple & Co.)
  LOCATION       - where this copy runs, e.g. "Store #214 back room"
  LOCATION_TYPE  - "edge" (amber banner) or "cloud" (blue banner)
  APP_VERSION    - version label (default: 1.0)
Uses only the Python standard library.
"""
import html
import json
import os
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer

STORE_NAME = os.environ.get("STORE_NAME", "Maple & Co.")
LOCATION = os.environ.get("LOCATION", "Unknown location")
LOCATION_TYPE = os.environ.get("LOCATION_TYPE", "cloud").lower()
APP_VERSION = os.environ.get("APP_VERSION", "1.0")
PORT = int(os.environ.get("PORT", "8080"))
HOST = socket.gethostname()

BANNER = {
    "edge": ("#b45309", "#fef3c7", "&#127978;", "On-premises"),
    "cloud": ("#1d4ed8", "#dbeafe", "&#9729;&#65039;", "Public cloud"),
}.get(LOCATION_TYPE, ("#374151", "#f3f4f6", "&#128421;&#65039;", "Server"))

PRODUCTS = [
    ("Insulated Winter Parka", "$189"),
    ("Cast Iron Skillet", "$49"),
    ("Smart LED Bulb 4-pack", "$39"),
    ("Holiday Light String", "$24"),
    ("Thermal Travel Mug", "$19"),
    ("Wireless Earbuds", "$79"),
]


def page():
    dark, light, icon, kind = BANNER
    cards = "".join(
        f'<div class="card"><div class="img"></div><h3>{html.escape(n)}</h3>'
        f'<p>{p}</p><button>Add to cart</button></div>'
        for n, p in PRODUCTS
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(STORE_NAME)}</title>
<style>
 body{{margin:0;font-family:system-ui,sans-serif;background:#fafafa;color:#111}}
 .banner{{background:{dark};color:#fff;padding:28px 24px;text-align:center}}
 .banner .kind{{font-size:15px;letter-spacing:.12em;text-transform:uppercase;opacity:.85}}
 .banner .loc{{font-size:40px;font-weight:800;margin-top:6px}}
 .meta{{background:{light};color:{dark};text-align:center;padding:10px;font-size:15px}}
 header{{padding:20px 24px;font-size:26px;font-weight:700}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px;padding:0 24px 32px}}
 .card{{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px}}
 .img{{height:110px;border-radius:8px;background:linear-gradient(135deg,#e5e7eb,#d1d5db)}}
 .card h3{{font-size:16px;margin:12px 0 4px}} .card p{{margin:0 0 12px;font-weight:700}}
 button{{width:100%;padding:8px;border:0;border-radius:8px;background:#111;color:#fff}}
</style></head>
<body>
 <div class="banner"><div class="kind">{icon} {kind}</div>
  <div class="loc">Running in: {html.escape(LOCATION)}</div></div>
 <div class="meta">Same app, version {html.escape(APP_VERSION)} &middot;
  served by copy <b>{html.escape(HOST)}</b></div>
 <header>{html.escape(STORE_NAME)} &mdash; Holiday Deals</header>
 <div class="grid">{cards}</div>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/info"):
            body = json.dumps({"store": STORE_NAME, "location": LOCATION,
                               "type": LOCATION_TYPE, "version": APP_VERSION,
                               "host": HOST}).encode()
            ctype = "application/json"
        elif self.path.startswith("/healthz"):
            body, ctype = b"ok", "text/plain"
        else:
            body, ctype = page().encode(), "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"Serving {STORE_NAME} ({LOCATION}) on port {PORT}", flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
