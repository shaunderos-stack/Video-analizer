"""Extract zoomed-in crops from key court zones to identify players and actions."""
import sys
import cv2
import numpy as np
from pathlib import Path


def extract_zones(video_path: str, output_dir: str, start_sec: float, end_sec: float, interval_sec: float = 5.0):
    """Extract full frame + zoomed crops of key court zones."""
    out = Path(output_dir)
    (out / "full").mkdir(parents=True, exist_ok=True)
    (out / "serve_left").mkdir(parents=True, exist_ok=True)
    (out / "serve_right").mkdir(parents=True, exist_ok=True)
    (out / "net").mkdir(parents=True, exist_ok=True)
    (out / "scoreboard").mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    print(f"Video: {duration:.0f}s ({duration/60:.1f} min), {fps:.1f} FPS")

    timestamp = start_sec
    count = 0
    while timestamp <= min(end_sec, duration):
        frame_num = int(timestamp * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        if not ret:
            break

        h, w = frame.shape[:2]
        minutes = int(timestamp // 60)
        seconds = int(timestamp % 60)
        tag = f"{minutes:03d}m{seconds:02d}s"

        # Full frame (resized)
        full = cv2.resize(frame, (1280, int(h * 1280 / w)))
        cv2.imwrite(str(out / "full" / f"{tag}.jpg"), full, [cv2.IMWRITE_JPEG_QUALITY, 90])

        # Serve zone left (UKC side in Set 1) - bottom-left of frame
        # The server stands at the back-left from camera's perspective
        sl = frame[int(h*0.3):int(h*0.75), 0:int(w*0.3)]
        sl = cv2.resize(sl, (640, 480))
        cv2.imwrite(str(out / "serve_left" / f"{tag}.jpg"), sl, [cv2.IMWRITE_JPEG_QUALITY, 90])

        # Serve zone right (USTA side in Set 1) - bottom-right of frame
        sr = frame[int(h*0.3):int(h*0.75), int(w*0.7):w]
        sr = cv2.resize(sr, (640, 480))
        cv2.imwrite(str(out / "serve_right" / f"{tag}.jpg"), sr, [cv2.IMWRITE_JPEG_QUALITY, 90])

        # Net zone - center of frame where attacks/blocks happen
        net = frame[int(h*0.15):int(h*0.65), int(w*0.2):int(w*0.8)]
        net = cv2.resize(net, (800, 500))
        cv2.imwrite(str(out / "net" / f"{tag}.jpg"), net, [cv2.IMWRITE_JPEG_QUALITY, 90])

        # Scoreboard - top-right corner
        sb = frame[0:int(h*0.2), int(w*0.6):w]
        sb = cv2.resize(sb, (500, 200))
        cv2.imwrite(str(out / "scoreboard" / f"{tag}.jpg"), sb, [cv2.IMWRITE_JPEG_QUALITY, 90])

        count += 1
        if count % 20 == 0:
            print(f"  Extracted {count} frame sets ({minutes}:{seconds:02d})")

        timestamp += interval_sec

    cap.release()
    print(f"Extracted {count} frame sets to {out}")


if __name__ == "__main__":
    video = r"C:\Users\shaun\Video analizer\downloads\ACAA Women's Volleyball 🏐 UKC @ USTA [25-Jan-26].mp4"
    output = r"C:\Users\shaun\Video analizer\zones"

    start = float(sys.argv[1]) if len(sys.argv) > 1 else 2700
    end = float(sys.argv[2]) if len(sys.argv) > 2 else 4080
    interval = float(sys.argv[3]) if len(sys.argv) > 3 else 5

    extract_zones(video, output, start, end, interval)
