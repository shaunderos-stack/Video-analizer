"""Analyze the full match: read scoreboards at strategic time points using Claude Vision.

Strategy:
1. Sample scoreboard frames every 30s during match play (45:00 to 164:00)
2. Send to Claude Vision in batches to read scores
3. Parse score progression to identify sets and build rally data
"""

import json
import sys
import os
import cv2
import base64
import time as time_mod
from pathlib import Path

import anthropic

VIDEO_PATH = r"C:\Users\shaun\Video analizer\downloads\match.mp4"
RALLIES_DIR = Path(r"C:\Users\shaun\Video analizer\rallies")

# Claude Code OAuth token
CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"


def get_auth_token():
    """Read the Claude Code OAuth access token."""
    with open(CREDENTIALS_PATH, "r") as f:
        creds = json.load(f)
    token = creds.get("claudeAiOauth", {}).get("accessToken", "")
    if not token:
        raise RuntimeError("No OAuth access token found in Claude Code credentials")
    return token


def extract_scoreboard_at_time(cap, timestamp_sec, fps):
    """Extract scoreboard crop at a given time."""
    frame_num = int(timestamp_sec * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
    ret, frame = cap.read()
    if not ret:
        return None
    h, w = frame.shape[:2]
    sb = frame[0:int(h * 0.2), int(w * 0.6):w]
    sb = cv2.resize(sb, (500, 200))
    return sb


def image_to_base64(img):
    """Convert OpenCV image to base64 JPEG."""
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return base64.standard_b64encode(buf.tobytes()).decode("utf-8")


def read_scoreboards_batch(client, scoreboard_images):
    """Send a batch of scoreboard images to Claude Vision to read scores."""
    content = []
    content.append({
        "type": "text",
        "text": (
            "Read these volleyball scoreboard images. The scoreboard layout is: "
            "LEFT number = USTA (home), RIGHT number = UKC (away). "
            "There may also be a set indicator. Read every image carefully.\n\n"
            "Return ONLY a JSON array with one object per image:\n"
            '[{"time": "MM:SS", "left": N, "right": N, "set": N, "notes": ""}]\n'
            "Where left/right are the score numbers, set is the set number if visible (or 0 if not). "
            "If the scoreboard is not visible or unreadable, use -1 for scores.\n\n"
            f"{len(scoreboard_images)} images follow:"
        ),
    })

    for i, (ts_str, img_b64) in enumerate(scoreboard_images):
        content.append({
            "type": "text",
            "text": f"Image {i + 1} — video time {ts_str}:",
        })
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": img_b64,
            },
        })

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[{"role": "user", "content": content}],
    )

    text = response.content[0].text
    try:
        start = text.index("[")
        end = text.rindex("]") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError) as e:
        print(f"  Warning: Could not parse response: {e}")
        print(f"  Response text: {text[:300]}")
        return []


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print("=== Full Match Scoreboard Analysis ===\n")

    # Auth
    token = get_auth_token()
    client = anthropic.Anthropic(auth_token=token)
    print("Authenticated via Claude Code OAuth token")

    # Open video
    cap = cv2.VideoCapture(VIDEO_PATH)
    if not cap.isOpened():
        print("Error: Could not open video")
        sys.exit(1)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    print(f"Video: {duration:.0f}s ({duration / 60:.1f} min), {fps:.1f} FPS")

    # Sample scoreboard every 30s from 45:00 (match start) to end
    MATCH_START = 45 * 60      # 45:00 = 2700s
    MATCH_END = int(duration)   # end of video
    SAMPLE_INTERVAL = 30        # every 30 seconds

    timestamps = list(range(MATCH_START, MATCH_END, SAMPLE_INTERVAL))
    print(f"Sampling {len(timestamps)} scoreboard frames ({MATCH_START}s to {MATCH_END}s at {SAMPLE_INTERVAL}s intervals)")

    # Extract all scoreboard images
    print("\nExtracting scoreboard frames...")
    scoreboard_images = []
    for ts in timestamps:
        sb = extract_scoreboard_at_time(cap, ts, fps)
        if sb is not None:
            mins = ts // 60
            secs = ts % 60
            ts_str = f"{mins}:{secs:02d}"
            img_b64 = image_to_base64(sb)
            scoreboard_images.append((ts_str, img_b64))

    cap.release()
    print(f"Extracted {len(scoreboard_images)} scoreboard images")

    # Send to Claude Vision in batches of 8
    BATCH_SIZE = 8
    all_readings = []
    total_batches = (len(scoreboard_images) + BATCH_SIZE - 1) // BATCH_SIZE

    print(f"\nReading scoreboards in {total_batches} batches...")
    for batch_start in range(0, len(scoreboard_images), BATCH_SIZE):
        batch = scoreboard_images[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        print(f"  Batch {batch_num}/{total_batches} ({batch[0][0]} - {batch[-1][0]})...", end=" ", flush=True)

        try:
            readings = read_scoreboards_batch(client, batch)
            all_readings.extend(readings)
            print(f"OK ({len(readings)} readings)")
        except Exception as e:
            print(f"ERROR: {e}")
            # Add placeholder readings
            for ts_str, _ in batch:
                all_readings.append({"time": ts_str, "left": -1, "right": -1, "set": 0, "notes": f"error: {e}"})

        time_mod.sleep(0.5)

    print(f"\nTotal readings: {len(all_readings)}")

    # Parse readings into sets
    sets = parse_into_sets(all_readings)

    # Save results
    output = {
        "readings": all_readings,
        "sets": sets,
    }
    output_path = RALLIES_DIR / "full_match_analysis.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {output_path}")

    # Print summary
    print("\n=== MATCH SUMMARY ===")
    for s in sets:
        print(f"  Set {s['set_number']}: USTA {s['final_home']} - UKC {s['final_away']}  "
              f"({s['time_start']} - {s['time_end']}, {s['rally_count']} score changes)")

    return output


