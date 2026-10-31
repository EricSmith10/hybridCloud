"""Front door: cloud-bursting demo.

Simulated shoppers go to the on-prem store server first. Once it hits its
capacity (shoppers per second), the overflow is routed to the public cloud.
A live dashboard shows the split.

Environment variables:
  LOCAL_URL       on-prem store app, e.g. http://localhost:8090
  CLOUD_URL       OpenShift route, e.g. https://hybrid-cloud-git-....openshiftapps.com
  LOCAL_CAPACITY  shoppers/sec the store server can handle (default 10)
  PORT            dashboard port (default 8095)
Standard library only.
"""
import json
import os
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

LOCAL_URL = os.environ.get("LOCAL_URL", "http://localhost:8090").rstrip("/")
CLOUD_URL = os.environ.get("CLOUD_URL", "").rstrip("/")
PORT = int(os.environ.get("PORT", "8095"))
HISTORY = 60
MAX_PENDING = 300

lock = threading.Lock()
state = {"rate": 0, "capacity": int(os.environ.get("LOCAL_CAPACITY", "10")), "pending": 0}
buckets = {}      # second -> counts
local_sent = {}   # second -> requests assigned to local
cloud_hosts = {}  # pod name -> last seen
info = {"local_host": None, "cloud_ok": None, "cloud_error": ""}
pool = ThreadPoolExecutor(max_workers=96)


def bucket(sec):
    b = buckets.get(sec)
    if b is None:
        b = buckets[sec] = {"local": 0, "cloud": 0, "local_err": 0, "cloud_err": 0}
        for k in [k for k in buckets if k < sec - HISTORY - 5]:
            del buckets[k]
        for k in [k for k in local_sent if k < sec - 5]:
            del local_sent[k]
    return b


def choose_target():
    sec = int(time.time())
    with lock:
        n = local_sent.get(sec, 0)
        if n < state["capacity"] or not CLOUD_URL:
            local_sent[sec] = n + 1
            return "local"
        return "cloud"


def shop():
    target = choose_target()
    url = (LOCAL_URL if target == "local" else CLOUD_URL) + "/api/info"
    sec = int(time.time())
    ok, host, err = False, None, ""
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            host = json.loads(r.read()).get("host", "?")
        ok = True
    except Exception as e:  # network down, timeout, etc.
        err = str(e)[:140]
    with lock:
        state["pending"] -= 1
        b = bucket(sec)
        if ok:
            b[target] += 1
            if target == "cloud":
                cloud_hosts[host] = time.time()
                info["cloud_ok"], info["cloud_error"] = True, ""
            else:
                info["local_host"] = host
        else:
            b[target + "_err"] += 1
            if target == "cloud":
                info["cloud_ok"], info["cloud_error"] = False, err


def submit():
    with lock:
        if state["pending"] >= MAX_PENDING:
            bucket(int(time.time()))["cloud_err"] += 1
            return
        state["pending"] += 1
    pool.submit(shop)


def generator():
    while True:
        rate = state["rate"]
        if rate <= 0:
            time.sleep(0.2)
            continue
        start = time.time()
        for i in range(rate):
            submit()
            delay = start + (i + 1) / rate - time.time()
            if delay > 0:
                time.sleep(delay)


def stats():
    now = int(time.time())
    with lock:
        series = []
        for s in range(now - HISTORY, now):
            b = buckets.get(s, {})
            series.append([b.get("local", 0), b.get("cloud", 0),
                           b.get("local_err", 0) + b.get("cloud_err", 0)])
        recent = series[-2:]
        avg = lambda i: round(sum(x[i] for x in recent) / len(recent), 1)
        t = time.time()
        return {
            "rate": state["rate"], "capacity": state["capacity"],
            "local_rps": avg(0), "cloud_rps": avg(1), "err_rps": avg(2),
            "series": series,
            "cloud_copies": sorted(h for h, seen in cloud_hosts.items() if t - seen < 5),
            "local_host": info["local_host"], "cloud_ok": info["cloud_ok"],
            "cloud_error": info["cloud_error"], "cloud_configured": bool(CLOUD_URL),
        }


