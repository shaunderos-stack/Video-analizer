"""Player detection & tracking via YOLOv8 + ByteTrack.

Two-pass pipeline per rally:
  Pass 1 — Track: run YOLO+ByteTrack on every Nth frame, collect metadata only.
  Pass 2 — OCR:  seek to best frame per track, crop jersey, read number via EasyOCR.

Reuses jersey_detector helpers for OCR, team classification, and zone mapping.
"""

import cv2
import numpy as np

import config
import db

# ---------------------------------------------------------------------------
# Lazy-loaded YOLO model singleton
# ---------------------------------------------------------------------------

_yolo_model = None


def init_yolo_model():
    """Lazy singleton YOLOv8n (CPU). Auto-downloads ~6MB on first call."""
    global _yolo_model
    if _yolo_model is None:
        from ultralytics import YOLO
        _yolo_model = YOLO("yolov8n.pt")
    return _yolo_model


# ---------------------------------------------------------------------------
# Pass 1 — Track players (metadata only, no frame storage)
# ---------------------------------------------------------------------------

def _run_tracking_pass(video_path, start_sec, end_sec):
    """Run YOLO+ByteTrack on a video segment, collecting per-track metadata.

    Args:
        video_path: Path to the video file.
        start_sec: Start time in seconds.
        end_sec: End time in seconds.

    Returns:
        dict mapping track_id -> list of detection dicts:
            {frame_number, timestamp, bbox_xyxy, conf, area, center}
    """
    model = init_yolo_model()
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return {}

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    start_frame = max(0, int(start_sec * fps))
    end_frame = int(end_sec * fps)
    frame_skip = config.TRACKER_FRAME_SKIP
    min_conf = config.TRACKER_CONFIDENCE

    tracks = {}  # track_id -> [detections]
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    frame_num = start_frame
    frames_read = 0

    while frame_num <= end_frame:
        ret, frame = cap.read()
        if not ret:
            break

        # Only process every Nth frame
        if frames_read % frame_skip != 0:
            frame_num += 1
            frames_read += 1
            continue

        timestamp = frame_num / fps

        # Run YOLO with ByteTrack persistence (classes=[0] = person only)
        results = model.track(
            frame, persist=True, tracker="bytetrack.yaml",
            classes=[0], conf=min_conf, verbose=False,
        )

        if results and results[0].boxes is not None and results[0].boxes.id is not None:
            boxes = results[0].boxes
            for i in range(len(boxes)):
                track_id = int(boxes.id[i].item())
                x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                conf = float(boxes.conf[i].item())
                w = x2 - x1
                h = y2 - y1
                area = w * h
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2

                det = {
                    "frame_number": frame_num,
                    "timestamp": timestamp,
                    "bbox_xyxy": (x1, y1, x2, y2),
                    "conf": conf,
                    "area": area,
                    "center": (cx, cy),
                    "bbox_height": h,
                }

                if track_id not in tracks:
                    tracks[track_id] = []
                tracks[track_id].append(det)

        frame_num += 1
        frames_read += 1

    cap.release()
    return tracks


# ---------------------------------------------------------------------------
# Pass 2 — OCR best frames for qualifying tracks
# ---------------------------------------------------------------------------

def _select_best_detections(tracks):
    """For each qualifying track, pick the detection with highest conf*area.

    Returns:
        list of (track_id, best_detection) for tracks meeting thresholds.
    """
    min_frames = config.TRACKER_MIN_FRAMES_SEEN
    min_height = config.TRACKER_MIN_BBOX_HEIGHT

    selected = []
    for track_id, detections in tracks.items():
        if len(detections) < min_frames:
            continue

        max_height = max(d["bbox_height"] for d in detections)
        if max_height < min_height:
            continue

        # Best frame = highest conf * area product
        best = max(detections, key=lambda d: d["conf"] * d["area"])
        selected.append((track_id, best))

    return selected


