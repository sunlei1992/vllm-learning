#!/usr/bin/env python3
"""Plot the P/D dry-run trend from tmp/simlogs/pd_bench/k8_*.json (Pillow only)."""

import glob
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

def _repo_root() -> str:
    root = os.environ.get("VLLM_LAB_ROOT") or os.path.dirname(os.path.abspath(__file__))
    while root != "/" and not os.path.exists(os.path.join(root, "AGENTS.md")):
        root = os.path.dirname(root)
    return root


ROOT = _repo_root()
RESULT_DIR = os.environ.get("RESULT_DIR") or os.path.join(
    ROOT, "tmp", "simlogs", "pd_bench"
)
OUT = os.environ.get("OUT") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "pd_trend.png"
)
FONT = next(
    (
        f
        for f in (
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        )
        if os.path.exists(f)
    ),
    None,
)
if FONT is None:
    raise SystemExit("no usable TTF font found")

W, H = 1080, 420
BG = (255, 255, 255)
FG = (32, 32, 32)
GRID = (226, 226, 226)
MEAN = (31, 119, 180)
P99 = (214, 39, 40)


def load_latest(prefix: str) -> dict:
    files = sorted(
        glob.glob(os.path.join(RESULT_DIR, f"{prefix}-*.json")),
        key=os.path.getmtime,
    )
    if not files:
        raise SystemExit(f"no result for {prefix}")
    with open(files[-1]) as f:
        return json.load(f)


def panel(draw, x0, y0, w, h, title, xs, labels, series, ylabel, ymax=None):
    """series: list of (name, color, [(x, y), ...])"""
    fs = ImageFont.truetype(FONT, 13)
    fsb = ImageFont.truetype(FONT, 15)
    left, right, top, bottom = x0 + 46, x0 + w - 30, y0 + 34, y0 + h - 40

    draw.text((x0, y0 + 6), title, font=fsb, fill=FG)

    ys = [y for _, _, pts in series for _, y in pts]
    hi = ymax if ymax else max(ys) * 1.15
    hi = max(hi, 1e-9)

    def sx(x):
        if len(xs) == 1:
            return (left + right) / 2
        return left + (x - xs[0]) / (xs[-1] - xs[0]) * (right - left)

    def sy(y):
        return bottom - (y / hi) * (bottom - top)

    # grid + y ticks
    for i in range(5):
        y = top + i * (bottom - top) / 4
        draw.line([(left, y), (right, y)], fill=GRID)
        draw.text((x0 + 6, y - 7), f"{hi * (4 - i) / 4:.0f}", font=fs, fill=(110, 110, 110))
    draw.line([(left, top), (left, bottom)], fill=(150, 150, 150))
    draw.line([(left, bottom), (right, bottom)], fill=(150, 150, 150))

    # x ticks
    for x, lab in zip(xs, labels):
        draw.text((sx(x) - 8, bottom + 6), lab, font=fs, fill=(80, 80, 80))

    for name, color, pts in series:
        pts = sorted(pts)
        draw.line([(sx(x), sy(y)) for x, y in pts], fill=color, width=2)
        for x, y in pts:
            draw.ellipse([sx(x) - 4, sy(y) - 4, sx(x) + 4, sy(y) + 4], fill=color)
            lab = f"{y:.0f}"
            if x == max(xs):
                tw = draw.textlength(lab, font=fs)
                draw.text((sx(x) - 8 - tw, sy(y) - 16), lab, font=fs, fill=color)
            else:
                draw.text((sx(x) + 7, sy(y) - 16), lab, font=fs, fill=color)

    # legend
    lx = right - 120
    for i, (name, color, _) in enumerate(series):
        draw.line([(lx, top + 8 + i * 16), (lx + 16, top + 8 + i * 16)], fill=color, width=2)
        draw.text((lx + 20, top + 1 + i * 16), name, font=fs, fill=FG)


def main() -> None:
    d = {
        "1P1D": load_latest("k8_1p1d_25"),
        "2P1D": load_latest("k8_2p1d_25"),
        "4P1D": load_latest("k8_4p1d_25"),
        "1P2D": load_latest("k8_1p2d_25"),
        "2P2D": load_latest("k8_2p2d_25"),
        "2P1D@10": load_latest("k8_2p1d_10"),
        "2P1D@100": load_latest("k8_2p1d_100"),
    }

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    fs = ImageFont.truetype(FONT, 13)
    fsb = ImageFont.truetype(FONT, 15)

    pw = (W - 24) // 3
    panel(
        draw, 12, 10, pw, 330,
        "A. TTFT (ms) vs #prefill  (D=1, 25GB/s)",
        [1, 2, 4], ["1P", "2P", "4P"],
        [
            ("mean", MEAN, [(1, d["1P1D"]["mean_ttft_ms"]), (2, d["2P1D"]["mean_ttft_ms"]), (4, d["4P1D"]["mean_ttft_ms"])]),
            ("p99", P99, [(1, d["1P1D"]["p99_ttft_ms"]), (2, d["2P1D"]["p99_ttft_ms"]), (4, d["4P1D"]["p99_ttft_ms"])]),
        ],
        "TTFT (ms)",
    )
    panel(
        draw, 12 + pw, 10, pw, 330,
        "B. TTFT (ms) vs #decode  (P=2, 25GB/s)",
        [1, 2], ["1D", "2D"],
        [
            ("mean", MEAN, [(1, d["2P1D"]["mean_ttft_ms"]), (2, d["2P2D"]["mean_ttft_ms"])]),
            ("p99", P99, [(1, d["2P1D"]["p99_ttft_ms"]), (2, d["2P2D"]["p99_ttft_ms"])]),
        ],
        "TTFT (ms)",
    )
    panel(
        draw, 12 + 2 * pw, 10, pw, 330,
        "C. TTFT (ms) vs KV BW (GB/s, 2P1D)",
        [10, 25, 100], ["10", "25", "100"],
        [
            ("mean", MEAN, [(10, d["2P1D@10"]["mean_ttft_ms"]), (25, d["2P1D"]["mean_ttft_ms"]), (100, d["2P1D@100"]["mean_ttft_ms"])]),
            ("p99", P99, [(10, d["2P1D@10"]["p99_ttft_ms"]), (25, d["2P1D"]["p99_ttft_ms"]), (100, d["2P1D@100"]["p99_ttft_ms"])]),
        ],
        "TTFT (ms)",
    )

    note = (
        "Qwen3-0.6B / linear timing from 910B3 public data "
        "(fixed 6.2ms + 15us/prefill-token + 2.4ms/decode-req + 0.14us/KV-token); "
        "8 requests x 1024 in / 64 out; KV 2 GiB; single run each."
    )
    draw.text((14, H - 62), note, font=fs, fill=(90, 90, 90))
    tpot = (
        "TPOT mean: 1P1D 24.8ms | 2P1D 25.4ms | 2P2D 15.8ms | 1P2D 15.2ms      "
        "duration: 2P1D 1.78s -> 2P2D 1.15s (-35%)"
    )
    draw.text((14, H - 38), tpot, font=fsb, fill=FG)

    img.save(OUT)
    print(f"wrote {OUT}")
    print(f"read results from {RESULT_DIR}")
    for k, v in d.items():
        print(f"{k:10} TTFT mean {v['mean_ttft_ms']:7.1f}  p99 {v['p99_ttft_ms']:7.1f}  "
              f"TPOT {v['mean_tpot_ms']:6.2f}  dur {v['duration']:.2f}s")


if __name__ == "__main__":
    sys.exit(main())
