"""Pass 2: Extract dense frame bursts around each detected score change.

Reads score_changes.json from Pass 1 and extracts frames at 0.5s intervals
from T-10s to T+2s around each score change, saving all 5 zone crops per frame.

Usage:
    python extract_rallies.py [--before N] [--after N] [--interval N]
    Defaults: 10s before, 2s after, 0.5s interval
"""
import sys
import json
import csv
import cv2
from pathlib import Path


def extract_zone_crops(frame, h, w):
    """Extract all 5 zone crops from a frame. Returns dict of zone_name -> image."""
    crops = {}

    # Full frame (resized)
    full = cv2.resize(frame, (1280, int(h * 1280 / w)))
    crops["full"] = full

    # Serve zone left (UKC side) — bottom-left
    sl = frame[int(h * 0.3):int(h * 0.75), 0:int(w * 0.3)]
    crops["serve_left"] = cv2.resize(sl, (640, 480))

    # Serve zone right (USTA side) — bottom-right
    sr = frame[int(h * 0.3):int(h * 0.75), int(w * 0.7):w]
    crops["serve_right"] = cv2.resize(sr, (640, 480))

    # Net zone — center
    net = frame[int(h * 0.15):int(h * 0.65), int(w * 0.2):int(w * 0.8)]
    crops["net"] = cv2.resize(net, (800, 500))

    # Scoreboard — top-right
    sb = frame[0:int(h * 0.2), int(w * 0.6):w]
    crops["scoreboard"] = cv2.resize(sb, (500, 200))

    return crops


def merge_windows(detections, before_sec, after_sec):
    """Merge overlapping extraction windows.

    If two score changes are close together, their windows overlap.
    Merge them into a single continuous window to avoid extracting
    the same frames twice.

    Returns list of (start_sec, end_sec, detection_indices).
    """
    if not detections:
        return []

    windows = []
    for i, det in enumerate(detections):
        t = det["timestamp_sec"]
        win_start = t - before_sec
        win_end = t + after_sec
        windows.append((win_start, win_end, [i]))

    # Merge overlapping windows
    merged = [windows[0]]
    for win_start, win_end, indices in windows[1:]:
        prev_start, prev_end, prev_indices = merged[-1]
        if win_start <= prev_end:
            # Overlapping — merge
            merged[-1] = (prev_start, max(prev_end, win_end), prev_indices + indices)
        else:
            merged.append((win_start, win_end, indices))

    return merged


def extract_rallies(video_path, detections, output_dir,
                    before_sec=10.0, after_sec=2.0, interval=0.5):
    """Extract dense frame bursts around each detected score change.

    Args:
        video_path: Path to the video
        detections: List of detection dicts from Pass 1
        output_dir: Base output directory
        before_sec: Seconds before score change to start extraction
        after_sec: Seconds after score change to end extraction
        interval: Frame extraction interval in seconds
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Error: Could not open video")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps

    print(f"Video: {duration:.0f}s, {fps:.1f} FPS")
    print(f"Detections: {len(detections)}")
    print(f"Window: {before_sec}s before to {after_sec}s after each change")
    print(f"Interval: {interval}s")

    # Merge overlapping windows
    windows = merge_windows(detections, before_sec, after_sec)
    print(f"Merged into {len(windows)} extraction windows")
    print("-" * 60)

    zones = ["full", "serve_left", "serve_right", "net", "scoreboard"]
    total_extracted = 0
    summary_rows = []

    for win_idx, (win_start, win_end, det_indices) in enumerate(windows):
        # Create rally directory named by the first detection in this window
        first_det = detections[det_indices[0]]
        rally_name = f"rally_{win_idx + 1:03d}_{first_det['time_str'].replace(':', '')}"
        rally_dir = output_dir / rally_name

        for zone in zones:
            (rally_dir / zone).mkdir(parents=True, exist_ok=True)

        # Extract frames
        timestamp = max(0, win_start)
        frame_count = 0
        while timestamp <= min(win_end, duration):
            frame_num = int(timestamp * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()
            if not ret:
                break

            h, w = frame.shape[:2]
            crops = extract_zone_crops(frame, h, w)

            # Create filename from timestamp
            minutes = int(timestamp // 60)
            seconds = int(timestamp % 60)
            frac = int((timestamp % 1) * 10)
            tag = f"{minutes:03d}m{seconds:02d}s{frac}f"

            for zone_name, crop_img in crops.items():
                filepath = rally_dir / zone_name / f"{tag}.jpg"
                cv2.imwrite(str(filepath), crop_img, [cv2.IMWRITE_JPEG_QUALITY, 90])

            frame_count += 1
            timestamp += interval

        total_extracted += frame_count

        # Summary info
        det_times = [detections[i]["time_str"] for i in det_indices]
        det_str = ", ".join(det_times)
        print(f"  Rally {win_idx + 1:3d}: {frame_count:3d} frames "
              f"({int(win_start)}s-{int(win_end)}s) "
              f"score changes at: {det_str}")

        for di in det_indices:
            det = detections[di]
            summary_rows.append({
                "rally": rally_name,
                "detection_index": det["index"],
                "score_change_time": det["time_str"],
                "timestamp_sec": det["timestamp_sec"],
                "big_pixels": det.get("big_pixels", ""),
                "window_start": round(win_start, 1),
                "window_end": round(win_end, 1),
                "frames_extracted": frame_count,
            })

    cap.release()

    # Save summary CSV
    csv_path = output_dir / "summary.csv"
    if summary_rows:
        fieldnames = list(summary_rows[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(summary_rows)

    print("-" * 60)
    print(f"Total: {total_extracted} frames extracted across {len(windows)} rally windows")
    print(f"Summary saved to: {csv_path}")

    return total_extracted


def main():
    rallies_dir = Path(r"C:\Users\shaun\Video analizer\rallies")
    json_path = rallies_dir / "score_changes.json"

    if not json_path.exists():
        print(f"Error: {json_path} not found. Run detect_score_changes.py first.")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    video_name = data["video"]
    video_path = str(Path(r"C:\Users\shaun\Video analizer\downloads") / video_name)
    detections = data["detections"]

    # Parse args
    before = 10.0
    after = 2.0
    interval = 0.5

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--before" and i + 1 < len(args):
            before = float(args[i + 1])
            i += 2
        elif args[i] == "--after" and i + 1 < len(args):
            after = float(args[i + 1])
            i += 2
        elif args[i] == "--interval" and i + 1 < len(args):
            interval = float(args[i + 1])
            i += 2
        else:
            i += 1

    print("Rally Burst Extraction - Pass 2")
    print(f"Score changes file: {json_path}")
    print(f"Detections loaded: {len(detections)}")
    print()

    extract_rallies(video_path, detections, rallies_dir,
                    before_sec=before, after_sec=after, interval=interval)


if __name__ == "__main__":
    main()
