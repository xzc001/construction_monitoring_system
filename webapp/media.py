"""视频转码工具 —— 把 cv2 写出的 mp4v 转成浏览器可播的 H.264。

cv2.VideoWriter 用 mp4v(MPEG-4 Part2)编码, Chrome/Firefox 的 <video> 标签
普遍无法播放; 必须转成 H.264(avc1)+ yuv420p。
"""

import subprocess
from pathlib import Path

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def ensure_h264(annotated_mp4: Path) -> Path:
    """确保存在浏览器可播的 H.264 版本, 返回其路径。

    输入 .../annotated.mp4, 产出同目录 .../web.mp4(若已最新则直接复用)。
    """
    annotated_mp4 = Path(annotated_mp4)
    web_mp4 = annotated_mp4.with_name("web.mp4")
    if web_mp4.exists() and web_mp4.stat().st_mtime >= annotated_mp4.stat().st_mtime:
        return web_mp4
    cmd = [
        FFMPEG, "-y", "-i", str(annotated_mp4),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-an", str(web_mp4),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return web_mp4
