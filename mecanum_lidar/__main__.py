from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys


def entry() -> None:
    # On macOS, MuJoCo viewer requires running under `mjpython`.
    if platform.system() == "Darwin":
        mj = shutil.which("mjpython")
        if mj:
            # Re-exec under mjpython, preserving args; run module form to hit sim.main
            cmd = [mj, "-m", "mecanum_lidar.sim", *sys.argv[1:]]
            raise SystemExit(subprocess.call(cmd))
        else:
            print(
                "MuJoCo viewer on macOS must run under 'mjpython', but it was not found in PATH.\n"
                "Install the 'mujoco' Python package in this environment, or run:\n"
                "  uv run mjpython -m mecanum_lidar.sim\n",
                file=sys.stderr,
            )
    # Non-macOS, just run directly
    from .sim import main

    main()


if __name__ == "__main__":  # pragma: no cover
    entry()

