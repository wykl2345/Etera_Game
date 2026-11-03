#!/usr/bin/env python3
"""立绘后处理：去背景（仅未抠图的 RGB 图）+ alpha 清理 + 规范尺寸。

用法（项目根执行）：
    # serious 是带白色/棋盘格底的 RGB 图 → 自动用 isnet-anime 抠图
    .venv/bin/python tools/process_sprite.py \
        --char reimu --expr serious --src "/mnt/c/Users/Hasee/Desktop/Pixel/serious.png" --force

    # normal/happy 已经是 RGBA → 跳过去背，只清 alpha + 缩放
    .venv/bin/python tools/process_sprite.py \
        --char reimu --expr normal --src incoming/art/characters/reimu/normal.png --force

输出：resources/images/characters/{char}/{expr}.png（1200×1800 RGBA）

处理规则：
- 没有有效 alpha（如 RGB 或全不透明）→ rembg isnet-anime 去背
- alpha < floor（默认 8）的噪点清零；alpha >= opaque_at（默认 253）拉到 255
- 等比缩放到 1200×1800（输入应为 2:3；比例不符会直接报错，避免拉伸）

首次运行会下载 isnet-anime 模型（约 176MB）到 .rembg-models/（已 gitignore）。
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = (1200, 1800)
DEFAULT_MODEL = "isnet-anime"
DEFAULT_MODEL_HOME = ROOT / ".rembg-models"


def parse_size(text: str) -> tuple[int, int]:
    try:
        w, h = text.lower().split("x")
        return int(w), int(h)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("尺寸格式应为 WxH，例如 1200x1800") from exc


def has_useful_alpha(im: Image.Image) -> bool:
    """有透明区域才算“已抠图”；全不透明仍需要 rembg。"""
    if im.mode not in ("RGBA", "LA"):
        return False
    alpha = im.convert("RGBA").getchannel("A")
    hist = alpha.histogram()
    transparent = sum(hist[:250])
    return transparent > im.width * im.height * 0.01


def clean_alpha(im: Image.Image, floor: int, opaque_at: int) -> Image.Image:
    """清掉低 alpha 噪点，并把接近不透明的核心拉满 255。"""
    im = im.convert("RGBA")
    alpha = im.getchannel("A")
    lut = []
    for value in range(256):
        if value < floor:
            out = 0
        elif value >= opaque_at:
            out = 255
        else:
            out = round(value * 255 / opaque_at)
        lut.append(out)
    im.putalpha(alpha.point(lut))
    return im


def remove_background(im: Image.Image, model: str) -> Image.Image:
    os.environ.setdefault("U2NET_HOME", str(DEFAULT_MODEL_HOME))
    try:
        from rembg import new_session, remove
    except ImportError as exc:
        raise SystemExit("缺少 rembg：.venv/bin/pip install \"rembg[cli]\" pillow") from exc
    session = new_session(model)
    return remove(im, session=session)


def main() -> int:
    parser = argparse.ArgumentParser(description="立绘去背 + alpha 清理 + 规范尺寸")
    parser.add_argument("--char", required=True, help="角色 id，如 reimu")
    parser.add_argument("--expr", required=True, help="表情文件名，如 serious")
    parser.add_argument("--src", required=True, help="输入图片路径")
    parser.add_argument("--out", default="", help="输出目录（默认 resources/images/characters）")
    parser.add_argument("--size", default=f"{DEFAULT_TARGET[0]}x{DEFAULT_TARGET[1]}",
                        type=parse_size, help="目标尺寸 WxH（默认 1200x1800）")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="rembg 模型（默认 isnet-anime）")
    parser.add_argument("--alpha-floor", type=int, default=8, help="低于该值的 alpha 清零")
    parser.add_argument("--opaque-at", type=int, default=253, help="高于该值的 alpha 拉满 255")
    parser.add_argument("--no-rembg", action="store_true", help="强制不去背（输入必须已有 alpha）")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的输出")
    args = parser.parse_args()

    src = Path(args.src)
    if not src.exists():
        print(f"[×] 输入不存在：{src}")
        return 1

    out_dir = Path(args.out) if args.out else ROOT / "resources" / "images" / "characters" / args.char
    out = out_dir / f"{args.expr}.png"
    if out.exists() and not args.force:
        print(f"[×] 已存在：{out.relative_to(ROOT)}（加 --force 覆盖）")
        return 1

    target = args.size
    with Image.open(src) as raw:
        im = raw.convert("RGBA")
        print(f"输入：{src} | {im.width}x{im.height} {raw.mode}")

        if has_useful_alpha(im):
            print("检测到已有 alpha → 跳过 rembg")
        elif args.no_rembg:
            print("[×] 输入没有有效 alpha，但指定了 --no-rembg")
            return 1
        else:
            print(f"没有有效 alpha → rembg {args.model}（首次会下载模型）…")
            im = remove_background(im, args.model)
            print(f"去背完成：{im.width}x{im.height} RGBA")

        im = clean_alpha(im, args.alpha_floor, args.opaque_at)

        if im.width * target[1] != im.height * target[0]:
            print(
                f"[×] 比例不是 {target[0]}:{target[1]}（输入 {im.width}x{im.height}），"
                "拒绝拉伸。请先生成/裁成 2:3。"
            )
            return 1

        if im.size != target:
            im = im.resize(target, Image.Resampling.LANCZOS)

    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, "PNG", optimize=True)
    alpha = im.getchannel("A")
    hist = alpha.histogram()
    total = im.width * im.height
    print(
        f"[✓] {out.relative_to(ROOT)} | {im.width}x{im.height} RGBA | "
        f"透明 {sum(hist[:10]) / total * 100:.1f}% | {out.stat().st_size / 1024:.0f} KB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
