"""Feature 1: Score OCR — read scoreboard digits with EasyOCR.

Uses the same scoreboard crop region as detect_score_changes.py:
  frame[0:h*0.2, w*0.6:w] resized to 500x200, digits at [20:110, 120:310].

EasyOCR runs locally on CPU (no API key needed).
"""

import cv2
import numpy as np

import config

# Lazy singleton — EasyOCR is heavy, only load when first needed
_ocr_reader = None


def init_ocr_reader():
    """Lazy-init a singleton EasyOCR reader (CPU mode)."""
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        _ocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _ocr_reader


def _extract_scoreboard_crop(frame):
    """Extract the 500x200 scoreboard region from a full video frame."""
    h, w = frame.shape[:2]
    sb = frame[0:int(h * 0.2), int(w * 0.6):w]
    sb = cv2.resize(sb, (500, 200))
    return sb


def preprocess_scoreboard(crop):
    """Threshold bright LED digits from a 500x200 scoreboard crop.

    Returns left-half and right-half digit images (for home and away scores).
    """
    x1, y1, x2, y2 = config.SCOREBOARD_DIGIT_REGION
    digits = crop[y1:y2, x1:x2]

    # Convert to grayscale and threshold for bright digits
    gray = cv2.cvtColor(digits, cv2.COLOR_BGR2GRAY)
    # OTSU auto-threshold works well for LED scoreboards
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Split into left (home) and right (away) halves
    mid = thresh.shape[1] // 2
    left = thresh[:, :mid]
    right = thresh[:, mid:]

    return left, right


def read_score(crop):
    """OCR each half of the scoreboard crop and return (home, away) scores.

    Args:
        crop: 500x200 BGR scoreboard image.

    Returns:
        (home_score, away_score) as ints, or (None, None) on failure.
    """
    reader = init_ocr_reader()
    left, right = preprocess_scoreboard(crop)

    def _parse_half(img):
        # Resize up for better OCR accuracy
        img_big = cv2.resize(img, (img.shape[1] * 3, img.shape[0] * 3),
                             interpolation=cv2.INTER_CUBIC)
        results = reader.readtext(img_big, allowlist="0123456789",
                                  paragraph=False, detail=1)
        for bbox, text, conf in results:
            if conf >= config.OCR_CONFIDENCE_THRESHOLD:
                text = text.strip()
                if text.isdigit():
                    val = int(text)
                    if 0 <= val <= 30:
                        return val
        return None

    home = _parse_half(left)
    away = _parse_half(right)
    return home, away


def read_score_from_frame(frame):
    """Convenience: extract scoreboard from a full frame and OCR it.

    Returns (home, away) or (None, None).
    """
    crop = _extract_scoreboard_crop(frame)
    return read_score(crop)


def run_ocr_on_video(video_path, timestamps):
    """Batch OCR at given timestamps in a video.

    Args:
        video_path: Path to video file.
        timestamps: List of float timestamps (seconds).

    Returns:
        List of dicts: [{"timestamp": t, "home": h, "away": a, "raw_crop": crop}, ...]
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []

    fps = cap.get(cv2.CAP_PROP_FPS)
    results = []

    for ts in timestamps:
        frame_num = int(ts * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        if not ret:
            results.append({"timestamp": ts, "home": None, "away": None})
            continue

        crop = _extract_scoreboard_crop(frame)
        home, away = read_score(crop)
        results.append({
            "timestamp": ts,
            "home": home,
            "away": away,
        })

    cap.release()
    return results


def ocr_rally_scores(video_path, rallies):
    """Run OCR on timestamps from rally data, return updated score readings.

    Args:
        video_path: Path to video file.
        rallies: List of rally dicts (must have 'video_time' field).

    Returns:
        List of dicts with OCR results per rally.
    """
    timestamps = []
    for r in rallies:
        vt = r.get("video_time", "")
        if vt:
            try:
                # video_time can be "MM:SS" or seconds
                if ":" in str(vt):
                    parts = str(vt).split(":")
                    ts = int(parts[0]) * 60 + float(parts[1])
                else:
                    ts = float(vt)
                timestamps.append(ts)
            except (ValueError, IndexError):
                timestamps.append(None)
        else:
            timestamps.append(None)

    # Filter valid timestamps for batch OCR
    valid_ts = [t for t in timestamps if t is not None]
    if not valid_ts:
        return []

    ocr_results = run_ocr_on_video(video_path, valid_ts)

    # Map back to rally indices
    ocr_idx = 0
    results = []
    for i, ts in enumerate(timestamps):
        if ts is not None and ocr_idx < len(ocr_results):
            results.append({
                "rally_index": i,
                "rally_id": rallies[i].get("id"),
                "timestamp": ts,
                "home": ocr_results[ocr_idx]["home"],
                "away": ocr_results[ocr_idx]["away"],
            })
            ocr_idx += 1
        else:
            results.append({
                "rally_index": i,
                "rally_id": rallies[i].get("id"),
                "timestamp": ts,
                "home": None,
                "away": None,
            })

    return results
