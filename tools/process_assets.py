#!/usr/bin/env python3
"""把 ComfyUI 生成的素材处理进项目。

- 立绘 / 头像：白底 → `rembg` 自动抠图成透明 PNG
- 背景 / CG：不透明，直接复制
- 统一复制到 `resources/images/`

用法（项目根执行）：
    .venv/bin/python tools/process_assets.py                 # 处理默认源目录
    .venv/bin/python tools/process_assets.py --src /mnt/f/AI/ComfyUI/output/etera_assets
    .venv/bin/python tools/process_assets.py --no-rembg      # 跳过抠图（只复制）
    .venv/bin/python tools/process_assets.py --only reimu    # 只处理路径含该子串的
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "resources" / "images"
DEFAULT_SRC = Path("/mnt/f/AI/ComfyUI/output/etera_assets")

# 这些子目录需要透明背景（走 rembg）
TRANSPARENT_DIRS = ("characters", "avatars")


def process_rembg(src: Path, dest: Path) -> bool:
    """用 rembg 去背景，输出 RGBA PNG。"""
    try:
        from rembg import remove
        from PIL import Image
    except ImportError as exc:
        print(f"    [跳过] 缺少依赖: {exc}（先 pip install rembg pillow）")
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as img:
        cut = remove(img.convert("RGBA"))
        cut.save(dest, "PNG")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="处理 ComfyUI 产出并放入项目")
    ap.add_argument("--src", default=str(DEFAULT_SRC), help="ComfyUI 输出目录")
    ap.add_argument("--only", default="", help="只处理路径含该子串的")
    ap.add_argument("--no-rembg", action="store_true", help="跳过抠图，只复制")
    args = ap.parse_args()

    src_root = Path(args.src)
    if not src_root.exists():
        print(f"[×] 源目录不存在: {src_root}")
        return 1

    files = sorted(p for p in src_root.rglob("*.png") if p.is_file())
    if args.only:
        files = [p for p in files if args.only in str(p)]
    if not files:
        print("源目录里没有可处理的图片")
        return 0

    ok = fail = skipped = 0
    for src in files:
        rel = src.relative_to(src_root)
        dest = DEST / rel
        need_alpha = rel.parts and rel.parts[0] in TRANSPARENT_DIRS

        print(f"  {rel}")
        if need_alpha and not args.no_rembg:
            if process_rembg(src, dest):
                print(f"    ✓ 抠图 → {dest.relative_to(ROOT)}")
                ok += 1
            else:
                fail += 1
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            print(f"    ✓ 复制 → {dest.relative_to(ROOT)}")
            ok += 1

    print(f"\n完成：处理 {ok}，失败 {fail}，共 {len(files)} 张")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