def _ocr_tracks(video_path, selected, home_hsv, away_hsv, home_abbr, away_abbr):
    """Seek to best frames and run OCR + team classification on each track.

    Args:
        video_path: Path to video.
        selected: list of (track_id, best_detection) from _select_best_detections.
        home_hsv, away_hsv: HSV ranges for team classification.
        home_abbr, away_abbr: Team abbreviation strings.

    Returns:
        list of result dicts per track.
    """
    from jersey_detector import read_jersey_number, _classify_team_by_color, _classify_zone

    if not selected:
        return []

    # Collect unique frame numbers and map to tracks
    frame_to_tracks = {}
    for track_id, det in selected:
        fn = det["frame_number"]
        if fn not in frame_to_tracks:
            frame_to_tracks[fn] = []
        frame_to_tracks[fn].append((track_id, det))

    # Open video once and seek to each unique frame
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []

    results = []
    for frame_num in sorted(frame_to_tracks.keys()):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        if not ret:
            continue

        fh, fw = frame.shape[:2]
        hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        for track_id, det in frame_to_tracks[frame_num]:
            x1, y1, x2, y2 = det["bbox_xyxy"]
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

            # Clamp to frame bounds
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(fw, x2)
            y2 = min(fh, y2)

            bbox_w = x2 - x1
            bbox_h = y2 - y1
            if bbox_w < 10 or bbox_h < 10:
                continue

            # Extract jersey crop (upper 15-55% of person bbox)
            jersey_top = y1 + int(bbox_h * 0.15)
            jersey_bottom = y1 + int(bbox_h * 0.55)
            jersey_left = x1 + int(bbox_w * 0.1)
            jersey_right = x2 - int(bbox_w * 0.1)
            jersey_top = max(0, jersey_top)
            jersey_bottom = min(fh, jersey_bottom)
            jersey_left = max(0, jersey_left)
            jersey_right = min(fw, jersey_right)

            if jersey_bottom <= jersey_top or jersey_right <= jersey_left:
                continue

            jersey_crop = frame[jersey_top:jersey_bottom, jersey_left:jersey_right]
            number, ocr_conf = read_jersey_number(jersey_crop)

            # Team classification via HSV around bbox center
            cx, cy = int(det["center"][0]), int(det["center"][1])
            pad = 20
            ry1 = max(0, cy - pad)
            ry2 = min(fh, cy + pad)
            rx1 = max(0, cx - pad)
            rx2 = min(fw, cx + pad)
            region_hsv = hsv_frame[ry1:ry2, rx1:rx2]

            team = _classify_team_by_color(region_hsv, home_hsv, away_hsv,
                                           home_abbr, away_abbr)
            zone = _classify_zone((cx, cy), frame.shape)

            results.append({
                "track_id": track_id,
                "jersey_number": number,
                "ocr_confidence": ocr_conf if number is not None else 0.0,
                "detection_confidence": det["conf"],
                "team": team,
                "zone": zone,
                "center": det["center"],
                "timestamp": det["timestamp"],
                "bbox_xyxy": det["bbox_xyxy"],
            })

    cap.release()
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def track_players_in_segment(video_path, start_sec, end_sec,
                             home_hsv, away_hsv, home_abbr, away_abbr):
    """Two-pass tracking+OCR on a video segment.

    Args:
        video_path: Path to video file.
        start_sec: Segment start (seconds).
        end_sec: Segment end (seconds).
        home_hsv: ((h_lo, s_lo, v_lo), (h_hi, s_hi, v_hi)) for home team.
        away_hsv: Same for away team.
        home_abbr: Home team abbreviation.
        away_abbr: Away team abbreviation.

    Returns:
        list of dicts per unique track with jersey_number, team, zone, etc.
    """
    # Pass 1: track
    tracks = _run_tracking_pass(video_path, start_sec, end_sec)

    # Pass 2: OCR best frames
    selected = _select_best_detections(tracks)
    results = _ocr_tracks(video_path, selected,
                          home_hsv, away_hsv, home_abbr, away_abbr)

    return results


