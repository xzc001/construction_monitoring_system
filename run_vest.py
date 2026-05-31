"""未穿反光衣模块命令行入口。

示例:
    python run_vest.py --video your_clip.mp4 --out vest_demo
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.modules.vest import VestConfig, VestPipeline


def main():
    p = argparse.ArgumentParser(description="未穿反光衣告警(独立模块)")
    p.add_argument("--video", required=True)
    p.add_argument("--out", default=None)
    p.add_argument("--vest_conf", type=float, default=0.40)
    p.add_argument("--persist", type=float, default=1.0)
    p.add_argument("--no-require-person", action="store_true")
    p.add_argument("--imgsz", type=int, default=1280)
    args = p.parse_args()

    video_in = Path(args.video)
    if not video_in.is_absolute():
        video_in = ROOT / video_in
    assert video_in.exists(), f"找不到视频: {video_in}"

    cfg = VestConfig(vest_conf=args.vest_conf, persist_alert=args.persist,
                     require_person=not args.no_require_person, imgsz=args.imgsz)
    VestPipeline(cfg).process_video(
        video_in, ROOT / "runs" / (args.out or video_in.stem + "_vest"))


if __name__ == "__main__":
    main()
