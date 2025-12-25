from __future__ import annotations

import os
from pathlib import Path

from .control_web import serve as serve_web


def assets_path() -> Path:
    return Path(__file__).resolve().parent / "models" / "mecanum_lidar.xml"


def main() -> None:
    xml = str(assets_path())
    if not os.path.exists(xml):
        raise FileNotFoundError(f"MJCF model not found: {xml}")

    # Geometry values should reflect the current MJCF (wheel radius, half-length/width)
    serve_web(
        xml_path=xml,
        wheel_r=0.05,
        L=0.18,
        W=0.16,
        vmax=0.8,
        wmax=2.0,
        kp_speed=0.25,
        host="127.0.0.1",
        port=8765,
        show_viewer=True,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