def detect_players_for_game_tracked(video_path, game_id,
                                     progress_callback=None,
                                     home_hsv=None, away_hsv=None):
    """Drop-in replacement for jersey_detector.detect_players_for_game().

    Uses YOLO+ByteTrack for person detection and persistent tracking,
    then reads jersey numbers via EasyOCR from the best frame per track.

    Args:
        video_path: Path to video.
        game_id: Game ID.
        progress_callback: Optional callable(current, total).
        home_hsv: Optional HSV range for home team.
        away_hsv: Optional HSV range for away team.

    Returns:
        Number of rallies where a server was identified.
    """
    game = db.get_game(game_id)
    if not game:
        return 0

    home_abbr = game.get("home_abbr", "home")
    away_abbr = game.get("away_abbr", "away")

    if home_hsv is None:
        home_hsv = config.HOME_JERSEY_HSV
    if away_hsv is None:
        away_hsv = config.AWAY_JERSEY_HSV

    rallies = db.get_rallies_without_players(game_id)
    if not rallies:
        return 0

    identified = 0
    total = len(rallies)
    window_before = config.TRACKER_WINDOW_BEFORE
    window_after = config.TRACKER_WINDOW_AFTER

    for i, r in enumerate(rallies):
        vt = r.get("video_time", "")
        if not vt:
            if progress_callback:
                progress_callback(i + 1, total)
            continue

        # Parse timestamp
        try:
            if ":" in str(vt):
                parts = str(vt).split(":")
                ts = int(parts[0]) * 60 + float(parts[1])
            else:
                ts = float(vt)
        except (ValueError, IndexError):
            if progress_callback:
                progress_callback(i + 1, total)
            continue

        start_sec = max(0, ts - window_before)
        end_sec = ts + window_after
        serving = r.get("serving_team", "")

        # Run two-pass tracking + OCR
        track_results = track_players_in_segment(
            video_path, start_sec, end_sec,
            home_hsv, away_hsv, home_abbr, away_abbr,
        )

        # Find server: among tracks classified as the serving team,
        # pick the one in a back-row zone with the highest OCR confidence
        server_result = None
        best_server_conf = 0.0
        serving_lower = serving.lower()

        for tr in track_results:
            # Store all detections
            db.insert_player_detection(
                rally_id=r["id"],
                frame_timestamp=tr["timestamp"],
                zone=tr["zone"],
                team=tr["team"],
                jersey_number=tr["jersey_number"],
                confidence=tr["ocr_confidence"],
                role="",
                track_id=tr["track_id"],
            )

            # Check if this track could be the server
            if tr["jersey_number"] is None:
                continue

            tr_team_lower = tr["team"].lower()
            is_serving_team = (
                tr_team_lower == serving_lower
                or (tr_team_lower == home_abbr.lower()
                    and serving_lower in ("home", home_abbr.lower()))
                or (tr_team_lower == away_abbr.lower()
                    and serving_lower in ("away", away_abbr.lower()))
            )

            if not is_serving_team:
                continue

            # Prefer back-row zones for server
            is_back_row = tr["zone"].startswith("back")
            effective_conf = tr["ocr_confidence"]
            if is_back_row:
                effective_conf *= 1.5  # boost back-row candidates

            if effective_conf > best_server_conf:
                server_result = tr
                best_server_conf = effective_conf

        if server_result:
            player_label = f"#{server_result['jersey_number']} ({serving})"
            db.update_rally(r["id"], key_player=player_label)
            identified += 1

            # Mark server detection with role
            db.insert_player_detection(
                rally_id=r["id"],
                frame_timestamp=server_result["timestamp"],
                zone=server_result["zone"],
                team=serving,
                jersey_number=server_result["jersey_number"],
                confidence=server_result["ocr_confidence"],
                role="server",
                track_id=server_result["track_id"],
            )

        if progress_callback:
            progress_callback(i + 1, total)

    return identified
