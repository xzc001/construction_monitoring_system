"""未戴安全帽模块命令行入口(不经网站, 直接出标注视频)。

示例:
    python run_helmet.py --video data/samples/helmet_workshop.mp4 --out helmet_demo
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.modules.helmet import HelmetConfig, HelmetPipeline


def main():
    p = argparse.ArgumentParser(description="未戴安全帽告警(独立模块)")
    p.add_argument("--video", required=True, help="输入视频(相对本目录或绝对路径)")
    p.add_argument("--out", default=None, help="输出子目录名, 默认用视频文件名")
    p.add_argument("--helmet_conf", type=float, default=0.40, help="安全帽模型置信度")
    p.add_argument("--persist", type=float, default=1.0, help="未戴帽持续多少秒才告警")
    p.add_argument("--no-require-person", action="store_true",
                   help="关闭'未戴帽框须落在人体内'的二次校验")
    p.add_argument("--imgsz", type=int, default=1280)
    args = p.parse_args()

    video_in = Path(args.video)
    if not video_in.is_absolute():
        video_in = ROOT / video_in
    assert video_in.exists(), f"找不到视频: {video_in}"

    cfg = HelmetConfig(helmet_conf=args.helmet_conf, persist_alert=args.persist,
                       require_person=not args.no_require_person, imgsz=args.imgsz)
    HelmetPipeline(cfg).process_video(
        video_in, ROOT / "runs" / (args.out or video_in.stem + "_helmet"))


if __name__ == "__main__":
    main()
