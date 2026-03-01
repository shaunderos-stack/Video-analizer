"""Extract frames from the video and save as images for manual analysis."""
import sys
import cv2
from pathlib import Path

def extract_frames(video_path: str, output_dir: str, start_sec: float, end_sec: float, interval_sec: float = 30.0):
    """Extract frames at regular intervals and save as JPEG files."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

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

        # Resize to 1280 wide max
        h, w = frame.shape[:2]
        if w > 1280:
            scale = 1280 / w
            frame = cv2.resize(frame, (1280, int(h * scale)))

        minutes = int(timestamp // 60)
        seconds = int(timestamp % 60)
        filename = out / f"frame_{minutes:03d}m{seconds:02d}s.jpg"
        cv2.imwrite(str(filename), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        count += 1
        timestamp += interval_sec

    cap.release()
    print(f"Extracted {count} frames to {out}")


if __name__ == "__main__":
    video = r"C:\Users\shaun\Video analizer\downloads\ACAA Women's Volleyball 🏐 UKC @ USTA [25-Jan-26].mp4"
    output = r"C:\Users\shaun\Video analizer\frames"

    # Parse args: start_sec end_sec interval_sec
    start = float(sys.argv[1]) if len(sys.argv) > 1 else 0
    end = float(sys.argv[2]) if len(sys.argv) > 2 else 300
    interval = float(sys.argv[3]) if len(sys.argv) > 3 else 30

    extract_frames(video, output, start, end, interval)
