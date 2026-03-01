"""Feature 5: Video clip extraction per rally.

Extracts short clips around each score change using OpenCV VideoWriter.
Output: clips/game_{id}/set{N}_rally{NNN}.mp4 (~1-2 MB each @ 480p 15fps).
"""

import cv2
from pathlib import Path

import config
import db


def extract_rally_clip(video_path, start_sec, end_sec, output_path):
    """Extract a clip from video_path between start_sec and end_sec.

    Args:
        video_path: Source video file path.
        start_sec: Start time in seconds.
        end_sec: End time in seconds.
        output_path: Where to write the output .mp4 file.

    Returns:
        Path to the written clip, or None on failure.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None

    fps = cap.get(cv2.CAP_PROP_FPS)
    out_w, out_h = config.CLIP_RESOLUTION
    out_fps = config.CLIP_FPS

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, out_fps, (out_w, out_h))

    if not writer.isOpened():
        cap.release()
        return None

    # Seek to start
    start_frame = max(0, int(start_sec * fps))
    end_frame = int(end_sec * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    # Calculate frame step to match target fps
    frame_step = max(1, int(fps / out_fps))
    frame_num = start_frame

    while frame_num <= end_frame:
        ret, frame = cap.read()
        if not ret:
            break

        current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
        if (current_frame - start_frame) % frame_step == 0:
            resized = cv2.resize(frame, (out_w, out_h))
            writer.write(resized)

        frame_num = current_frame + 1

    writer.release()
    cap.release()

    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path
    return None


def extract_all_clips(video_path, game_id, progress_callback=None):
    """Extract clips for all rallies in a game that have video timestamps.

    Each clip spans CLIP_BEFORE_SEC before to CLIP_AFTER_SEC after the score change.

    Args:
        video_path: Source video file path.
        game_id: Game ID to look up rallies.
        progress_callback: Optional callable(current, total) for progress updates.

    Returns:
        List of dicts: [{"rally_id": id, "clip_path": path}, ...]
    """
    rallies = db.get_rallies_for_game(game_id)
    if not rallies:
        return []

    # Filter rallies with valid timestamps
    timed_rallies = []
    for r in rallies:
        vt = r.get("video_time", "")
        if vt:
            try:
                if ":" in str(vt):
                    parts = str(vt).split(":")
                    ts = int(parts[0]) * 60 + float(parts[1])
                else:
                    ts = float(vt)
                r["_timestamp_sec"] = ts
                timed_rallies.append(r)
            except (ValueError, IndexError):
                continue

    if not timed_rallies:
        return []

    clips_dir = config.CLIPS_DIR / f"game_{game_id}"
    clips_dir.mkdir(parents=True, exist_ok=True)

    results = []
    total = len(timed_rallies)

    for i, r in enumerate(timed_rallies):
        ts = r["_timestamp_sec"]
        start = max(0, ts - config.CLIP_BEFORE_SEC)
        end = ts + config.CLIP_AFTER_SEC

        set_num = r.get("set_number", 1)
        rally_num = r["rally_number"]
        filename = f"set{set_num}_rally{rally_num:03d}.mp4"
        output_path = clips_dir / filename

        clip_path = extract_rally_clip(video_path, start, end, output_path)

        if clip_path:
            # Update DB with clip path (relative)
            rel_path = str(clip_path.relative_to(Path(config.CLIPS_DIR).parent))
            db.update_rally(r["id"], clip_path=rel_path)
            results.append({"rally_id": r["id"], "clip_path": str(clip_path)})

        if progress_callback:
            progress_callback(i + 1, total)

    return results


def get_clip_path(game_id, set_number, rally_number):
    """Look up the clip file path for a specific rally.

    Returns Path if the clip exists on disk, None otherwise.
    """
    clips_dir = config.CLIPS_DIR / f"game_{game_id}"
    filename = f"set{set_number}_rally{rally_number:03d}.mp4"
    path = clips_dir / filename

    if path.exists():
        return path
    return None
