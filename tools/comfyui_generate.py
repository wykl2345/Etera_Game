#!/usr/bin/env python3
"""ComfyUI 批量出图脚本（txt2img，小显存友好）。

按 docs/美术资源规范.md 的清单生成缺图，输出到 resources/images/。

用法（在项目根执行）：
    .venv/bin/python tools/comfyui_generate.py --probe       # 探测 ComfyUI 与可用模型
    .venv/bin/python tools/comfyui_generate.py --dry-run     # 只打印计划，不提交
    .venv/bin/python tools/comfyui_generate.py --only reimu  # 只生成名字含 reimu 的
    .venv/bin/python tools/comfyui_generate.py               # 全量生成（跳过已存在的）
    .venv/bin/python tools/comfyui_generate.py --force       # 覆盖已有文件
    .venv/bin/python tools/comfyui_generate.py --host 172.20.0.1:8188   # ComfyUI 在 Windows 侧

依赖：只用标准库（urllib），不需要额外装包。
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "resources" / "images"

# ── 风格统一（角色一致性靠相同前缀 + 同 seed）──────────────────────────
STYLE = ("anime style, clean lineart, soft lighting, muted colors, "
         "touhou project, detailed")
NEGATIVE = ("lowres, bad anatomy, bad hands, extra fingers, missing fingers, "
            "watermark, text, signature, jpeg artifacts, blurry, cropped")

# 角色外观前缀（不同表情共用，保证是同一个人）
CHAR_LOOK = {
    "reimu": ("hakurei reimu, long black hair, red hair tubes, red and white "
              "detached sleeves, shrine maiden, ribbon"),
    "marisa": ("kirisame marisa, blonde hair, black witch hat, white apron, "
               "black dress, holding broom"),
}

EXPRESSION_WORDS = {
    "normal": "calm neutral expression",
    "happy": "happy smile, cheerful",
    "serious": "serious expression, focused",
    "grin": "confident grin, smug",
    "angry": "angry expression",
    "sad": "sad expression",
    "surprised": "surprised expression",
    "embarrassed": "embarrassed, blushing",
    "thinking": "thinking expression",
}

# ── 生成清单（与规范文档同步）────────────────────────────────────────
# (输出相对路径, 宽, 高, 正向提示词)
Job = Dict[str, Any]


def build_jobs() -> List[Job]:
    jobs: List[Job] = []

    # 立绘：832x1216 生成（2:3，SDXL 基准），透明底靠 white background + 后期抠图
    for char, exprs in {
        "reimu": ["normal", "happy", "serious"],
        "marisa": ["normal", "grin", "happy"],
    }.items():
        for expr in exprs:
            jobs.append({
                "path": f"characters/{char}/{expr}.png",
                "width": 832, "height": 1216,
                "prompt": (f"1girl, solo, {CHAR_LOOK[char]}, "
                           f"{EXPRESSION_WORDS.get(expr, expr)}, "
                           f"upper body, standing, simple background, white background, {STYLE}"),
            })

    # 背景：768x432 生成（16:9）
    backgrounds = {
        "shrine": "mountain shrine, stone stairs, offering box, torii gate, "
                  "clear sky, tranquil, no humans, scenery",
        "home": "japanese room interior, tatami, futon, wooden window, "
                "soft daylight, no humans, scenery",
        "forest": "magical forest, mist, giant mushrooms, dappled sunlight, "
                  "no humans, scenery",
        "market": "japanese village market, stalls, paper lanterns, crowd, "
                  "daytime, no humans (foreground), scenery",
    }
    for name, desc in backgrounds.items():
        jobs.append({
            "path": f"backgrounds/{name}.png",
            "width": 1024, "height": 576,
            "prompt": f"{desc}, {STYLE}",
        })

    # CG：768x432 生成（16:9），带角色
    cgs = {
        "reimu_01_afternoon": "hakurei reimu, sitting on wooden veranda, drinking tea, "
                              "afternoon sunlight, relax",
        "reimu_02_leaves": "hakurei reimu, holding broom, standing in shrine yard, "
                           "fallen autumn leaves, sunset",
        "reimu_03_confession": "hakurei reimu, sitting on stone stairs at night, "
                               "paper lantern light, quiet",
        "reimu_04_sunrise": "hakurei reimu, sunrise on mountain top, warm sky, "
                            "back view, wide shot",
    }
    for name, desc in cgs.items():
        jobs.append({
            "path": f"cg/{name}.png",
            "width": 1024, "height": 576,
            "prompt": f"{desc}, cinematic, detailed background, {STYLE}",
        })

    # 头像：512x512 生成
    for char in ("reimu", "marisa"):
        jobs.append({
            "path": f"avatars/{char}/normal.png",
            "width": 768, "height": 768,
            "prompt": (f"1girl, {CHAR_LOOK[char]}, portrait, face closeup, "
                       f"{EXPRESSION_WORDS['normal']}, simple background, {STYLE}"),
        })

    return jobs


# ── ComfyUI HTTP ──────────────────────────────────────────────────────
class Comfy:
    def __init__(self, host: str) -> None:
        self.base = f"http://{host}"

    def _get(self, path: str) -> Any:
        with urllib.request.urlopen(f"{self.base}{path}", timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))

    def _post(self, path: str, data: Dict[str, Any]) -> Any:
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base}{path}", data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))

    def probe(self) -> Optional[Dict[str, Any]]:
        try:
            return self._get("/system_stats")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return None

    def checkpoints(self) -> List[str]:
        try:
            info = self._get("/object_info/CheckpointLoaderSimple")
            return list(info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0])
        except Exception:  # noqa: BLE001
            return []

    def submit(self, workflow: Dict[str, Any]) -> str:
        res = self._post("/prompt", {"prompt": workflow})
        return res["prompt_id"]

    def wait(self, prompt_id: str, timeout: float = 300.0) -> Optional[Dict[str, Any]]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                hist = self._get(f"/history/{prompt_id}")
            except Exception:  # noqa: BLE001
                hist = {}
            if prompt_id in hist:
                return hist[prompt_id]
            time.sleep(1.0)
        return None

    def download(self, filename: str, subfolder: str, folder_type: str, dest: Path) -> bool:
        query = urllib.parse.urlencode({
            "filename": filename, "subfolder": subfolder, "type": folder_type,
        })
        try:
            with urllib.request.urlopen(f"{self.base}/view?{query}", timeout=60) as r:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(r.read())
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"    下载失败: {exc}")
            return False


def build_workflow(job: Job, ckpt: str, seed: int, steps: int, cfg: float,
                   vae: str = "") -> Dict[str, Any]:
    """标准 txt2img 工作流（节点 id 固定，方便排查）。

    vae 非空时插入 VAELoader（动漫风模型配 vaeKlF8Anime2 效果更好）。
    """
    wf = {
        "4": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": ckpt}},
        "5": {"class_type": "EmptyLatentImage",
              "inputs": {"width": job["width"], "height": job["height"], "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode",
              "inputs": {"text": job["prompt"], "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode",
              "inputs": {"text": NEGATIVE, "clip": ["4", 1]}},
        "3": {"class_type": "KSampler",
              "inputs": {"seed": seed, "steps": steps, "cfg": cfg,
                         "sampler_name": "dpmpp_2m", "scheduler": "karras",
                         "denoise": 1.0, "model": ["4", 0],
                         "positive": ["6", 0], "negative": ["7", 0],
                         "latent_image": ["5", 0]}},
        "8": {"class_type": "VAEDecode",
              "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": "etera", "images": ["8", 0]}},
    }
    if vae:
        wf["10"] = {"class_type": "VAELoader", "inputs": {"vae_name": vae}}
        wf["8"]["inputs"]["vae"] = ["10", 0]
    return wf


def main() -> int:
    ap = argparse.ArgumentParser(description="ComfyUI 批量出图（Etera_Game）")
    ap.add_argument("--host", default="127.0.0.1:8188")
    ap.add_argument("--out", default="",
                    help="输出根目录（默认 <项目根>/resources/images）；"
                         "ComfyUI 在 Windows 而脚本在 WSL 时用它指向 Windows 目录")
    ap.add_argument("--probe", action="store_true", help="只探测连接与可用模型")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划")
    ap.add_argument("--only", default="", help="只处理路径含该子串的任务")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的文件")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="生成尺寸缩放（4GB 显存建议 0.5~0.6，例如 0.5 → 立绘 416x608）")
    ap.add_argument("--ckpt", default="", help="指定 checkpoint 文件名（默认自动挑动漫风）")
    ap.add_argument("--vae", default="", help="指定 VAE 文件名（默认用 checkpoint 自带）")
    ap.add_argument("--seed", type=int, default=12345, help="固定 seed 保证角色一致性")
    ap.add_argument("--steps", type=int, default=18)
    ap.add_argument("--cfg", type=float, default=6.5)
    args = ap.parse_args()

    global IMAGES
    if args.out:
        IMAGES = Path(args.out)

    comfy = Comfy(args.host)
    stats = comfy.probe()
    if stats is None:
        print(f"[×] 连不上 ComfyUI: {args.host}")
        print("    确认服务已启动（python main.py --listen 或默认 8188），")
        print("    Windows 侧跑的 ComfyUI 可用 --host <WSL看到的Windows IP>:8188")
        return 1

    dev = (stats.get("devices") or [{}])[0]
    print(f"[✓] ComfyUI 已连接 | 设备: {dev.get('name', '?')} "
          f"| 显存: {round(dev.get('vram_total', 0) / 1024**3, 1)} GB")

    ckpts = comfy.checkpoints()
    if not ckpts:
        print("[×] 没找到可用 checkpoint（models/checkpoints 为空？）")
        return 1
    print(f"[✓] 可用模型 ({len(ckpts)}): {ckpts[:6]}")

    # 优先动漫风 checkpoint（Illustrious / Animix 系）
    if args.ckpt:
        ckpt = args.ckpt
    else:
        prefer = ("anim", "illustrious", "anime")
        ckpt = next(
            (c for c in ckpts if any(k in c.lower() for k in prefer)),
            ckpts[0],
        )
    print(f"    使用: {ckpt}")

    if args.probe:
        return 0

    jobs = build_jobs()
    if args.scale != 1.0:
        for j in jobs:
            j["width"] = max(256, int(round(j["width"] * args.scale / 8)) * 8)
            j["height"] = max(256, int(round(j["height"] * args.scale / 8)) * 8)
    if args.only:
        jobs = [j for j in jobs if args.only in j["path"]]
    todo = [j for j in jobs if args.force or not (IMAGES / j["path"]).exists()]

    print(f"\n计划生成 {len(todo)} 张（共 {len(jobs)} 张，其余已存在）")
    for j in todo:
        print(f"  {j['width']}x{j['height']}  {j['path']}")
    if args.dry_run or not todo:
        return 0

    ok = fail = 0
    for i, job in enumerate(todo, 1):
        dest = IMAGES / job["path"]
        print(f"\n[{i}/{len(todo)}] {job['path']}")
        wf = build_workflow(job, ckpt, args.seed, args.steps, args.cfg, args.vae)
        try:
            pid = comfy.submit(wf)
        except Exception as exc:  # noqa: BLE001
            print(f"    提交失败: {exc}")
            fail += 1
            continue
        hist = comfy.wait(pid)
        if not hist:
            print("    超时或失败")
            fail += 1
            continue
        images = []
        for node_out in (hist.get("outputs") or {}).values():
            images.extend(node_out.get("images") or [])
        if not images:
            print("    没有输出图片（检查节点错误）")
            fail += 1
            continue
        img = images[0]
        if comfy.download(img["filename"], img.get("subfolder", ""),
                          img.get("type", "output"), dest):
            size = dest.stat().st_size // 1024
            try:
                shown = dest.relative_to(ROOT)
            except ValueError:
                shown = dest
            print(f"    ✓ 保存到 {shown} ({size} KB)")
            ok += 1
        else:
            fail += 1

    print(f"\n完成：成功 {ok} 张，失败 {fail} 张")
    if ok:
        print("提示：立绘需要透明背景，生成的是白底 → 用抠图工具处理后再放入 "
              "resources/images/characters/")
        print("     放大可另接 upscale 工作流，本脚本只做初版测试用。")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
