"""Hybrid cloud demo storefront.

A generic electronics store page that shows WHERE it is running, so a
non-technical audience can see the same app in two places.

Configure with environment variables:
  STORE_NAME     - shop name shown on the page (default: Demo Electronics)
  LOCATION       - where this copy runs, e.g. "Your data centre"
  LOCATION_TYPE  - "edge" (amber banner) or "cloud" (blue banner)
  APP_VERSION    - version label (default: 1.0)
Uses only the Python standard library.
"""
import html
import json
import os
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer

STORE_NAME = os.environ.get("STORE_NAME", "Demo Electronics")
LOCATION = os.environ.get("LOCATION", "Unknown location")
LOCATION_TYPE = os.environ.get("LOCATION_TYPE", "cloud").lower()
APP_VERSION = os.environ.get("APP_VERSION", "1.0")
PORT = int(os.environ.get("PORT", "8080"))
HOST = socket.gethostname()

BANNER = {
    "edge": ("#b45309", "#fef3c7", "&#127970;", "On-premises"),
    "cloud": ("#1d4ed8", "#dbeafe", "&#9729;&#65039;", "Public cloud"),
}.get(LOCATION_TYPE, ("#374151", "#f3f4f6", "&#128421;&#65039;", "Server"))

CATEGORIES = ["TVs & Home Theatre", "Computers & Tablets", "Gaming", "Headphones & Audio",
              "Smart Home", "Phones", "Appliances", "Cameras"]

# (emoji, name, rating, reviews, was, now, badge)
PRODUCTS = [
    ("&#128250;", "65-inch 4K UHD Smart TV", 4.6, 2841, 799, 499, "Doorbuster"),
    ("&#127911;", "Wireless Noise-Cancelling Headphones", 4.7, 5120, 399, 249, "Top deal"),
    ("&#128187;", "15-inch Gaming Laptop, 16GB RAM", 4.5, 963, 1399, 999, "Doorbuster"),
    ("&#127918;", "Next-Gen Game Console Bundle", 4.8, 3307, 599, 499, "Limited stock"),
    ("&#8986;", "Fitness Smartwatch, 45mm", 4.4, 1788, 429, 299, "Top deal"),
    ("&#129302;", "Self-Emptying Robot Vacuum", 4.3, 1215, 549, 299, "Doorbuster"),
    ("&#128241;", "Unlocked 5G Smartphone, 256GB", 4.6, 2210, 1099, 899, "Top deal"),
    ("&#128266;", "Smart Speaker with Voice Assistant", 4.5, 4402, 129, 59, "Limited stock"),
]


def stars(r):
    full = int(round(r))
    return "&#9733;" * full + "&#9734;" * (5 - full)


def page():
    dark, light, icon, kind = BANNER
    cats = "".join(f"<a>{html.escape(c)}</a>" for c in CATEGORIES)
    cards = "".join(
        f'<div class="card"><span class="badge">{b}</span><div class="img">{e}</div>'
        f'<h3>{html.escape(n)}</h3><div class="rate"><span>{stars(r)}</span> {r} ({v:,})</div>'
        f'<div class="price"><b>${now:,}</b> <s>Was ${was:,}</s></div>'
        f'<div class="save">Save ${was - now:,}</div>'
        f'<div class="ful"><span>&#10003; Pickup today</span><span>&#10003; Free shipping</span></div>'
        f'<button>Add to cart</button></div>'
        for e, n, r, v, was, now, b in PRODUCTS
    )
    name = html.escape(STORE_NAME)
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name}</title>
<style>
 *{{box-sizing:border-box}}
 body{{margin:0;font-family:system-ui,sans-serif;background:#f4f5f7;color:#111}}
 .banner{{background:{dark};color:#fff;padding:22px 24px;text-align:center}}
 .banner .kind{{font-size:14px;letter-spacing:.12em;text-transform:uppercase;opacity:.85}}
 .banner .loc{{font-size:36px;font-weight:800;margin-top:4px}}
 .meta{{background:{light};color:{dark};text-align:center;padding:8px;font-size:14px}}
 .top{{background:#0f172a;color:#fff;display:flex;align-items:center;gap:20px;padding:14px 24px;flex-wrap:wrap}}
 .logo{{font-size:22px;font-weight:800;letter-spacing:-.01em}}
 .logo span{{color:#22d3ee}}
 .search{{flex:1;min-width:220px;background:#fff;color:#64748b;border-radius:8px;padding:10px 14px;font-size:15px}}
 .acct{{font-size:14px;opacity:.9}}
 nav{{background:#1e293b;display:flex;gap:22px;padding:10px 24px;overflow-x:auto;white-space:nowrap}}
 nav a{{color:#cbd5e1;font-size:14px}}
 .hero{{background:linear-gradient(90deg,#111827,#334155);color:#fff;padding:26px 24px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}}
 .hero h1{{margin:0;font-size:32px}} .hero p{{margin:4px 0 0;color:#cbd5e1}}
 .count{{background:#22d3ee;color:#0f172a;font-weight:800;padding:8px 14px;border-radius:8px}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px;padding:22px 24px 34px}}
 .card{{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px;position:relative;display:flex;flex-direction:column}}
 .badge{{position:absolute;top:12px;left:12px;background:#dc2626;color:#fff;font-size:12px;font-weight:700;padding:3px 8px;border-radius:6px}}
 .img{{height:120px;border-radius:8px;background:#f1f5f9;display:grid;place-items:center;font-size:58px}}
 .card h3{{font-size:15px;margin:12px 0 4px;min-height:38px}}
 .rate{{font-size:13px;color:#64748b}} .rate span{{color:#f59e0b}}
 .price{{margin-top:8px}} .price b{{font-size:22px}} .price s{{color:#64748b;font-size:13px;margin-left:4px}}
 .save{{color:#dc2626;font-weight:700;font-size:13px;margin-top:2px}}
 .ful{{display:flex;flex-direction:column;gap:2px;font-size:12px;color:#15803d;margin:10px 0 12px}}
 button{{margin-top:auto;width:100%;padding:10px;border:0;border-radius:8px;background:#0f172a;color:#fff;font-weight:600}}
 footer{{text-align:center;color:#64748b;font-size:12px;padding:0 24px 24px}}
</style></head>
<body>
 <div class="banner"><div class="kind">{icon} {kind}</div>
  <div class="loc">Running in: {html.escape(LOCATION)}</div></div>
 <div class="meta">Same app, version {html.escape(APP_VERSION)} &middot;
  served by copy <b>{html.escape(HOST)}</b></div>
 <div class="top"><div class="logo">{name}<span>.</span></div>
  <div class="search">&#128269; Search products, brands and more</div>
  <div class="acct">&#128100; Account &nbsp; &#128722; Cart (0)</div></div>
 <nav>{cats}</nav>
 <div class="hero"><div><h1>Black Friday Deals</h1>
  <p>Shop online or pick up in store today. While quantities last.</p></div>
  <div class="count">Deals end in 2d 14h 06m</div></div>
 <div class="grid">{cards}</div>
 <footer>Demonstration store for a hybrid cloud presentation. Not a real retailer.</footer>
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
