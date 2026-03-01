"""Feature 2: Jersey number detection via HSV color masking + EasyOCR.

Detects players by jersey color (HSV ranges), extracts jersey number crops,
and reads digits with EasyOCR.  Focuses on the serve zone where the server
is isolated and standing still (highest confidence scenario).
"""

import cv2
import numpy as np

import config
import db


def detect_players_by_color(frame, hsv_lower, hsv_upper, min_area=800,
                            max_area=None, exclude_rect=None):
    """Find player-sized blobs matching a jersey color range.

    Args:
        frame: BGR image.
        hsv_lower: (H, S, V) lower bound tuple.
        hsv_upper: (H, S, V) upper bound tuple.
        min_area: Minimum contour area to consider (filters noise).
        max_area: Maximum contour area (filters large non-player blobs).
        exclude_rect: Optional (x1, y1, x2, y2) region to ignore (e.g. scoreboard).

    Returns:
        List of dicts: [{"bbox": (x, y, w, h), "area": int, "center": (cx, cy)}, ...]
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(hsv_lower), np.array(hsv_upper))

    # Black out excluded region (scoreboard overlay etc.)
    if exclude_rect:
        ex1, ey1, ex2, ey2 = exclude_rect
        mask[ey1:ey2, ex1:ex2] = 0

    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Default max_area based on frame size (player shouldn't exceed ~2% of frame)
    if max_area is None:
        fh, fw = frame.shape[:2]
        max_area = int(fh * fw * 0.02)

    players = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        # Filter by aspect ratio — players are taller than wide
        aspect = h / w if w > 0 else 0
        if 0.5 < aspect < 4.0:
            cx = x + w // 2
            cy = y + h // 2
            players.append({"bbox": (x, y, w, h), "area": area, "center": (cx, cy)})

    # Sort by area descending (largest = most likely a real player)
    players.sort(key=lambda p: p["area"], reverse=True)
    return players


def read_jersey_number(jersey_crop):
    """OCR a cropped jersey region to read the number.

    Tries multiple preprocessing strategies: raw scaled image, OTSU
    threshold, and CLAHE enhancement.  Returns the best result.

    Args:
        jersey_crop: BGR image of the upper body / jersey area.

    Returns:
        (number, confidence) or (None, 0.0) if unreadable.
    """
    from score_ocr import init_ocr_reader

    reader = init_ocr_reader()

    h, w = jersey_crop.shape[:2]
    if h < 10 or w < 10:
        return None, 0.0

    # Scale up to at least 120px tall for better OCR
    scale = max(1, 120 // h)
    big = cv2.resize(jersey_crop, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)

    # Try multiple preprocessing approaches and pick the best result
    candidates = [
        big,                    # raw color (best for high-contrast jerseys)
        gray,                   # grayscale
    ]

    # OTSU threshold (good for dark-on-light)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    candidates.append(thresh)

    # CLAHE enhanced (good for low-contrast)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    enhanced = clahe.apply(gray)
    candidates.append(enhanced)

    best_num = None
    best_conf = 0.0

    for img in candidates:
        results = reader.readtext(img, allowlist="0123456789",
                                  paragraph=False, detail=1)
        for bbox, text, conf in results:
            text = text.strip()
            if text.isdigit() and 0 < int(text) <= 99 and conf > best_conf:
                best_num = int(text)
                best_conf = conf
        # Stop early if we found a high-confidence result
        if best_conf > 0.8:
            break

    return best_num, best_conf


def _get_jersey_crop(frame, bbox):
    """Extract the upper-body jersey region from a player bounding box."""
    x, y, w, h = bbox
    # Jersey number is typically in the upper 40-70% of the body
    jersey_top = y + int(h * 0.15)
    jersey_bottom = y + int(h * 0.55)
    jersey_left = x + int(w * 0.1)
    jersey_right = x + int(w * 0.9)

    fh, fw = frame.shape[:2]
    jersey_top = max(0, jersey_top)
    jersey_bottom = min(fh, jersey_bottom)
    jersey_left = max(0, jersey_left)
    jersey_right = min(fw, jersey_right)

    if jersey_bottom <= jersey_top or jersey_right <= jersey_left:
        return None

    return frame[jersey_top:jersey_bottom, jersey_left:jersey_right]


def identify_server(frame, serving_team_hsv):
    """Identify the server in a frame (isolated player at back court).

    First tries serve-zone corners, then falls back to scanning the full
    court for any readable jersey of the serving team.

    Args:
        frame: Full BGR video frame.
        serving_team_hsv: ((h_lo, s_lo, v_lo), (h_hi, s_hi, v_hi)).

    Returns:
        dict with "jersey_number", "confidence", "bbox" or None.
    """
    h, w = frame.shape[:2]
    hsv_lo, hsv_hi = serving_team_hsv

    # Scoreboard exclusion zone (top-left overlay)
    scoreboard_rect = (0, 0, int(w * 0.22), int(h * 0.20))

    # Phase 1: Try traditional serve zones (bottom corners)
    serve_regions = [
        frame[int(h * 0.65):h, 0:int(w * 0.30)],
        frame[int(h * 0.65):h, int(w * 0.70):w],
    ]
    serve_offsets = [
        (0, int(h * 0.65)),
        (int(w * 0.70), int(h * 0.65)),
    ]

    best = None
    best_conf = 0.0

    for region, (ox, oy) in zip(serve_regions, serve_offsets):
        players = detect_players_by_color(region, hsv_lo, hsv_hi, min_area=500)
        if players:
            p = players[0]
            bx, by, bw, bh = p["bbox"]
            full_bbox = (bx + ox, by + oy, bw, bh)
            jersey_crop = _get_jersey_crop(frame, full_bbox)
            if jersey_crop is not None:
                num, conf = read_jersey_number(jersey_crop)
                if num is not None and conf > best_conf:
                    best = {
                        "jersey_number": num,
                        "confidence": conf,
                        "bbox": full_bbox,
                        "zone": "back-left" if ox == 0 else "back-right",
                    }
                    best_conf = conf

    # Phase 2: If serve zones failed, scan full court
    if best is None:
        players = detect_players_by_color(
            frame, hsv_lo, hsv_hi, min_area=500,
            exclude_rect=scoreboard_rect,
        )
        for p in players[:8]:
            jersey_crop = _get_jersey_crop(frame, p["bbox"])
            if jersey_crop is not None:
                num, conf = read_jersey_number(jersey_crop)
                if num is not None and conf > best_conf:
                    best = {
                        "jersey_number": num,
                        "confidence": conf,
                        "bbox": p["bbox"],
                        "zone": _classify_zone(p["center"], frame.shape),
                    }
                    best_conf = conf

    return best


def attribute_rally_players(video_path, rally_time_sec, serving_team,
                            home_hsv=None, away_hsv=None,
                            home_abbr="home", away_abbr="away"):
    """Orchestrator: detect server and key players around a rally timestamp.

    Args:
        video_path: Path to video.
        rally_time_sec: Timestamp of the score change.
        serving_team: "home" or "away" (or team abbreviation like "HOL").
        home_hsv: HSV range for home team (default from config).
        away_hsv: HSV range for away team (default from config).
        home_abbr: Home team abbreviation for matching serving_team.
        away_abbr: Away team abbreviation for matching serving_team.

    Returns:
        dict with "server", "detections" list.
    """
    if home_hsv is None:
        home_hsv = config.HOME_JERSEY_HSV
    if away_hsv is None:
        away_hsv = config.AWAY_JERSEY_HSV

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return {"server": None, "detections": []}

    fps = cap.get(cv2.CAP_PROP_FPS)

    # Sample a few frames before the score change (server should be visible)
    sample_times = [
        rally_time_sec - 6.0,  # early in rally (serve)
        rally_time_sec - 5.0,
        rally_time_sec - 4.0,
    ]

    # Determine which HSV range is for the serving team
    serving_team_lower = serving_team.lower()
    if serving_team_lower in ("home", home_abbr.lower()):
        serve_hsv = home_hsv
    else:
        serve_hsv = away_hsv

    server_result = None
    best_server_conf = 0.0
    all_detections = []
    seen_numbers = set()  # deduplicate across frames

    for t in sample_times:
        if t < 0:
            continue
        frame_num = int(t * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        if not ret:
            continue

        # Primary approach: full-frame OCR scan (works best for elevated cameras)
        scanned = scan_jersey_numbers(
            frame, home_hsv=home_hsv, away_hsv=away_hsv,
            home_abbr=home_abbr, away_abbr=away_abbr,
        )
        for det in scanned:
            key = (det["team"], det["jersey_number"])
            if key not in seen_numbers or det["confidence"] > 0.8:
                seen_numbers.add(key)
                all_detections.append({
                    "frame_timestamp": t,
                    "team": det["team"],
                    "jersey_number": det["jersey_number"],
                    "confidence": det["confidence"],
                    "zone": det["zone"],
                })

                # Check if this could be the server
                serving_team_lower = serving_team.lower()
                det_team_lower = det["team"].lower()
                is_serving_team = (
                    det_team_lower == serving_team_lower
                    or det_team_lower == home_abbr.lower()
                    and serving_team_lower in ("home", home_abbr.lower())
                    or det_team_lower == away_abbr.lower()
                    and serving_team_lower in ("away", away_abbr.lower())
                )
                if is_serving_team and det["confidence"] > best_server_conf:
                    server_result = {
                        "jersey_number": det["jersey_number"],
                        "confidence": det["confidence"],
                        "bbox": (0, 0, 0, 0),
                        "zone": det["zone"],
                    }
                    best_server_conf = det["confidence"]

        # Fallback: try color-detection + crop approach
        if not scanned:
            srv = identify_server(frame, serve_hsv)
            if srv and srv["confidence"] > best_server_conf:
                server_result = srv
                best_server_conf = srv["confidence"]

            h, w = frame.shape[:2]
            scoreboard_rect = (0, 0, int(w * 0.22), int(h * 0.20))
            for team_label, hsv_range in [("home", home_hsv), ("away", away_hsv)]:
                hsv_lo, hsv_hi = hsv_range
                players = detect_players_by_color(
                    frame, hsv_lo, hsv_hi,
                    exclude_rect=scoreboard_rect,
                )
                for p in players[:6]:
                    jersey_crop = _get_jersey_crop(frame, p["bbox"])
                    if jersey_crop is not None:
                        num, conf = read_jersey_number(jersey_crop)
                        if num is not None and conf > 0.3:
                            key = (team_label, num)
                            if key not in seen_numbers:
                                seen_numbers.add(key)
                                all_detections.append({
                                    "frame_timestamp": t,
                                    "team": team_label,
                                    "jersey_number": num,
                                    "confidence": conf,
                                    "zone": _classify_zone(p["center"], frame.shape),
                                })

    cap.release()

    return {
        "server": server_result,
        "detections": all_detections,
    }


def scan_jersey_numbers(frame, home_hsv=None, away_hsv=None,
                        home_abbr="home", away_abbr="away"):
    """Scan a full frame for visible jersey numbers using OCR-first approach.

    Runs EasyOCR on the court region to find all digit-like text, then
    classifies each detection's team by checking the surrounding pixel colors.

    Args:
        frame: Full BGR video frame.
        home_hsv: ((h_lo, s_lo, v_lo), (h_hi, s_hi, v_hi)) for home team.
        away_hsv: Same for away team.
        home_abbr: Home team abbreviation.
        away_abbr: Away team abbreviation.

    Returns:
        List of dicts: [{"jersey_number", "confidence", "team", "zone", "center"}, ...]
    """
    from score_ocr import init_ocr_reader

    if home_hsv is None:
        home_hsv = config.HOME_JERSEY_HSV
    if away_hsv is None:
        away_hsv = config.AWAY_JERSEY_HSV

    reader = init_ocr_reader()
    h, w = frame.shape[:2]

    # Scan the court area (skip scoreboard overlay in top-left)
    y_start = int(h * 0.05)
    y_end = int(h * 0.95)
    court = frame[y_start:y_end, :]

    results = reader.readtext(court, allowlist="0123456789",
                              paragraph=False, detail=1)

    detections = []
    hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    for bbox_pts, text, conf in results:
        text = text.strip()
        if not text.isdigit() or not (0 < int(text) <= 99) or conf < 0.3:
            continue

        # Compute center in full-frame coordinates
        cx = int(sum(p[0] for p in bbox_pts) / 4)
        cy = int(sum(p[1] for p in bbox_pts) / 4) + y_start

        # Skip if in scoreboard area
        if cx < w * 0.22 and cy < h * 0.20:
            continue

        # Sample HSV in a small region around the detection to classify team
        pad = 15
        ry1 = max(0, cy - pad)
        ry2 = min(h, cy + pad)
        rx1 = max(0, cx - pad)
        rx2 = min(w, cx + pad)
        region_hsv = hsv_frame[ry1:ry2, rx1:rx2]

        team = _classify_team_by_color(region_hsv, home_hsv, away_hsv,
                                       home_abbr, away_abbr)
        zone = _classify_zone((cx, cy), frame.shape)

        detections.append({
            "jersey_number": int(text),
            "confidence": float(conf),
            "team": team,
            "zone": zone,
            "center": (cx, cy),
        })

    return detections


def _classify_team_by_color(region_hsv, home_hsv, away_hsv,
                            home_abbr, away_abbr):
    """Classify which team a jersey belongs to based on surrounding HSV pixels."""
    home_lo, home_hi = home_hsv
    away_lo, away_hi = away_hsv

    home_mask = cv2.inRange(region_hsv, np.array(home_lo), np.array(home_hi))
    away_mask = cv2.inRange(region_hsv, np.array(away_lo), np.array(away_hi))

    home_pct = home_mask.sum() / 255
    away_pct = away_mask.sum() / 255

    if home_pct > away_pct and home_pct > 5:
        return home_abbr
    elif away_pct > home_pct and away_pct > 5:
        return away_abbr
    return "unknown"


def _classify_zone(center, frame_shape):
    """Classify a player's court zone from their center position."""
    h, w = frame_shape[:2]
    cx, cy = center
    x_pct = cx / w
    y_pct = cy / h

    if y_pct < 0.4:
        row = "net"
    elif y_pct < 0.65:
        row = "mid"
    else:
        row = "back"

    if x_pct < 0.33:
        col = "left"
    elif x_pct < 0.66:
        col = "center"
    else:
        col = "right"

    return f"{row}-{col}"


