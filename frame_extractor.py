import base64
import io
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from config import FRAME_INTERVAL_SECONDS, MAX_FRAME_WIDTH, SCENE_CHANGE_THRESHOLD


def _resize_frame(frame: np.ndarray) -> np.ndarray:
    """Resize a frame so its width is at most MAX_FRAME_WIDTH, preserving aspect ratio."""
    h, w = frame.shape[:2]
    if w <= MAX_FRAME_WIDTH:
        return frame
    scale = MAX_FRAME_WIDTH / w
    new_w = MAX_FRAME_WIDTH
    new_h = int(h * scale)
    return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)


def _frame_to_base64(frame: np.ndarray) -> str:
    """Convert an OpenCV BGR frame to a base64-encoded JPEG string."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(rgb)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=80)
    return base64.standard_b64encode(buffer.getvalue()).decode("utf-8")


def _frame_difference(frame_a: np.ndarray, frame_b: np.ndarray) -> float:
    """Calculate normalized difference between two frames (0-1)."""
    gray_a = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY)
    # Resize to same dimensions if needed
    if gray_a.shape != gray_b.shape:
        gray_b = cv2.resize(gray_b, (gray_a.shape[1], gray_a.shape[0]))
    diff = cv2.absdiff(gray_a, gray_b)
    return float(np.mean(diff) / 255.0)


def extract_frames(video_path: Path) -> list[tuple[float, str]]:
    """Extract key frames from a video file.

    Returns a list of (timestamp_seconds, base64_jpeg) tuples.

    Frames are extracted at regular intervals (FRAME_INTERVAL_SECONDS) and
    also whenever a significant scene change is detected.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0
    frame_interval = int(fps * FRAME_INTERVAL_SECONDS)

    print(f"Video: {duration:.1f}s, {fps:.1f} FPS, {total_frames} total frames")
    print(f"Extracting frames every {FRAME_INTERVAL_SECONDS}s + scene changes...")

    extracted: list[tuple[float, str]] = []
    prev_frame = None
    frame_idx = 0
    last_extracted_idx = -frame_interval  # allow first frame to be extracted

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        timestamp = frame_idx / fps if fps > 0 else 0.0
        should_extract = False

        # Regular interval extraction
        if frame_idx - last_extracted_idx >= frame_interval:
            should_extract = True

        # Scene-change detection (only check if we wouldn't already extract)
        if not should_extract and prev_frame is not None:
            # Only check every 10 frames for performance
            if frame_idx % 10 == 0:
                diff = _frame_difference(prev_frame, frame)
                if diff > SCENE_CHANGE_THRESHOLD:
                    should_extract = True

        if should_extract:
            resized = _resize_frame(frame)
            b64 = _frame_to_base64(resized)
            extracted.append((timestamp, b64))
            last_extracted_idx = frame_idx

            if len(extracted) % 50 == 0:
                print(f"  Extracted {len(extracted)} frames ({timestamp:.1f}s / {duration:.1f}s)")

        prev_frame = frame
        frame_idx += 1

    cap.release()
    print(f"Extracted {len(extracted)} total frames from {duration:.1f}s video")
    return extracted
