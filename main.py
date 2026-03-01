"""Volleyball Video Analyzer — Main entry point.

Downloads a YouTube volleyball game video, analyzes it using Claude's vision API
to detect game events and player actions, then exports comprehensive per-player
statistics to CSV and Excel.

Usage:
    python main.py "https://youtube.com/watch?v=VIDEO_ID"
"""

import sys
import time

from downloader import download_video
from frame_extractor import extract_frames
from analyzer import analyze_frames
from stats_tracker import aggregate_stats
from exporter import export_stats


def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <youtube_url>")
        print('Example: python main.py "https://youtube.com/watch?v=abc123"')
        sys.exit(1)

    url = sys.argv[1]
    start_time = time.time()

    # Step 1: Download
    print("=" * 60)
    print("STEP 1/4: Downloading video")
    print("=" * 60)
    video_path = download_video(url)

    # Step 2: Extract frames
    print("\n" + "=" * 60)
    print("STEP 2/4: Extracting frames")
    print("=" * 60)
    frames = extract_frames(video_path)

    # Step 3: Analyze with Claude Vision
    print("\n" + "=" * 60)
    print("STEP 3/4: Analyzing frames with Claude Vision API")
    print("=" * 60)
    events = analyze_frames(frames)

    # Step 4: Aggregate & export
    print("\n" + "=" * 60)
    print("STEP 4/4: Aggregating stats and exporting")
    print("=" * 60)
    player_stats, game_state = aggregate_stats(events)
    csv_path, xlsx_path = export_stats(player_stats, game_state)

    elapsed = time.time() - start_time
    print(f"\nDone in {elapsed:.1f}s")
    print(f"Output files:")
    print(f"  CSV:   {csv_path}")
    print(f"  Excel: {xlsx_path}")


if __name__ == "__main__":
    main()
