from __future__ import annotations

import threading
from dataclasses import dataclass

try:
    import tkinter as tk
except Exception as e:  # pragma: no cover - runtime env guard
    tk = None  # type: ignore


@dataclass
class Limits:
    vx_max: float = 1.5
    vy_max: float = 1.5
    wz_max: float = 2.5


class SharedDesired:
    def __init__(self) -> None:
        self._vx = 0.0
        self._vy = 0.0
        self._wz = 0.0
        self._lock = threading.Lock()

    def read(self) -> tuple[float, float, float]:
        with self._lock:
            return self._vx, self._vy, self._wz

    def write(self, vx: float, vy: float, wz: float) -> None:
        with self._lock:
            self._vx, self._vy, self._wz = vx, vy, wz

    def stop(self) -> None:
        self.write(0.0, 0.0, 0.0)


class TkJoystick:
    """Two-pad joystick in a Tkinter window.

    - Left pad controls Vx (vertical) and Vy (horizontal)
    - Right pad controls Wz (horizontal)
    """

    def __init__(self, shared: SharedDesired, stop_event: threading.Event, limits: Limits | None = None) -> None:
        if tk is None:
            raise RuntimeError("tkinter is not available in this Python")
        self.shared = shared
        self.stop_event = stop_event
        self.limits = limits or Limits()

        self.root = tk.Tk()
        self.root.title("Mecanum Joystick")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.pad_size = 220
        self.margin = 16

        # Layout: Left and right frames
        container = tk.Frame(self.root)
        container.pack(padx=10, pady=10)

        left_frame = tk.Frame(container)
        right_frame = tk.Frame(container)
        left_frame.grid(row=0, column=0, padx=8)
        right_frame.grid(row=0, column=1, padx=8)

        self.left = tk.Canvas(left_frame, width=self.pad_size, height=self.pad_size, bg="#fafafa", highlightthickness=1, highlightbackground="#bbb")
        self.right = tk.Canvas(right_frame, width=self.pad_size, height=self.pad_size/2, bg="#fafafa", highlightthickness=1, highlightbackground="#bbb")
        self.left.pack()
        self.right.pack()

        self.label = tk.Label(self.root, text="Vx=0.00 Vy=0.00 Wz=0.00")
        self.label.pack(pady=(6, 0))

        # Draw guides
        s = self.pad_size
        self.left.create_line(s/2, 0, s/2, s, dash=(2,2), fill="#cccccc")
        self.left.create_line(0, s/2, s, s/2, dash=(2,2), fill="#cccccc")
        rs = self.pad_size/2
        self.right.create_line(rs/2, 0, rs/2, rs, dash=(2,2), fill="#cccccc")

        # Active markers
        self.left_dot = self.left.create_oval(s/2-6, s/2-6, s/2+6, s/2+6, fill="#3366ff", outline="")
        self.right_dot = self.right.create_oval(rs/2-6, rs/2-6, rs/2+6, rs/2+6, fill="#ff6633", outline="")

        # Bind events
        for ev in ("<ButtonPress-1>", "<B1-Motion>"):
            self.left.bind(ev, self._on_left_drag)
        self.left.bind("<ButtonRelease-1>", self._on_left_release)

        for ev in ("<ButtonPress-1>", "<B1-Motion>"):
            self.right.bind(ev, self._on_right_drag)
        self.right.bind("<ButtonRelease-1>", self._on_right_release)

        self._update_label_task()

    def _on_close(self):
        self.shared.stop()
        self.stop_event.set()
        self.root.destroy()

    def _update_label_task(self):
        vx, vy, wz = self.shared.read()
        self.label.config(text=f"Vx={vx:+.2f}  Vy={vy:+.2f}  Wz={wz:+.2f}")
        if not self.stop_event.is_set():
            self.root.after(50, self._update_label_task)

    def _on_left_drag(self, event):
        s = self.pad_size
        x = max(0, min(s, event.x))
        y = max(0, min(s, event.y))
        self.left.coords(self.left_dot, x-6, y-6, x+6, y+6)
        nx = (x - s/2) / (s/2)
        ny = (s/2 - y) / (s/2)
        vx = ny * self.limits.vx_max
        vy = nx * self.limits.vy_max
        _, _, wz = self.shared.read()
        self.shared.write(vx, vy, wz)

    def _on_left_release(self, _event):
        s = self.pad_size
        self.left.coords(self.left_dot, s/2-6, s/2-6, s/2+6, s/2+6)
        _, _, wz = self.shared.read()
        self.shared.write(0.0, 0.0, wz)

    def _on_right_drag(self, event):
        rs = self.pad_size/2
        x = max(0, min(rs, event.x))
        y = rs/2  # lock vertical
        self.right.coords(self.right_dot, x-6, y-6, x+6, y+6)
        nx = (x - rs/2) / (rs/2)
        vx, vy, _ = self.shared.read()
        self.shared.write(vx, vy, nx * self.limits.wz_max)

    def _on_right_release(self, _event):
        rs = self.pad_size/2
        self.right.coords(self.right_dot, rs/2-6, rs/2-6, rs/2+6, rs/2+6)
        vx, vy, _ = self.shared.read()
        self.shared.write(vx, vy, 0.0)

    def run(self) -> None:
        # Blocking mainloop; call from main thread
        self.root.mainloop()

