#!/usr/bin/env python3
"""背景 / CG 后处理：裁成 16:9 并缩放到 1920×1080（不做去背）。

用法（项目根执行）：
    .venv/bin/python tools/process_scene.py \
        --kind background --name shrine \
        --src incoming/art/backgrounds/shrine.png --force

    .venv/bin/python tools/process_scene.py \
        --kind cg --name reimu_01_afternoon \
        --src incoming/art/cg/reimu_01_afternoon.png --force

    # 只检查分辨率/比例，不写文件（CG 常用）
    .venv/bin/python tools/process_scene.py \
        --kind cg --name reimu_01_afternoon --src ... --check-only

输出：
    resources/images/backgrounds/{name}.png
    resources/images/cg/{name}.png

说明：
- 用 ImageOps.fit 居中偏上裁剪（保留画面上半部，下缘本来就会被文本框遮住）
- 统一输出不透明 PNG（引擎按 .png 路径加载）
- 比例与 16:9 差得较多时会裁掉两侧/上下，请先确认构图
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = (1920, 1080)
KIND_DIR = {
    "background": ROOT / "resources" / "images" / "backgrounds",
    "cg": ROOT / "resources" / "images" / "cg",
}


def parse_size(text: str) -> tuple[int, int]:
    try:
        w, h = text.lower().split("x")
        return int(w), int(h)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("尺寸格式应为 WxH，例如 1920x1080") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="背景/CG 裁剪并规范到 1920×1080")
    parser.add_argument("--kind", choices=sorted(KIND_DIR), required=True)
    parser.add_argument("--name", required=True, help="输出文件名（不含扩展名）")
    parser.add_argument("--src", required=True, help="输入图片路径")
    parser.add_argument("--size", default=f"{DEFAULT_TARGET[0]}x{DEFAULT_TARGET[1]}",
                        type=parse_size, help="目标尺寸 WxH（默认 1920x1080）")
    parser.add_argument("--out", default="", help="输出目录（默认按 kind 选择）")
    parser.add_argument("--check-only", action="store_true", help="只检查分辨率/比例")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的输出")
    args = parser.parse_args()

    src = Path(args.src)
    if not src.exists():
        print(f"[×] 输入不存在：{src}")
        return 1

    with Image.open(src) as raw:
        im = raw.convert("RGB")
        ratio = im.width / im.height
        target_ratio = args.size[0] / args.size[1]
        print(
            f"输入：{src} | {im.width}x{im.height} | 比例 {ratio:.4f} | "
            f"目标 {args.size[0]}x{args.size[1]}（{target_ratio:.4f}）"
        )
        if args.check_only:
            diff = abs(ratio - target_ratio)
            print(f"[检查] 与 16:9 比例差 {diff:.4f}，{'可接受' if diff < 0.01 else '需要裁剪/重生成'}")
            return 0

        if args.out:
            out_dir = Path(args.out)
            if not out_dir.is_absolute():
                out_dir = ROOT / out_dir
        else:
            out_dir = KIND_DIR[args.kind]
        out = out_dir / f"{args.name}.png"
        if out.exists() and not args.force:
            print(f"[×] 已存在：{out.relative_to(ROOT)}（加 --force 覆盖）")
            return 1

        fitted = ImageOps.fit(
            im,
            args.size,
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.0),  # 保留上半部
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    fitted.save(out, "PNG", optimize=True)
    print(
        f"[✓] {out.relative_to(ROOT)} | {fitted.width}x{fitted.height} RGB | "
        f"{out.stat().st_size / 1024:.0f} KB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
