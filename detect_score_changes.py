"""Pass 1: Detect score changes by monitoring the scoreboard region.

Compares consecutive frames at 0.5s intervals, counting pixels in the score
digit area that changed significantly (>50 intensity levels). Score changes
produce 80+ big pixel changes while noise produces ~0.

Usage:
    python detect_score_changes.py [start_sec] [end_sec] [--threshold N]
    Default: Set 1 from 2700 (45:00) to 4080 (68:00)
"""
import sys
import json
import cv2
import numpy as np
from pathlib import Path


def extract_score_strip(frame):
    """Extract the score digit strip from a video frame at full resolution.

    The score digits in the 500x200 scoreboard crop are at x=120-310, y=20-110.
    """
    h, w = frame.shape[:2]
    sb = frame[0:int(h * 0.2), int(w * 0.6):w]
    sb = cv2.resize(sb, (500, 200))
    strip = sb[20:110, 120:310]
    gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    return gray, sb


def count_big_changes(gray1, gray2, intensity_threshold=50):
    """Count pixels that changed by more than intensity_threshold between frames."""
    diff = cv2.absdiff(gray1, gray2)
    return int(np.sum(diff > intensity_threshold))


def detect_score_changes(video_path, start_sec, end_sec,
                         big_px_threshold=60, cooldown_sec=3.0, interval=0.5):
    """Scan video and detect score changes by comparing consecutive frames.

    Args:
        video_path: Path to the video file
        start_sec: Start time in seconds
        end_sec: End time in seconds
        big_px_threshold: Minimum "big pixel changes" to flag a score change
        cooldown_sec: Seconds to wait after a detection before allowing another
        interval: Seconds between frame samples
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Error: Could not open video")
        return []

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    print(f"Video: {duration:.0f}s ({duration / 60:.1f} min), {fps:.1f} FPS")
    print(f"Scanning {start_sec:.0f}s to {min(end_sec, duration):.0f}s at {interval}s intervals")
    print(f"Big pixel threshold: {big_px_threshold}, Cooldown: {cooldown_sec}s")
    print("-" * 60)

    prev_gray = None
    detections = []
    last_detection_time = -999
    timestamp = start_sec
    frame_count = 0
    all_values = []

    debug_dir = Path(r"C:\Users\shaun\Video analizer\rallies\debug")
    debug_dir.mkdir(parents=True, exist_ok=True)

    while timestamp <= min(end_sec, duration):
        frame_num = int(timestamp * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        if not ret:
            break

        gray, sb_crop = extract_score_strip(frame)
        frame_count += 1

        if prev_gray is not None:
            big_px = count_big_changes(prev_gray, gray)
            all_values.append({"t": round(timestamp, 1), "big_px": big_px})

            if big_px >= big_px_threshold and (timestamp - last_detection_time) > cooldown_sec:
                minutes = int(timestamp // 60)
                seconds = int(timestamp % 60)
                time_str = f"{minutes:02d}:{seconds:02d}"

                detection = {
                    "index": len(detections) + 1,
                    "timestamp_sec": round(timestamp, 1),
                    "time_str": time_str,
                    "big_pixels": big_px,
                }
                detections.append(detection)
                last_detection_time = timestamp

                print(f"  SCORE #{len(detections):3d} at {time_str} "
                      f"(t={timestamp:.1f}s) big_px={big_px}")

                # Save debug scoreboard crop
                idx = len(detections)
                cv2.imwrite(str(debug_dir / f"change_{idx:03d}_{time_str.replace(':','')}.jpg"),
                            sb_crop)

        prev_gray = gray
        timestamp += interval

        if frame_count % 200 == 0:
            m = int(timestamp // 60)
            s = int(timestamp % 60)
            print(f"  ... scanned to {m:02d}:{s:02d} "
                  f"({frame_count} frames, {len(detections)} changes)")

    cap.release()

    # Stats
    if all_values:
        vals = [v["big_px"] for v in all_values]
        arr = np.array(vals)
        nonzero = arr[arr > 0]
        print("-" * 60)
        print(f"Scan complete: {frame_count} frames")
        print(f"Big pixel stats: min={arr.min()}, max={arr.max()}, "
              f"mean={arr.mean():.1f}, median={np.median(arr):.0f}")
        if len(nonzero) > 0:
            print(f"Non-zero values: {len(nonzero)} of {len(arr)} frames")
            print(f"Non-zero stats: mean={nonzero.mean():.1f}, median={np.median(nonzero):.0f}")
        percentiles = [50, 75, 90, 95, 99, 99.5]
        pvals = np.percentile(arr, percentiles)
        print(f"Percentiles: " + ", ".join(f"p{p}={v:.0f}" for p, v in zip(percentiles, pvals)))
        print(f"\nDetections: {len(detections)} score changes found")
        print(f"Expected: ~42 for Set 1 (USTA 25 + UKC 17)")

    return detections, all_values


def main():
    video = r"C:\Users\shaun\Video analizer\downloads\ACAA Women's Volleyball 🏐 UKC @ USTA [25-Jan-26].mp4"
    output_dir = Path(r"C:\Users\shaun\Video analizer\rallies")
    output_dir.mkdir(parents=True, exist_ok=True)

    start = 2700.0
    end = 4080.0
    threshold = 60

    args = sys.argv[1:]
    positional = []
    i = 0
    while i < len(args):
        if args[i] == "--threshold" and i + 1 < len(args):
            threshold = int(args[i + 1])
            i += 2
        else:
            positional.append(float(args[i]))
            i += 1

    if len(positional) >= 1:
        start = positional[0]
    if len(positional) >= 2:
        end = positional[1]

    print("Score Change Detection - Set 1")
    print()

    detections, all_values = detect_score_changes(
        video, start, end, big_px_threshold=threshold
    )

    json_path = output_dir / "score_changes.json"
    result = {
        "video": str(Path(video).name),
        "start_sec": start,
        "end_sec": end,
        "big_px_threshold": threshold,
        "total_detections": len(detections),
        "detections": detections,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    timeseries_path = output_dir / "big_px_timeseries.json"
    with open(timeseries_path, "w", encoding="utf-8") as f:
        json.dump(all_values, f)

    print(f"\nResults saved to: {json_path}")


if __name__ == "__main__":
    main()
