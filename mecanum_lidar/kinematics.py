from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MecanumGeometry:
    wheel_radius: float  # wheel radius (m)
    half_length: float   # half of robot length (x half-extent, m)
    half_width: float    # half of robot width (y half-extent, m)

    @property
    def l_plus_w(self) -> float:
        return self.half_length + self.half_width


def body_to_wheel_speeds(vx: float, vy: float, wz: float, geom: MecanumGeometry) -> tuple[float, float, float, float]:
    """Compute wheel angular velocities (rad/s) for a mecanum base.

    Mapping:
      - fl: front-left
      - fr: front-right
      - rl: rear-left
      - rr: rear-right
    Using convention where +x forward, +y to the left, +z up, and wz CCW about +z.
    """
    r = geom.wheel_radius
    LpW = geom.l_plus_w
    # Standard inverse kinematics for mecanum wheels
    w_fl = (1.0 / r) * (vx - vy - LpW * wz)
    w_fr = (1.0 / r) * (vx + vy + LpW * wz)
    w_rl = (1.0 / r) * (vx + vy - LpW * wz)
    w_rr = (1.0 / r) * (vx - vy + LpW * wz)
    return w_fl, w_fr, w_rl, w_rr


def clamp(x: float, lo: float, hi: float) -> float:
    return hi if x > hi else lo if x < lo else x

