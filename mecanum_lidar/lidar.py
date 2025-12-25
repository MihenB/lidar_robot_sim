from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Tuple

import numpy as np

try:
    import mujoco
except Exception:  # pragma: no cover - runtime import guard
    mujoco = None  # type: ignore


@dataclass
class CylinderObstacle:
    center_xy: Tuple[float, float]
    radius: float


def world_cylinders_from_model(model, data, exclude_body_ids: Iterable[int] = ()) -> List[CylinderObstacle]:
    """Extract vertical cylinders from a MuJoCo model as 2D obstacles.

    Only picks geoms of type cylinder aligned with world Z (default).
    """
    obstacles: List[CylinderObstacle] = []
    if mujoco is None:
        return obstacles

    # geom types are ints; cylinder type value is available via enum
    mjGEOM_CYLINDER = mujoco.mjtGeom.mjGEOM_CYLINDER

    for g in range(model.ngeom):
        if int(model.geom_type[g]) != int(mjGEOM_CYLINDER):
            continue
        b = int(model.geom_bodyid[g])
        if b in exclude_body_ids:
            continue
        # pose
        x, y = float(data.geom_xpos[g][0]), float(data.geom_xpos[g][1])
        radius = float(model.geom_size[g][0])
        obstacles.append(CylinderObstacle((x, y), radius))
    return obstacles


def ray_circle_intersection(origin: Tuple[float, float], direction: Tuple[float, float],
                             center: Tuple[float, float], radius: float) -> float | None:
    """Compute intersection distance t>=0 from origin along direction to circle.
    Returns None if no intersection.
    """
    ox, oy = origin
    dx, dy = direction
    cx, cy = center
    # Shift to circle frame
    fx, fy = ox - cx, oy - cy
    a = dx * dx + dy * dy
    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - radius * radius
    disc = b * b - 4 * a * c
    if disc < 0.0:
        return None
    sqrt_disc = math.sqrt(disc)
    t1 = (-b - sqrt_disc) / (2 * a)
    t2 = (-b + sqrt_disc) / (2 * a)
    # We want the smallest non-negative t
    ts = [t for t in (t1, t2) if t >= 0.0]
    if not ts:
        return None
    return min(ts)


def lidar_scan_xy(model, data, base_body_id: int, n_beams: int = 36,
                  max_range: float = 5.0, ignore_body_ids: Iterable[int] = ()) -> np.ndarray:
    """Compute a 2D lidar scan in the world XY plane using simple cylinder intersections.

    - base_body_id: MuJoCo body id whose XY position is the scan origin.
    - n_beams: number of beams over 360 degrees.
    - max_range: maximum range in meters.
    - ignore_body_ids: bodies to exclude from intersection (e.g., robot parts).
    Returns array length n_beams with distances in meters.
    """
    if mujoco is None:
        raise RuntimeError("mujoco module not available")

    origin_xy = (float(data.xpos[base_body_id][0]), float(data.xpos[base_body_id][1]))
    obstacles = world_cylinders_from_model(model, data, exclude_body_ids=set(ignore_body_ids))

    angles = np.linspace(0.0, 2.0 * math.pi, num=n_beams, endpoint=False)
    dists = np.full(n_beams, max_range, dtype=float)

    for i, th in enumerate(angles):
        dx, dy = math.cos(th), math.sin(th)
        best = max_range
        for obs in obstacles:
            t = ray_circle_intersection(origin_xy, (dx, dy), obs.center_xy, obs.radius)
            if t is not None and 0.0 <= t < best:
                best = t
        dists[i] = best
    return dists