def parse_into_sets(readings):
    """Parse score readings into sets by detecting score resets."""
    sets = []
    current_set_num = 1
    current_set_readings = []
    prev_left = 0
    prev_right = 0
    max_left = 0
    max_right = 0

    for r in readings:
        left = r.get("left", -1)
        right = r.get("right", -1)

        # Skip unreadable
        if left < 0 or right < 0:
            continue

        # Detect set reset: scores drop significantly (new set started)
        if (max_left >= 15 or max_right >= 15) and left < 5 and right < 5:
            # Save previous set
            if current_set_readings:
                last = current_set_readings[-1]
                sets.append({
                    "set_number": current_set_num,
                    "final_home": max_left,
                    "final_away": max_right,
                    "time_start": current_set_readings[0].get("time", ""),
                    "time_end": last.get("time", ""),
                    "rally_count": count_score_changes(current_set_readings),
                    "readings": current_set_readings,
                })
            current_set_num += 1
            current_set_readings = []
            max_left = 0
            max_right = 0

        current_set_readings.append(r)
        max_left = max(max_left, left)
        max_right = max(max_right, right)
        prev_left = left
        prev_right = right

    # Save final set
    if current_set_readings:
        last = current_set_readings[-1]
        sets.append({
            "set_number": current_set_num,
            "final_home": max_left,
            "final_away": max_right,
            "time_start": current_set_readings[0].get("time", ""),
            "time_end": last.get("time", ""),
            "rally_count": count_score_changes(current_set_readings),
            "readings": current_set_readings,
        })

    return sets


def count_score_changes(readings):
    """Count how many times the score changed in a sequence of readings."""
    changes = 0
    prev_left = -1
    prev_right = -1
    for r in readings:
        left = r.get("left", -1)
        right = r.get("right", -1)
        if left < 0 or right < 0:
            continue
        if left != prev_left or right != prev_right:
            if prev_left >= 0:
                changes += 1
            prev_left = left
            prev_right = right
    return changes


if __name__ == "__main__":
    main()
