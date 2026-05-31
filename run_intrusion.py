"""危险区域闯入模块命令行入口(不经网站, 直接出标注视频)。

示例(矩形禁区):
    python run_intrusion.py --video data/samples/panel_storyline.mp4 \
        --zone "150,640,820,1080" --out intrusion_demo
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.modules.intrusion import IntrusionConfig, IntrusionPipeline


def main():
    p = argparse.ArgumentParser(description="危险区域闯入告警(独立模块)")
    p.add_argument("--video", required=True, help="输入视频(相对本目录或绝对路径)")
    p.add_argument("--zone", required=True,
                   help='矩形禁区 "x1,y1,x2,y2", 多个用 ; 分隔')
    p.add_argument("--kind", default="no_entry",
                   help="区域类型: no_entry / approach_warning / general")
    p.add_argument("--name", default="危险区域", help="区域中文名")
    p.add_argument("--out", default=None, help="输出子目录名, 默认用视频文件名")
    p.add_argument("--persist", type=float, default=1.5,
                   help="闯入持续多少秒才告警")
    p.add_argument("--imgsz", type=int, default=1280)
    args = p.parse_args()

    video_in = Path(args.video)
    if not video_in.is_absolute():
        video_in = ROOT / video_in
    assert video_in.exists(), f"找不到视频: {video_in}"

    cfg = IntrusionConfig.from_roi_string(
        args.zone, kind=args.kind, name=args.name,
        persist_alert=args.persist, imgsz=args.imgsz)
    print("监控区域: " + "; ".join(f"{z.name}({z.kind}) {z.polygon}" for z in cfg.zones))
    IntrusionPipeline(cfg).process_video(
        video_in, ROOT / "runs" / (args.out or video_in.stem + "_intrusion"))


if __name__ == "__main__":
    main()
