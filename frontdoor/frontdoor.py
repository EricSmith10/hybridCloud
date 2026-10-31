"""Front door: cloud-bursting demo.

Shoppers go to the on-prem server first. In "hybrid" mode, when it's busy
the overflow goes to the public cloud. In "onprem" mode everything waits for
the on-prem server, so queues and page-load times grow and some shoppers
give up. A live dashboard shows it all, and /shop lets a real person browse
through the same routing.

The on-prem server's capacity is simulated (each shopper occupies it for a
short service time); every visit is a real request and every time shown is
measured.

Environment variables:
  LOCAL_URL       on-prem store app, e.g. http://localhost:8090
  CLOUD_URL       OpenShift route, e.g. https://hybrid-cloud-git-....openshiftapps.com
  LOCAL_CAPACITY  shoppers/sec the on-prem server can handle (default 10)
  LOCAL_LABEL     name shown for on-prem (default: Your data centre)
  CLOUD_LABEL     name shown for cloud (default: Red Hat OpenShift)
  PORT            dashboard port (default 8095)
Standard library only.
"""
import json
import os
import threading
import time
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

LOCAL_URL = os.environ.get("LOCAL_URL", "http://localhost:8090").rstrip("/")
CLOUD_URL = os.environ.get("CLOUD_URL", "").rstrip("/")
LOCAL_LABEL = os.environ.get("LOCAL_LABEL", "Your data centre")
CLOUD_LABEL = os.environ.get("CLOUD_LABEL", "Red Hat OpenShift")
PORT = int(os.environ.get("PORT", "8095"))
HISTORY = 60
SLOTS = 2          # parallel shoppers the on-prem server serves at once
GIVE_UP = 5.0      # seconds a shopper waits before abandoning
MAX_PENDING = 400

lock = threading.Lock()
state = {"rate": 0, "capacity": int(os.environ.get("LOCAL_CAPACITY", "10")),
         "mode": "hybrid", "pending": 0}
buckets = {}       # second -> counters
cloud_hosts = {}   # pod name -> last seen
feed = deque(maxlen=12)
info = {"local_host": None, "cloud_ok": None}
pool = ThreadPoolExecutor(max_workers=300)

local_cv = threading.Condition()
local = {"busy": 0, "waiting": 0}


def service_time():
    return SLOTS / max(1, state["capacity"])


def acquire_local(timeout):
    end = time.time() + timeout
    with local_cv:
        if local["busy"] >= SLOTS and timeout <= 0:
            return False
        local["waiting"] += 1
        try:
            while local["busy"] >= SLOTS:
                remaining = end - time.time()
                if remaining <= 0:
                    return False
                local_cv.wait(remaining)
            local["busy"] += 1
            return True
        finally:
            local["waiting"] -= 1


def release_local():
    with local_cv:
        local["busy"] -= 1
        local_cv.notify()


def bucket(sec):
    b = buckets.get(sec)
    if b is None:
        b = buckets[sec] = {"local": 0, "cloud": 0, "err": 0, "abandoned": 0,
                            "local_ms": 0.0, "cloud_ms": 0.0}
        for k in [k for k in buckets if k < sec - HISTORY - 5]:
            del buckets[k]
    return b


def record(target, ok, host, ms, who):
    sec = int(time.time())
    with lock:
        b = bucket(sec)
        if target == "abandoned":
            b["abandoned"] += 1
        elif ok:
            b[target] += 1
            b[target + "_ms"] += ms
            if target == "cloud":
                cloud_hosts[host] = time.time()
                info["cloud_ok"] = True
            else:
                info["local_host"] = host
        else:
            b["err"] += 1
            if target == "cloud":
                info["cloud_ok"] = False
        feed.appendleft({"t": time.strftime("%H:%M:%S"), "to": target, "ok": ok,
                         "host": host or "", "ms": round(ms), "who": who})


def visit(path="/api/info", who="sim"):
    """Route one shopper. Returns (target, ok, body)."""
    t0 = time.time()
    if state["mode"] == "hybrid" and CLOUD_URL:
        target = "local" if acquire_local(0) else "cloud"
    else:
        target = "local" if acquire_local(GIVE_UP) else None
    if target is None:
        record("abandoned", False, None, (time.time() - t0) * 1000, who)
        return "abandoned", False, None
    served = time.time()
    ok, body, host = False, None, None
    try:
        url = (LOCAL_URL if target == "local" else CLOUD_URL) + path
        with urllib.request.urlopen(url, timeout=4) as r:
            body = r.read()
        ok = True
        if path.startswith("/api/info"):
            host = json.loads(body).get("host", "?")
        else:
            host = "page"
    except Exception:
        pass
    finally:
        if target == "local":
            rest = service_time() - (time.time() - served)
            if rest > 0:
                time.sleep(rest)
            release_local()
    if host == "page" and target == "cloud":
        host = None  # don't add page views to the copy list
    record(target, ok, host, (time.time() - t0) * 1000, who)
    return target, ok, body


