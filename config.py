import os
from pathlib import Path

# --- Paths ---
PROJECT_DIR = Path(__file__).parent
DOWNLOADS_DIR = PROJECT_DIR / "downloads"
OUTPUT_DIR = PROJECT_DIR / "output"

# Ensure directories exist
DOWNLOADS_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# --- Anthropic API ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Claude model to use for vision analysis
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# --- Frame Extraction ---
# Extract one frame every N seconds
FRAME_INTERVAL_SECONDS = 2.0

# Maximum width for extracted frames (reduces API cost)
MAX_FRAME_WIDTH = 1024

# Threshold for scene-change detection (0-1, higher = less sensitive)
SCENE_CHANGE_THRESHOLD = 0.3

# --- Analysis ---
# Number of frames to send per Claude API call
FRAMES_PER_BATCH = 5

# Maximum retries for API calls
MAX_RETRIES = 3

# Delay between API calls in seconds (rate limiting)
API_CALL_DELAY = 1.0

# --- Video Download ---
# Maximum video resolution (keeps download size manageable)
MAX_VIDEO_RESOLUTION = 720

# --- Score OCR (Feature 1) ---
OCR_ENABLED = True
OCR_CONFIDENCE_THRESHOLD = 0.5
SCOREBOARD_DIGIT_REGION = (120, 20, 310, 110)  # (x1, y1, x2, y2) in 500x200 crop

# --- Video Clips (Feature 5) ---
CLIPS_DIR = PROJECT_DIR / "clips"
CLIP_FPS = 15.0
CLIP_RESOLUTION = (854, 480)
CLIP_BEFORE_SEC = 8.0
CLIP_AFTER_SEC = 2.0

# --- Jersey Detection (Feature 2) ---
HOME_JERSEY_HSV = ((100, 50, 20), (130, 255, 120))    # dark navy
AWAY_JERSEY_HSV = ((0, 0, 180), (180, 30, 255))        # white

# --- Player Tracking (YOLO + ByteTrack) ---
TRACKER_ENABLED = True
TRACKER_FRAME_SKIP = 6          # Every 6th frame (60fps → 10 effective fps)
TRACKER_CONFIDENCE = 0.4        # Min YOLO detection confidence
TRACKER_MIN_BBOX_HEIGHT = 60    # Min person bbox height (px) for OCR
TRACKER_WINDOW_BEFORE = 8.0     # Seconds before score change
TRACKER_WINDOW_AFTER = 1.0      # Seconds after score change
TRACKER_MIN_FRAMES_SEEN = 3     # Min appearances to be a real player
