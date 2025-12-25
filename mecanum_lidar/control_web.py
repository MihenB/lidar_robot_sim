from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Tuple

import numpy as np

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse
    import uvicorn
except Exception as e:  # pragma: no cover - import guarded for environments without net packages
    FastAPI = None  # type: ignore
    WebSocket = None  # type: ignore
    WebSocketDisconnect = Exception  # type: ignore
    HTMLResponse = None  # type: ignore
    uvicorn = None  # type: ignore

import mujoco


HTML = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Mecanum Web Joystick</title>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; margin: 16px; }
    .row { display: flex; gap: 16px; flex-wrap: wrap; align-items: center; }
    .card { border: 1px solid #ddd; border-radius: 12px; padding: 12px; }
    #pad { width: 260px; height: 260px; touch-action: none; background: #f7f7f7; border-radius: 16px; position: relative; }
    #stick { width: 70px; height: 70px; border-radius: 999px; background: #111; opacity: 0.15; position: absolute; left: 95px; top: 95px; }
    .label { font-size: 13px; color: #444; }
    .big { font-size: 16px; }
    input[type="range"] { width: 260px; }
    button { border: 0; border-radius: 10px; padding: 10px 14px; cursor: pointer; }
    button.stop { background: #ff4d4d; color: white; }
    .kv { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 13px; }
  </style>
  </head>
  <body>
    <h2>Mecanum robot — web joystick</h2>

    <div class="row">
      <div class="card">
        <div class="label">Translation joystick (Y=forward, X=strafe)</div>
        <div id="pad">
          <div id="stick"></div>
        </div>
        <div style="margin-top:10px" class="kv">
          x: <span id="xv">0.00</span> &nbsp; y: <span id="yv">0.00</span>
        </div>
      </div>

      <div class="card">
        <div class="label">Rotation (yaw)</div>
        <input id="rot" type="range" min="-1" max="1" value="0" step="0.01"/>
        <div class="kv">rot: <span id="rv">0.00</span></div>

        <div style="height:10px"></div>
        <div class="label">Speed scale</div>
        <input id="spd" type="range" min="0.1" max="2.0" value="1.0" step="0.05"/>
        <div class="kv">scale: <span id="sv">1.00</span></div>

        <div style="height:12px"></div>
        <button class="stop" id="stop">STOP</button>

        <div style="height:12px"></div>
        <div class="label">Connection</div>
        <div class="kv" id="status">connecting...</div>
      </div>
    </div>

  <script>
  (() => {
    const pad = document.getElementById('pad');
    const stick = document.getElementById('stick');
    const xv = document.getElementById('xv');
    const yv = document.getElementById('yv');
    const rot = document.getElementById('rot');
    const rv = document.getElementById('rv');
    const spd = document.getElementById('spd');
    const sv = document.getElementById('sv');
    const stopBtn = document.getElementById('stop');
    const status = document.getElementById('status');

    let joyX = 0, joyY = 0;     // [-1..1]
    let rotX = 0;               // [-1..1]
    let scale = 1.0;            // [0.1..2.0]
    let activePointer = null;

    const W = 260, H = 260;
    const center = { x: W/2, y: H/2 };
    const maxR = 100;

    function setStick(x, y) {
      const sx = center.x + x - 35;
      const sy = center.y + y - 35;
      stick.style.left = `${sx}px`;
      stick.style.top  = `${sy}px`;
    }

    function clamp(v, a, b){ return Math.max(a, Math.min(b, v)); }

    function updateFromPointer(px, py) {
      const rect = pad.getBoundingClientRect();
      const x = (px - rect.left) - center.x;
      const y = (py - rect.top)  - center.y;
      const r = Math.hypot(x, y);
      const k = (r > maxR) ? (maxR / r) : 1.0;
      const cx = x * k;
      const cy = y * k;

      joyX = clamp(cx / maxR, -1, 1);    // +X right
      joyY = clamp(-cy / maxR, -1, 1);   // +Y forward

      xv.textContent = joyX.toFixed(2);
      yv.textContent = joyY.toFixed(2);
      setStick(cx, cy);
    }

    function resetStick() {
      joyX = 0; joyY = 0;
      xv.textContent = joyX.toFixed(2);
      yv.textContent = joyY.toFixed(2);
      setStick(0, 0);
    }

    pad.addEventListener('pointerdown', (e) => {
      pad.setPointerCapture(e.pointerId);
      activePointer = e.pointerId;
      updateFromPointer(e.clientX, e.clientY);
    });

    pad.addEventListener('pointermove', (e) => {
      if (activePointer !== e.pointerId) return;
      updateFromPointer(e.clientX, e.clientY);
    });

    pad.addEventListener('pointerup', (e) => {
      if (activePointer !== e.pointerId) return;
      activePointer = null;
      resetStick();
    });

    pad.addEventListener('pointercancel', (e) => {
      if (activePointer !== e.pointerId) return;
      activePointer = null;
      resetStick();
    });

    rot.addEventListener('input', () => {
      rotX = parseFloat(rot.value);
      rv.textContent = rotX.toFixed(2);
    });

    spd.addEventListener('input', () => {
      scale = parseFloat(spd.value);
      sv.textContent = scale.toFixed(2);
    });

    stopBtn.addEventListener('click', () => {
      resetStick();
      rot.value = "0";
      rotX = 0;
      rv.textContent = "0.00";
    });

    const proto = (location.protocol === "https:") ? "wss" : "ws";
    let ws = null;
    let ws_ok = false;
    try {
      ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => { ws_ok = true; status.textContent = "connected"; };
      ws.onclose = () => { ws_ok = false; status.textContent = "disconnected"; };
      ws.onerror = () => { ws_ok = false; status.textContent = "error"; };
    } catch (e) {
      ws_ok = false;
    }

    setInterval(() => {
      const payload = JSON.stringify({ x: joyX, y: joyY, rot: rotX, scale: scale });
      if (ws && ws.readyState === 1) {
        ws.send(payload);
      } else {
        fetch('/set', { method:'POST', headers:{'Content-Type':'application/json'}, body: payload })
          .then(_ => { status.textContent = "http"; })
          .catch(_ => { status.textContent = "offline"; });
      }
    }, 50);
  })();
  </script>
  </body>
  </html>
"""


@dataclass
class Command:
    x: float = 0.0     # strafe [-1..1]
    y: float = 0.0     # forward [-1..1]
    rot: float = 0.0   # yaw [-1..1]
    scale: float = 1.0 # speed scale


cmd = Command()
cmd_lock = threading.Lock()


def _mj_name2id(model, objtype, name: str) -> int:
    _id = mujoco.mj_name2id(model, objtype, name)
    if _id < 0:
        raise RuntimeError(f"Name not found: {name} (objtype={objtype})")
    return _id


def _run_sim(xml_path: str,
             wheel_r: float,
             L: float,
             W: float,
             vmax: float,
             wmax: float,
             kp_speed: float,
             show_viewer: bool) -> None:
    model = mujoco.MjModel.from_xml_path(xml_path)
    data = mujoco.MjData(model)

    joint_names = ["joint_fl", "joint_fr", "joint_rl", "joint_rr"]
    motor_names = ["motor_fl", "motor_fr", "motor_rl", "motor_rr"]

    joint_ids = [_mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, n) for n in joint_names]
    dof_ids = [int(model.jnt_dofadr[jid]) for jid in joint_ids]
    act_ids = [_mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, n) for n in motor_names]

    # ctrlrange
    umin, umax = -6.0, 6.0
    try:
        umin = float(model.actuator_ctrlrange[act_ids[0], 0])
        umax = float(model.actuator_ctrlrange[act_ids[0], 1])
    except Exception:
        pass

    # optional viewer
    v = None
    if show_viewer:
        try:
            from mujoco import viewer as mj_viewer
            v = mj_viewer.launch_passive(model, data)
        except Exception as e:
            print(f"[WARN] Cannot start mujoco.viewer: {e}; running headless")
            v = None

    mujoco.mj_resetData(model, data)
    mujoco.mj_forward(model, data)

    # Warmup without control to settle contacts
    for _ in range(200):
        for i in range(model.nu):
            data.ctrl[i] = 0.0
        mujoco.mj_step(model, data)

    dt = float(model.opt.timestep)
    t0 = time.perf_counter()

    # smoothing filters
    vx_f = 0.0
    vy_f = 0.0
    wz_f = 0.0
    tau = 0.25  # s

    while True:
        with cmd_lock:
            cx, cy, crot, cscale = cmd.x, cmd.y, cmd.rot, cmd.scale

        vx_cmd = cy * vmax * cscale
        vy_cmd = cx * vmax * cscale
        wz_cmd = crot * wmax * cscale

        # Low-pass filter commands
        dt = float(model.opt.timestep)
        alpha = dt / max(1e-6, tau + dt)
        vx_f = (1.0 - alpha) * vx_f + alpha * vx_cmd
        vy_f = (1.0 - alpha) * vy_f + alpha * vy_cmd
        wz_f = (1.0 - alpha) * wz_f + alpha * wz_cmd

        k = (L + W)
        w_fl = (vx_f - vy_f - k * wz_f) / wheel_r
        w_fr = (vx_f + vy_f + k * wz_f) / wheel_r
        w_rl = (vx_f + vy_f - k * wz_f) / wheel_r
        w_rr = (vx_f - vy_f + k * wz_f) / wheel_r
        w_des = np.array([w_fl, w_fr, w_rl, w_rr], dtype=float)

        w_meas = np.array([data.qvel[d] for d in dof_ids], dtype=float)
        u = kp_speed * (w_des - w_meas)
        u = np.clip(u, umin, umax)
        for i, aid in enumerate(act_ids):
            data.ctrl[aid] = float(u[i])

        mujoco.mj_step(model, data)

        if v is not None:
            try:
                v.sync()
            except Exception:
                v = None

        # real-time pacing
        elapsed = time.perf_counter() - t0
        sim_time = data.time
        if sim_time > elapsed:
            time.sleep(min(0.01, sim_time - elapsed))


def serve(xml_path: str,
          wheel_r: float = 0.05,
          L: float = 0.18,
          W: float = 0.16,
          vmax: float = 0.5,
          wmax: float = 1.2,
          kp_speed: float = 0.12,
          host: str = "127.0.0.1",
          port: int = 8765,
          show_viewer: bool = True) -> None:
    if FastAPI is None or uvicorn is None:
        raise RuntimeError("fastapi/uvicorn not available; please install dependencies")

    sim_thread = threading.Thread(
        target=_run_sim,
        kwargs=dict(
            xml_path=xml_path,
            wheel_r=wheel_r,
            L=L,
            W=W,
            vmax=vmax,
            wmax=wmax,
            kp_speed=kp_speed,
            show_viewer=show_viewer,
        ),
        daemon=True,
    )
    sim_thread.start()

    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def index():  # noqa: ANN001
        return HTMLResponse(HTML)

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):  # noqa: ANN001
        await ws.accept()
        try:
            while True:
                msg = await ws.receive_text()
                try:
                    d = json.loads(msg)
                    x = float(d.get("x", 0.0))
                    y = float(d.get("y", 0.0))
                    rot = float(d.get("rot", 0.0))
                    scale = float(d.get("scale", 1.0))
                except Exception:
                    continue
                x = max(-1.0, min(1.0, x))
                y = max(-1.0, min(1.0, y))
                rot = max(-1.0, min(1.0, rot))
                scale = max(0.1, min(2.0, scale))
                with cmd_lock:
                    cmd.x = x
                    cmd.y = y
                    cmd.rot = rot
                    cmd.scale = scale
        except WebSocketDisconnect:
            pass
        finally:
            with cmd_lock:
                cmd.x = cmd.y = cmd.rot = 0.0
                cmd.scale = 1.0

    @app.post("/set")
    async def set_controls(payload: dict):  # noqa: ANN001
        try:
            x = float(payload.get("x", 0.0))
            y = float(payload.get("y", 0.0))
            rot = float(payload.get("rot", 0.0))
            scale = float(payload.get("scale", 1.0))
        except Exception:
            return {"ok": False}
        x = max(-1.0, min(1.0, x))
        y = max(-1.0, min(1.0, y))
        rot = max(-1.0, min(1.0, rot))
        scale = max(0.1, min(2.0, scale))
        with cmd_lock:
            cmd.x = x
            cmd.y = y
            cmd.rot = rot
            cmd.scale = scale
        return {"ok": True}

    uvicorn.run(app, host=host, port=port, log_level="info")