def sim_shopper():
    try:
        visit()
    finally:
        with lock:
            state["pending"] -= 1


def submit():
    with lock:
        if state["pending"] >= MAX_PENDING:
            bucket(int(time.time()))["abandoned"] += 1
            return
        state["pending"] += 1
    pool.submit(sim_shopper)


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
        rows = [buckets.get(s, {}) for s in range(now - HISTORY, now)]
        series = [[r.get("local", 0), r.get("cloud", 0), r.get("err", 0) + r.get("abandoned", 0)]
                  for r in rows]
        recent = rows[-3:]

        def rps(k):
            return round(sum(r.get(k, 0) for r in recent) / 3, 1)

        def avg_ms(k):
            n = sum(r.get(k, 0) for r in recent)
            return round(sum(r.get(k + "_ms", 0) for r in recent) / n) if n else None

        t = time.time()
        return {
            "rate": state["rate"], "capacity": state["capacity"], "mode": state["mode"],
            "local_rps": rps("local"), "cloud_rps": rps("cloud"),
            "err_rps": rps("err"), "abandoned_rps": rps("abandoned"),
            "local_ms": avg_ms("local"), "cloud_ms": avg_ms("cloud"),
            "queue": local["waiting"], "series": series, "feed": list(feed),
            "cloud_copies": sorted(h for h, seen in cloud_hosts.items() if t - seen < 5),
            "cloud_ok": info["cloud_ok"], "cloud_configured": bool(CLOUD_URL),
            "local_label": LOCAL_LABEL, "cloud_label": CLOUD_LABEL,
        }


BUSY_PAGE = b"""<!doctype html><html><head><meta charset="utf-8"><title>Site busy</title>
<style>body{font-family:system-ui,sans-serif;display:grid;place-items:center;height:100vh;margin:0;background:#fef2f2;color:#7f1d1d;text-align:center}
h1{font-size:40px;margin:0 0 10px}</style></head><body><div><h1>Sorry, we're experiencing high demand</h1>
<p style="font-size:20px">Please try again later. (This shopper waited 5 seconds and gave up.)</p></div></body></html>"""

