#!/usr/bin/env python3
"""兼容旧 USB 入口；实现位于 flasher/flash.py，无线升级使用 flasher/ota.py。"""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parent / "flasher/flash.py"), run_name="__main__")
