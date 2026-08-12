#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "pillow",
#     "numpy",
# ]
# ///
"""从任意图片生成 boot splash logo(RGB565 LE raw + gzip,供 kernel.its 打包)。

用法:
    uv run mklogo.py logo.png                  # 生成所有屏幕的 logo 到 ../logo/
    uv run mklogo.py logo.png -p boe_035       # 只生成 boe_035(720x1280 屏)
    uv run mklogo.py logo.png -o /tmp/out      # 指定输出目录
    uv run mklogo.py logo.png --preview        # 顺便输出 PNG 预览

图片按等比缩放放进可视区,黑边 letterbox。改完记得重新跑 buildroot 的
make(post-image 会把 logo 打进 boot.itb),然后 DFU 刷 boot 分区。
"""

import argparse
import gzip
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# scanout = mixer/TCON 出的分辨率;visible = 面板实际可见区(在 scanout 里的偏移)
PANELS = {
    "boe_035": {"scanout": (720, 1280), "visible": (720, 1280), "offset": (0, 0)},
}


def fit_into(img: Image.Image, w: int, h: int) -> Image.Image:
    scale = min(w / img.width, h / img.height)
    nw, nh = max(1, round(img.width * scale)), max(1, round(img.height * scale))
    resized = img.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGB", (w, h), (0, 0, 0))
    canvas.paste(resized, ((w - nw) // 2, (h - nh) // 2))
    return canvas


def to_rgb565le(img: Image.Image) -> bytes:
    a = np.asarray(img.convert("RGB"), dtype=np.uint16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    px = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    return px.astype("<u2").tobytes()


def render_frame(src: Image.Image, panel: str) -> Image.Image:
    """把源图摆进该 panel 的 scanout 画布(splashtool.py 也走这里,别各写一份)。"""
    geo = PANELS[panel]
    sw, sh = geo["scanout"]
    vw, vh = geo["visible"]
    ox, oy = geo["offset"]

    frame = Image.new("RGB", (sw, sh), (0, 0, 0))
    frame.paste(fit_into(src, vw, vh), (ox, oy))
    return frame


def panel_for_raw_len(nbytes: int) -> str:
    """按 RGB565 raw 字节数反查 panel,用来认出 FIT 里已有 logo 是哪种屏。"""
    for name, geo in PANELS.items():
        sw, sh = geo["scanout"]
        if sw * sh * 2 == nbytes:
            return name
    raise ValueError(f"没有 panel 的 scanout 匹配 {nbytes} 字节的 RGB565 数据")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("image", type=Path)
    ap.add_argument("-p", "--panel", choices=[*PANELS, "all"], default="all")
    ap.add_argument("-o", "--outdir", type=Path,
                    default=Path(__file__).resolve().parent.parent / "logo")
    ap.add_argument("--preview", action="store_true",
                    help="同时输出 logo-<panel>.preview.png")
    args = ap.parse_args()

    src = Image.open(args.image)
    args.outdir.mkdir(parents=True, exist_ok=True)

    panels = PANELS if args.panel == "all" else {args.panel: PANELS[args.panel]}
    for name, geo in panels.items():
        sw, sh = geo["scanout"]
        vw, vh = geo["visible"]

        frame = render_frame(src, name)
        raw = to_rgb565le(frame)
        assert len(raw) == sw * sh * 2

        out = args.outdir / f"logo-{name}.rgb565.gz"
        out.write_bytes(gzip.compress(raw, 9))
        gz_size = out.stat().st_size
        print(f"{out}  scanout {sw}x{sh}, visible {vw}x{vh}, "
              f"{gz_size} bytes gz ({gz_size / len(raw) * 100:.1f}% of raw)",
              flush=True)

        # dtbs.itb 整个只有 1MiB 的 slot,而照片类图像截成 RGB565 后低位近似随机,
        # gzip 压不动 —— 一份 720x1280 就能顶掉整个 slot,构建会在 buildimage.sh
        # 的大小检查那里失败。早说一声比让人去猜 mkimage 报错好。
        if gz_size > len(raw) // 2:
            print("  警告: 几乎没压动。dtbs slot 只有 1 MiB, 这张图装不进去。\n"
                  "  换成纯色块/少细节的图, 或者把图缩小放在黑底中间。",
                  file=sys.stderr)

        if args.preview:
            frame.save(args.outdir / f"logo-{name}.preview.png")

    return 0


if __name__ == "__main__":
    sys.exit(main())