DASHBOARD = r"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Front Door</title>
<style>
:root{--amber:#d97706;--blue:#2563eb;--red:#dc2626;--green:#15803d;--ink:#0f172a;--mut:#64748b;--line:#e2e8f0}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,sans-serif;background:#f8fafc;color:var(--ink)}
.wrap{max-width:1240px;margin:0 auto;padding:24px}
h1{margin:0;font-size:28px}.sub{color:var(--mut);margin:6px 0 18px;font-size:16px}
.row{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px}
.lbl{font-size:13px;letter-spacing:.1em;text-transform:uppercase;color:var(--mut);margin-right:4px;min-width:84px}
button,a.btn{font:inherit;font-size:15px;padding:9px 14px;border-radius:10px;border:1px solid var(--line);background:#fff;cursor:pointer;color:var(--ink);text-decoration:none}
button.on{background:var(--ink);color:#fff;border-color:var(--ink)}
a.btn{background:#16a34a;color:#fff;border-color:#16a34a;font-weight:600}
.arr{margin-left:auto;font-size:16px;color:var(--mut)}.arr b{color:var(--ink);font-size:22px}
.cards{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:6px}
.card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:20px;border-top:6px solid}
.card.l{border-top-color:var(--amber)}.card.c{border-top-color:var(--blue)}
.kind{font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:var(--mut)}
.title{font-size:21px;font-weight:700;margin:4px 0 12px}
.stats{display:flex;gap:28px;flex-wrap:wrap}.big{font-size:44px;font-weight:800;line-height:1}
.cap{font-size:13px;color:var(--mut);margin-top:4px}
.gauge{height:14px;background:#f1f5f9;border-radius:99px;margin:14px 0 6px;overflow:hidden}
.gauge div{height:100%;background:var(--amber);width:0;transition:width .5s}
.pill{display:inline-block;padding:5px 12px;border-radius:99px;font-size:14px;font-weight:600;margin-top:10px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;min-height:28px}
.chip{background:#dbeafe;color:var(--blue);padding:4px 10px;border-radius:8px;font-size:13px;font-family:ui-monospace,monospace}
.lower{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-top:16px}
.panel{background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px}
.legend{display:flex;flex-wrap:wrap;gap:16px;font-size:13px;color:var(--mut);margin-bottom:8px}
.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px}
canvas{width:100%;height:230px;display:block}
.feed{font-family:ui-monospace,monospace;font-size:13px;line-height:1.75}
.feed div{display:flex;gap:8px;white-space:nowrap;overflow:hidden}.feed .you{font-weight:700}
@media(max-width:860px){.cards,.lower{grid-template-columns:1fr}.arr{margin-left:0}}
</style></head><body><div class="wrap">
<h1>Front Door &middot; Hybrid traffic routing</h1>
<div class="sub">Every shopper is sent to your own servers first. When they're full, the overflow goes to the public cloud automatically.</div>
<div class="row"><span class="lbl">Shoppers</span>
 <button data-r="4">Quiet day</button><button data-r="10">Busy weekend</button>
 <button data-r="40">Black Friday</button><button data-r="0">Stop</button>
 <div class="arr">Arriving: <b id="rate">0</b> / sec</div></div>
<div class="row"><span class="lbl">Setup</span>
 <button data-m="hybrid">Hybrid cloud</button><button data-m="onprem"><span id="lname1">Data centre</span> only</button>
 <a class="btn" href="/shop" target="_blank">Open the store as a shopper &#8599;</a></div>
<div class="cards">
 <div class="card l"><div class="kind">&#127970; On-premises</div><div class="title" id="lname">Your data centre</div>
  <div class="stats"><div><div class="big" id="lr">0</div><div class="cap">shoppers / sec</div></div>
   <div><div class="big" id="lms">&ndash;</div><div class="cap">page load time</div></div>
   <div><div class="big" id="q">0</div><div class="cap">waiting in line</div></div></div>
  <div class="gauge"><div id="g"></div></div>
  <div class="cap">Capacity: <span id="cap">0</span> shoppers / sec</div>
  <span class="pill" id="lp"></span></div>
 <div class="card c"><div class="kind">&#9729;&#65039; Public cloud</div><div class="title" id="cname">Red Hat OpenShift</div>
  <div class="stats"><div><div class="big" id="cr">0</div><div class="cap">shoppers / sec</div></div>
   <div><div class="big" id="cms">&ndash;</div><div class="cap">page load time</div></div>
   <div><div class="big" id="cn">0</div><div class="cap">copies answering</div></div></div>
  <div class="chips" id="chips"></div>
  <span class="pill" id="cp"></span></div>
</div>
<div class="lower">
 <div class="panel"><div class="legend"><span><i style="background:var(--amber)"></i>On-premises</span>
  <span><i style="background:var(--blue)"></i>Public cloud</span><span><i style="background:var(--red)"></i>Lost shoppers</span>
  <span style="margin-left:auto">Last 60 seconds</span></div><canvas id="cv"></canvas></div>
 <div class="panel"><div class="legend"><span>Live shopper feed</span><span style="margin-left:auto">&#9733; = you</span></div><div class="feed" id="feed"></div></div>
</div></div>
<script>
const $=id=>document.getElementById(id);
const pill=(el,txt,fg,bg)=>{el.textContent=txt;el.style.color=fg;el.style.background=bg;};
const sec=ms=>ms==null?'–':(ms/1000).toFixed(ms<10000?2:1)+'s';
document.querySelectorAll('button[data-r]').forEach(b=>b.onclick=()=>fetch('/api/rate?n='+b.dataset.r).then(tick));
document.querySelectorAll('button[data-m]').forEach(b=>b.onclick=()=>fetch('/api/mode?m='+b.dataset.m).then(tick));
function render(s){
 $('lname').textContent=s.local_label;{const t=s.local_label.replace(/^Your /i,'');$('lname1').textContent=t.charAt(0).toUpperCase()+t.slice(1);}$('cname').textContent=s.cloud_label;
 $('rate').textContent=s.rate;$('lr').textContent=s.local_rps;$('cr').textContent=s.cloud_rps;$('cap').textContent=s.capacity;
 $('q').textContent=s.queue;$('lms').textContent=sec(s.local_ms);$('cms').textContent=sec(s.cloud_ms);
 $('lms').style.color=s.local_ms>1000?'var(--red)':'';$('q').style.color=s.queue>0?'var(--red)':'';
 document.querySelectorAll('button[data-r]').forEach(b=>b.classList.toggle('on',+b.dataset.r===s.rate));
 document.querySelectorAll('button[data-m]').forEach(b=>b.classList.toggle('on',b.dataset.m===s.mode));
 $('g').style.width=Math.min(100,s.local_rps/s.capacity*100)+'%';
 const lost=s.abandoned_rps+s.err_rps, full=s.rate>s.capacity, hybrid=s.mode==='hybrid';
 if(s.rate===0)pill($('lp'),'Idle','#64748b','#f1f5f9');
 else if(s.abandoned_rps>0)pill($('lp'),'Overloaded: '+s.abandoned_rps+' shoppers/sec giving up','#fff','#dc2626');
 else if(s.queue>0)pill($('lp'),'Overloaded: shoppers are waiting','#b91c1c','#fee2e2');
 else if(full&&hybrid)pill($('lp'),'At capacity, overflowing to cloud','#b45309','#fef3c7');
 else pill($('lp'),'Handling all shoppers','#15803d','#dcfce7');
 $('cn').textContent=s.cloud_copies.length;
 $('chips').innerHTML=s.cloud_copies.map(h=>'<span class="chip">&hellip;'+h.slice(-5)+'</span>').join('');
 if(!s.cloud_configured)pill($('cp'),'Not configured','#64748b','#f1f5f9');
 else if(!hybrid)pill($('cp'),'Not connected','#64748b','#f1f5f9');
 else if(s.cloud_ok===false&&s.err_rps>0)pill($('cp'),'Cloud unavailable: data centre keeps serving','#fff','#dc2626');
 else if(s.cloud_rps>0)pill($('cp'),'Absorbing the overflow','#1d4ed8','#dbeafe');
 else pill($('cp'),'Standing by','#64748b','#f1f5f9');
 $('feed').innerHTML=s.feed.map(f=>{
  const col=f.to==='local'?'var(--amber)':f.to==='cloud'?'var(--blue)':'var(--red)';
  const where=f.to==='local'?'On-prem':f.to==='cloud'?'Cloud'+(f.host?' …'+f.host.slice(-5):''):'Gave up';
  return '<div class="'+(f.who==='you'?'you':'')+'"><span style="color:var(--mut)">'+f.t+'</span>'+
   (f.who==='you'?'★':'&nbsp;')+'<span style="color:'+col+'">'+(f.ok||f.to==='abandoned'?where:where+' (failed)')+
   '</span><span style="margin-left:auto">'+sec(f.ms)+'</span></div>';}).join('');
 draw(s);
}
function draw(s){
 const c=$('cv'),d=devicePixelRatio||1,W=c.clientWidth,H=c.clientHeight;c.width=W*d;c.height=H*d;
 const x=c.getContext('2d');x.scale(d,d);x.clearRect(0,0,W,H);
 const p={l:36,r:10,t:10,b:12},w=W-p.l-p.r,h=H-p.t-p.b,n=s.series.length;
 const mx=Math.max(s.capacity*1.6,...s.series.map(v=>v[0]+v[1]+v[2]))*1.1||1;
 const X=i=>p.l+i*w/(n-1),Y=v=>p.t+h-v/mx*h;
 x.strokeStyle='#e2e8f0';x.fillStyle='#64748b';x.font='12px system-ui';
 for(let k=0;k<=4;k++){const v=mx*k/4;x.beginPath();x.moveTo(p.l,Y(v));x.lineTo(W-p.r,Y(v));x.stroke();x.fillText(Math.round(v),4,Y(v)+4);}
 const band=(lo,hi,col)=>{x.beginPath();s.series.forEach((v,i)=>{const yy=Y(hi(v));i?x.lineTo(X(i),yy):x.moveTo(X(i),yy);});
  for(let i=n-1;i>=0;i--)x.lineTo(X(i),Y(lo(s.series[i])));x.closePath();x.fillStyle=col;x.fill();};
 band(v=>0,v=>v[0],'#d97706');band(v=>v[0],v=>v[0]+v[1],'#2563eb');band(v=>v[0]+v[1],v=>v[0]+v[1]+v[2],'#dc2626');
 x.setLineDash([6,5]);x.strokeStyle='#0f172a';x.beginPath();x.moveTo(p.l,Y(s.capacity));x.lineTo(W-p.r,Y(s.capacity));x.stroke();x.setLineDash([]);
 x.fillStyle='#0f172a';x.fillText('On-premises capacity',p.l+6,Y(s.capacity)-6);
}
async function tick(){try{render(await (await fetch('/api/stats')).json());}catch(e){}}
setInterval(tick,1000);tick();addEventListener('resize',tick);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def send(self, body, ctype, code=200):
        self.send_response(code)
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
                if u.path == "/api/rate":
                    state["rate"] = n
                else:
                    state["capacity"] = max(1, n)
            return self.send(b"ok", "text/plain")
        if u.path == "/api/mode":
            m = q.get("m", ["hybrid"])[0]
            state["mode"] = "onprem" if m == "onprem" else "hybrid"
            return self.send(b"ok", "text/plain")
        if u.path == "/shop":
            target, ok, body = visit("/", who="you")
            if target == "abandoned":
                return self.send(BUSY_PAGE, "text/html; charset=utf-8", 503)
            if not ok:
                return self.send(b"Store unavailable", "text/plain", 502)
            return self.send(body, "text/html; charset=utf-8")
        if u.path == "/healthz":
            return self.send(b"ok", "text/plain")
        return self.send(DASHBOARD.encode(), "text/html; charset=utf-8")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    threading.Thread(target=generator, daemon=True).start()
    print(f"Front door on :{PORT}  local={LOCAL_URL}  cloud={CLOUD_URL or '(none)'}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
