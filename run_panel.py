"""配电箱模块命令行入口(不经网站, 直接出标注视频)。

示例:
    python run_panel.py --video data/samples/panel_storyline.mp4 \
        --panel_roi "195,611,477,790" --out panel_demo
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.modules.panel import PanelConfig, PanelPipeline


def main():
    p = argparse.ArgumentParser(description="配电箱无人值守告警(独立模块)")
    p.add_argument("--video", required=True, help="输入视频(相对本目录或绝对路径)")
    p.add_argument("--panel_roi", required=True, help='配电箱位置 "x1,y1,x2,y2", 多个用 ; 分隔')
    p.add_argument("--out", default=None, help="输出子目录名, 默认用视频文件名")
    p.add_argument("--threshold", type=float, default=95.0, help="门开亮度阈值")
    p.add_argument("--grace", type=float, default=2.0, help='"维修中"宽限期秒数(消除闪烁)')
    p.add_argument("--persist", type=float, default=1.5, help="无人值守持续多少秒才告警")
    p.add_argument("--imgsz", type=int, default=1280)
    args = p.parse_args()

    video_in = Path(args.video)
    if not video_in.is_absolute():
        video_in = ROOT / video_in
    assert video_in.exists(), f"找不到视频: {video_in}"

    cfg = PanelConfig.from_roi_string(
        args.panel_roi, threshold=args.threshold, attended_grace=args.grace,
        persist_alert=args.persist, imgsz=args.imgsz)
    print(f"配电箱 ROI: {cfg.panel_rois}")
    PanelPipeline(cfg).process_video(video_in, ROOT / "runs" / (args.out or video_in.stem))


if __name__ == "__main__":
    main()
