import subprocess
import re
from pathlib import Path
from config import DOWNLOADS_DIR, MAX_VIDEO_RESOLUTION


def sanitize_filename(title: str) -> str:
    """Remove characters that are invalid in file names."""
    return re.sub(r'[<>:"/\\|?*]', '_', title).strip()


def download_video(url: str) -> Path:
    """Download a YouTube video and return the path to the local file.

    Uses yt-dlp to download at up to MAX_VIDEO_RESOLUTION quality.
    """
    print(f"Downloading video from: {url}")

    # First get the video title for a clean filename
    result = subprocess.run(
        ["yt-dlp", "--get-title", url],
        capture_output=True, text=True, check=True
    )
    title = sanitize_filename(result.stdout.strip())
    output_path = DOWNLOADS_DIR / f"{title}.mp4"

    if output_path.exists():
        print(f"Video already downloaded: {output_path}")
        return output_path

    # Download the video
    subprocess.run(
        [
            "yt-dlp",
            "-f", f"bestvideo[height<={MAX_VIDEO_RESOLUTION}]+bestaudio/best[height<={MAX_VIDEO_RESOLUTION}]",
            "--merge-output-format", "mp4",
            "-o", str(output_path),
            url,
        ],
        check=True
    )

    print(f"Downloaded to: {output_path}")
    return output_path