def detect_players_for_game(video_path, game_id, progress_callback=None,
                            home_hsv=None, away_hsv=None):
    """Batch detect players for all rallies missing key_player in a game.

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

    rallies = db.get_rallies_without_players(game_id)
    if not rallies:
        return 0

    identified = 0
    total = len(rallies)

    for i, r in enumerate(rallies):
        vt = r.get("video_time", "")
        if not vt:
            continue

        try:
            if ":" in str(vt):
                parts = str(vt).split(":")
                ts = int(parts[0]) * 60 + float(parts[1])
            else:
                ts = float(vt)
        except (ValueError, IndexError):
            continue

        serving = r.get("serving_team", "")
        result = attribute_rally_players(
            video_path, ts, serving,
            home_hsv=home_hsv, away_hsv=away_hsv,
            home_abbr=home_abbr, away_abbr=away_abbr,
        )

        if result["server"]:
            srv = result["server"]
            player_label = f"#{srv['jersey_number']} ({serving})"
            db.update_rally(r["id"], key_player=player_label)
            identified += 1

            # Store detection in player_detections table
            db.insert_player_detection(
                rally_id=r["id"],
                frame_timestamp=ts - 5.0,
                zone=srv.get("zone", ""),
                team=serving,
                jersey_number=srv["jersey_number"],
                confidence=srv["confidence"],
                role="server",
            )

        # Store other detections too
        for det in result["detections"]:
            db.insert_player_detection(
                rally_id=r["id"],
                frame_timestamp=det["frame_timestamp"],
                zone=det["zone"],
                team=det["team"],
                jersey_number=det["jersey_number"],
                confidence=det["confidence"],
                role="",
            )

        if progress_callback:
            progress_callback(i + 1, total)

    return identified
