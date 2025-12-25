from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from typing import Tuple


INDEX_HTML = b"""
<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <title>Mecanum Web Joystick</title>
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <style>
    body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; padding: 16px; }
    .row { display: flex; gap: 16px; }
    .pad { background: #fafafa; border: 1px solid #bbb; border-radius: 8px; position: relative; touch-action: none; }
    #left { width: 240px; height: 240px; }
    #right { width: 240px; height: 120px; }
    .dot { width: 16px; height: 16px; border-radius: 50%; position: absolute; transform: translate(-50%, -50%); }
    #ldot { background: #3366ff; }
    #rdot { background: #ff6633; }
    .centerX { position: absolute; left: 50%; top: 0; bottom: 0; border-left: 1px dashed #ccc; }
    .centerY { position: absolute; top: 50%; left: 0; right: 0; border-top: 1px dashed #ccc; }
    .status { margin-top: 12px; color: #333; }
  </style>
</head>
<body>
  <h3 style=\"margin-top:0\">Mecanum Web Joystick</h3>
  <div class=\"row\">
    <div id=\"left\" class=\"pad\">
      <div class=\"centerX\"></div>
      <div class=\"centerY\"></div>
      <div id=\"ldot\" class=\"dot\"></div>
    </div>
  </div>
  <div style=\"margin-top:12px;\">
    <button id=\"stopbtn\" style=\"padding:6px 12px;\">Stop</button>
    <span class=\"status\" id=\"status\" style=\"margin-left:8px;\">Disconnected</span>
  </div>
  <script>
  const left = document.getElementById('left');
  const ldot = document.getElementById('ldot');
  const status = document.getElementById('status');
  const stopbtn = document.getElementById('stopbtn');

  let lx = 0, ly = 0;
  let sending = false;

  function clamp(x, a, b){ return Math.max(a, Math.min(b, x)); }

  function handlePad(ev, pad, horizontalOnly=false){
    const rect = pad.getBoundingClientRect();
    const x = (ev.touches? ev.touches[0].clientX : ev.clientX) - rect.left;
    const y = (ev.touches? ev.touches[0].clientY : ev.clientY) - rect.top;
    const nx = clamp((x - rect.width/2) / (rect.width/2), -1, 1);
    const ny = clamp((rect.height/2 - y) / (rect.height/2), -1, 1);
    if(pad === left){ lx = nx; ly = ny; }
    draw();
  }

  function draw(){
    // left dot
    const lrect = left.getBoundingClientRect();
    ldot.style.left = (lrect.width/2 + lx * lrect.width/2) + 'px';
    ldot.style.top  = (lrect.height/2 - ly * lrect.height/2) + 'px';
  }

  function startPad(pad, horizontalOnly=false){
    function down(ev){ ev.preventDefault(); handlePad(ev, pad, horizontalOnly); document.addEventListener('pointermove', move, {passive:false}); document.addEventListener('pointerup', up, {passive:false}); }
    function move(ev){ ev.preventDefault(); handlePad(ev, pad, horizontalOnly); }
    function up(ev){ ev.preventDefault(); document.removeEventListener('pointermove', move); document.removeEventListener('pointerup', up); lx=0; ly=0; draw(); }
    pad.addEventListener('pointerdown', down, {passive:false});
  }

  startPad(left, false);
  draw();

  stopbtn.addEventListener('click', (ev)=>{
    ev.preventDefault();
    lx = 0; ly = 0; draw();
    fetch('/set', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ lx, ly }) });
  });

  async function sendLoop(){
    while(true){
      try{
        const res = await fetch('/set', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ lx, ly }) });
        if(!res.ok) throw new Error('bad status');
        status.textContent = `Connected: lx=${lx.toFixed(2)} ly=${ly.toFixed(2)}`;
      }catch(e){
        status.textContent = 'Disconnected';
      }
      await new Promise(r=>setTimeout(r, 50));
    }
  }
  sendLoop();
  </script>
</body>
</html>
"""


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class WebJoystickServer(_ThreadingHTTPServer):
    def __init__(self, server_address, RequestHandlerClass, shared, limits):  # noqa: ANN001
        super().__init__(server_address, RequestHandlerClass)
        self.shared = shared
        self.limits = limits


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/" or self.path.startswith("/index"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(INDEX_HTML)))
            self.end_headers()
            self.wfile.write(INDEX_HTML)
        elif self.path == "/state":
            vx, vy, wz = self.server.shared.read()  # type: ignore[attr-defined]
            body = json.dumps({"vx": vx, "vy": vy, "wz": wz}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):  # noqa: N802
        if self.path == "/set":
            length = int(self.headers.get("Content-Length", 0))
            data = self.rfile.read(length) if length > 0 else b"{}"
            try:
                obj = json.loads(data.decode() or "{}")
            except Exception:
                obj = {}
            lx = float(obj.get("lx", 0.0))
            ly = float(obj.get("ly", 0.0))
            # Map to velocities
            vx = ly * self.server.limits.vx_max  # type: ignore[attr-defined]
            vy = lx * self.server.limits.vy_max  # type: ignore[attr-defined]
            # Single-pad control: no rotation
            self.server.shared.write(vx, vy, 0.0)  # type: ignore[attr-defined]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")
        else:
            self.send_error(404)

    def log_message(self, fmt, *args):  # silence noisy logs
        return


class Limits:
    def __init__(self, vx_max=0.6, vy_max=0.6, wz_max=2.5):
        self.vx_max = vx_max
        self.vy_max = vy_max
        self.wz_max = wz_max


def start_web_joystick(shared, host: str = "127.0.0.1", port: int = 8765, limits: Limits | None = None) -> tuple[WebJoystickServer, threading.Thread, str]:
    limits = limits or Limits()
    server = WebJoystickServer((host, port), _Handler, shared, limits)
    th = threading.Thread(target=server.serve_forever, name="web-joystick", daemon=True)
    th.start()
    url = f"http://{host}:{port}"
    return server, th, url
