import json
import time
from typing import Optional

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, FRAMES_PER_BATCH, MAX_RETRIES, API_CALL_DELAY
from models import GameEvent, EventType, Player

ANALYSIS_PROMPT = """You are an expert volleyball analyst. You are watching frames from a volleyball game video.

Analyze these sequential frames and identify any volleyball events that occur. For each event, provide:
- The approximate timestamp (I will tell you the timestamp of each frame)
- The event type
- The player's jersey number (if visible)
- Which team the player is on (describe by jersey color, e.g. "white", "blue")
- Any visible score on the scoreboard

Event types to look for:
- serve: A player serving the ball
- ace: A serve that directly scores a point (no return)
- kill: A successful attack/spike that scores a point
- attack_error: An attack that goes out or into the net
- attack_attempt: Any attack attempt (spike, tip, etc.)
- assist: A set that leads to a kill
- solo_block: A single player blocking for a point
- block_assist: A multi-player block for a point
- block_error: A blocking attempt that results in a violation
- dig: A successful defensive play on an attack
- dig_error: A failed defensive play
- reception: Successfully receiving a serve
- reception_error: Failing to receive a serve
- perfect_pass: A reception rated as perfect (to target)
- service_error: A serve that goes out or into the net
- ball_handling_error: A setting or passing violation
- substitution: A player substitution
- point_scored: Any point scored (include which team)
- rotation: Teams rotating positions

Also identify:
- Team names if visible on jerseys or scoreboard
- Current set number if visible
- Current score if visible on scoreboard

Respond ONLY with valid JSON in this exact format:
{
  "events": [
    {
      "timestamp": 12.5,
      "event_type": "kill",
      "jersey_number": 7,
      "team": "white",
      "details": "Outside hitter #7 in white scores with a cross-court spike",
      "set_number": 1,
      "score_home": 5,
      "score_away": 3
    }
  ],
  "team_info": {
    "home_team": "Team name or color",
    "away_team": "Team name or color"
  },
  "notes": "Any additional observations about the game state"
}

If no events are visible in the frames, return: {"events": [], "team_info": null, "notes": "No volleyball events detected in these frames"}
"""


def _build_messages(frames_batch: list[tuple[float, str]]) -> list[dict]:
    """Build the messages payload for the Claude API with frame images."""
    content = []

    # Add timestamp info
    timestamps = [f"Frame {i+1}: {ts:.1f}s" for i, (ts, _) in enumerate(frames_batch)]
    content.append({
        "type": "text",
        "text": f"Here are {len(frames_batch)} sequential frames from a volleyball game.\nTimestamps: {', '.join(timestamps)}\n\nAnalyze these frames for volleyball events."
    })

    # Add each frame as an image
    for i, (ts, b64_img) in enumerate(frames_batch):
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": b64_img,
            }
        })

    return [{"role": "user", "content": content}]


def _parse_response(response_text: str, frames_batch: list[tuple[float, str]]) -> list[GameEvent]:
    """Parse the Claude API response into GameEvent objects."""
    # Try to extract JSON from the response
    text = response_text.strip()

    # Handle markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (``` markers)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        print(f"  Warning: Could not parse API response as JSON")
        return []

    events = []
    for evt in data.get("events", []):
        try:
            event_type = EventType(evt["event_type"])
        except (ValueError, KeyError):
            continue

        player = None
        if evt.get("jersey_number") is not None and evt.get("team"):
            player = Player(
                jersey_number=int(evt["jersey_number"]),
                team=str(evt["team"]),
            )

        events.append(GameEvent(
            timestamp=float(evt.get("timestamp", 0)),
            event_type=event_type,
            player=player,
            details=str(evt.get("details", "")),
            set_number=int(evt.get("set_number", 1)),
            score_home=evt.get("score_home"),
            score_away=evt.get("score_away"),
        ))

    return events


def analyze_frames(frames: list[tuple[float, str]]) -> list[GameEvent]:
    """Analyze all extracted frames using the Claude Vision API.

    Frames are sent in batches. Returns a list of all detected GameEvents.
    """
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY environment variable is not set.\n"
            "Set it with: set ANTHROPIC_API_KEY=your-api-key"
        )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    all_events: list[GameEvent] = []
    total_batches = (len(frames) + FRAMES_PER_BATCH - 1) // FRAMES_PER_BATCH

    print(f"\nAnalyzing {len(frames)} frames in {total_batches} batches...")

    for batch_idx in range(0, len(frames), FRAMES_PER_BATCH):
        batch = frames[batch_idx:batch_idx + FRAMES_PER_BATCH]
        batch_num = batch_idx // FRAMES_PER_BATCH + 1
        time_range = f"{batch[0][0]:.1f}s - {batch[-1][0]:.1f}s"
        print(f"  Batch {batch_num}/{total_batches} ({time_range})...", end=" ", flush=True)

        messages = _build_messages(batch)

        for attempt in range(MAX_RETRIES):
            try:
                response = client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=4096,
                    system=ANALYSIS_PROMPT,
                    messages=messages,
                )
                response_text = response.content[0].text
                events = _parse_response(response_text, batch)
                all_events.extend(events)
                print(f"found {len(events)} events")
                break
            except anthropic.RateLimitError:
                wait = API_CALL_DELAY * (attempt + 2)
                print(f"rate limited, waiting {wait}s...")
                time.sleep(wait)
            except anthropic.APIError as e:
                print(f"API error: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(API_CALL_DELAY)
                else:
                    print(f"  Skipping batch after {MAX_RETRIES} failures")

        # Rate limiting between batches
        if batch_idx + FRAMES_PER_BATCH < len(frames):
            time.sleep(API_CALL_DELAY)

    print(f"\nAnalysis complete: {len(all_events)} total events detected")
    return all_events