DASHBOARD = r"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Front Door</title>
<style>
:root{--amber:#d97706;--amber-l:#fef3c7;--blue:#2563eb;--blue-l:#dbeafe;--red:#dc2626;--ink:#0f172a;--mut:#64748b;--line:#e2e8f0}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,sans-serif;background:#f8fafc;color:var(--ink)}
.wrap{max-width:1200px;margin:0 auto;padding:28px 24px}
h1{margin:0;font-size:30px}.sub{color:var(--mut);margin:6px 0 22px;font-size:17px}
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:22px}
button{font:inherit;font-size:16px;padding:10px 16px;border-radius:10px;border:1px solid var(--line);background:#fff;cursor:pointer}
button.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.arr{margin-left:auto;font-size:17px;color:var(--mut)}.arr b{color:var(--ink);font-size:22px}
.cards{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:22px;border-top:6px solid}
.card.l{border-top-color:var(--amber)}.card.c{border-top-color:var(--blue)}
.kind{font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:var(--mut)}
.title{font-size:22px;font-weight:700;margin:4px 0 14px}
.big{font-size:52px;font-weight:800;line-height:1}.big small{font-size:18px;color:var(--mut);font-weight:500}
.gauge{height:16px;background:#f1f5f9;border-radius:99px;margin:16px 0 8px;overflow:hidden}
.gauge div{height:100%;background:var(--amber);width:0;transition:width .5s}
.pill{display:inline-block;padding:5px 12px;border-radius:99px;font-size:14px;font-weight:600;margin-top:10px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px;min-height:30px}
.chip{background:var(--blue-l);color:var(--blue);padding:4px 10px;border-radius:8px;font-size:13px;font-family:ui-monospace,monospace}
.chart{background:#fff;border:1px solid var(--line);border-radius:16px;padding:18px;margin-top:18px}
.legend{display:flex;gap:18px;font-size:14px;color:var(--mut);margin-bottom:8px}
.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px}
canvas{width:100%;height:240px;display:block}
.warn{color:var(--red);font-size:14px;margin-top:8px;min-height:18px}
@media(max-width:760px){.cards{grid-template-columns:1fr}.arr{margin-left:0}}
</style></head><body><div class="wrap">
<h1>Front Door &middot; Hybrid traffic routing</h1>
<div class="sub">Shoppers go to the store server first. When it's full, the overflow goes to the public cloud automatically.</div>
<div class="controls">
 <button data-r="4">Quiet day</button><button data-r="10">Busy weekend</button>
 <button data-r="40">Black Friday</button><button data-r="0">Stop</button>
 <div class="arr">Shoppers arriving: <b id="rate">0</b> / sec</div>
</div>
<div class="cards">
 <div class="card l"><div class="kind">&#127978; On-premises</div><div class="title">Store server</div>
  <div class="big"><span id="lr">0</span> <small>shoppers / sec</small></div>
  <div class="gauge"><div id="g"></div></div>
  <div style="color:var(--mut);font-size:14px">Capacity: <span id="cap">0</span> shoppers / sec</div>
  <span class="pill" id="lp"></span></div>
 <div class="card c"><div class="kind">&#9729;&#65039; Public cloud</div><div class="title">Red Hat OpenShift</div>
  <div class="big"><span id="cr">0</span> <small>shoppers / sec</small></div>
  <div style="color:var(--mut);font-size:14px;margin-top:16px">Copies answering: <b id="cn">0</b></div>
  <div class="chips" id="chips"></div>
  <span class="pill" id="cp"></span><div class="warn" id="cw"></div></div>
</div>
<div class="chart"><div class="legend"><span><i style="background:var(--amber)"></i>Store server</span>
 <span><i style="background:var(--blue)"></i>Public cloud</span><span><i style="background:var(--red)"></i>Failed</span>
 <span style="margin-left:auto">Last 60 seconds</span></div><canvas id="cv"></canvas></div>
</div>
<script>
const $=id=>document.getElementById(id);
const pill=(el,txt,fg,bg)=>{el.textContent=txt;el.style.color=fg;el.style.background=bg;};
document.querySelectorAll('button[data-r]').forEach(b=>b.onclick=()=>fetch('/api/rate?n='+b.dataset.r).then(tick));
function render(s){
 $('rate').textContent=s.rate;$('lr').textContent=s.local_rps;$('cr').textContent=s.cloud_rps;$('cap').textContent=s.capacity;
 document.querySelectorAll('button[data-r]').forEach(b=>b.classList.toggle('on',+b.dataset.r===s.rate));
 const u=Math.min(1,s.local_rps/s.capacity);$('g').style.width=(u*100)+'%';
 const full=s.rate>s.capacity;
 if(s.rate===0)pill($('lp'),'Idle','#64748b','#f1f5f9');
 else if(full)pill($('lp'),'At capacity, overflowing to cloud','#b45309','#fef3c7');
 else pill($('lp'),'Handling all shoppers','#15803d','#dcfce7');
 $('cn').textContent=s.cloud_copies.length;
 $('chips').innerHTML=s.cloud_copies.map(h=>'<span class="chip">&hellip;'+h.slice(-5)+'</span>').join('');
 $('cw').textContent='';
 if(!s.cloud_configured)pill($('cp'),'Not configured','#64748b','#f1f5f9');
 else if(full&&s.cloud_ok===false){pill($('cp'),'Unreachable','#fff','#dc2626');$('cw').textContent='Store keeps selling locally; only the overflow is affected.';}
 else if(full)pill($('cp'),'Absorbing the overflow','#1d4ed8','#dbeafe');
 else pill($('cp'),'Standing by','#64748b','#f1f5f9');
 draw(s);
}
function draw(s){
 const c=$('cv'),d=devicePixelRatio||1,W=c.clientWidth,H=c.clientHeight;c.width=W*d;c.height=H*d;
 const x=c.getContext('2d');x.scale(d,d);x.clearRect(0,0,W,H);
 const p={l:36,r:10,t:10,b:20},w=W-p.l-p.r,h=H-p.t-p.b,n=s.series.length;
 const mx=Math.max(s.capacity*1.6,...s.series.map(v=>v[0]+v[1]+v[2]))*1.1||1;
 const X=i=>p.l+i*w/(n-1),Y=v=>p.t+h-v/mx*h;
 x.strokeStyle='#e2e8f0';x.fillStyle='#64748b';x.font='12px system-ui';
 for(let k=0;k<=4;k++){const v=mx*k/4;x.beginPath();x.moveTo(p.l,Y(v));x.lineTo(W-p.r,Y(v));x.stroke();x.fillText(Math.round(v),4,Y(v)+4);}
 const band=(lo,hi,col)=>{x.beginPath();s.series.forEach((v,i)=>{const yy=Y(hi(v));i?x.lineTo(X(i),yy):x.moveTo(X(i),yy);});
  for(let i=n-1;i>=0;i--)x.lineTo(X(i),Y(lo(s.series[i])));x.closePath();x.fillStyle=col;x.fill();};
 band(v=>0,v=>v[0],'#d97706');band(v=>v[0],v=>v[0]+v[1],'#2563eb');band(v=>v[0]+v[1],v=>v[0]+v[1]+v[2],'#dc2626');
 x.setLineDash([6,5]);x.strokeStyle='#0f172a';x.beginPath();x.moveTo(p.l,Y(s.capacity));x.lineTo(W-p.r,Y(s.capacity));x.stroke();x.setLineDash([]);
 x.fillStyle='#0f172a';x.fillText('Store server capacity',p.l+6,Y(s.capacity)-6);
}
async function tick(){try{render(await (await fetch('/api/stats')).json());}catch(e){}}
setInterval(tick,1000);tick();addEventListener('resize',tick);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def send(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/api/stats":
            return self.send(json.dumps(stats()).encode(), "application/json")
        if u.path in ("/api/rate", "/api/capacity"):
            try:
                n = max(0, min(100, int(q.get("n", ["0"])[0])))
            except ValueError:
                n = 0
            with lock:
                state["rate" if u.path == "/api/rate" else "capacity"] = n if u.path == "/api/rate" else max(1, n)
            return self.send(b"ok", "text/plain")
        if u.path == "/healthz":
            return self.send(b"ok", "text/plain")
        return self.send(DASHBOARD.encode(), "text/html; charset=utf-8")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    threading.Thread(target=generator, daemon=True).start()
    print(f"Front door on :{PORT}  local={LOCAL_URL}  cloud={CLOUD_URL or '(none)'}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
