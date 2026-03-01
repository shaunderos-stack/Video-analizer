# Volleyball Analytics Platform

A Streamlit-powered analytics platform for volleyball coaches and analysts. Analyze game video, track player stats, and visualize team performance — all from a single dashboard.

## Features

- **Video Analysis Pipeline** — Download YouTube game footage, extract frames, and use Claude AI (vision) to automatically detect rallies, score changes, and play types
- **Player Tracking** — YOLO + ByteTrack detection identifies players by jersey number and tracks positions across rallies
- **Score OCR** — Automatic scoreboard reading from video frames
- **Interactive Dashboard** — Streamlit app with pages for games, teams, players, season analytics, and exports
- **Game Detail View** — Play-by-play with YouTube timestamp links, rally log, player stats, team comparison, rotation analysis, score progression, video clips, and scouting notes
- **Season Analytics** — Leaderboards, head-to-head matchups, side-out percentages, and rotation breakdowns
- **Excel Export** — Export game stats and rally logs to spreadsheets

## Tech Stack

| Component | Technology |
|---|---|
| Frontend | Streamlit |
| Database | SQLite (WAL mode, FK enforcement) |
| AI/Vision | Anthropic Claude API |
| Object Detection | YOLOv8 + ByteTrack |
| OCR | EasyOCR |
| Video | yt-dlp, OpenCV |
| Data | pandas, openpyxl, matplotlib |

## Getting Started

### Prerequisites

- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com/) for video analysis features

### Installation

```bash
git clone https://github.com/shaunderos-stack/Video-analizer.git
cd Video-analizer
pip install -r requirements.txt
pip install streamlit
```

### Set your API key

```bash
export ANTHROPIC_API_KEY="your-key-here"
```

### Run the app

```bash
streamlit run app.py
```

The database is created automatically on first run with sample seed data (UKC vs USTA, Set 1).

## Project Structure

```
├── app.py                  # Streamlit app (all pages)
├── db.py                   # SQLite database layer
├── config.py               # Configuration constants
├── pipeline.py             # Full analysis pipeline orchestrator
├── analyzer.py             # Claude vision analysis
├── analyze_full_match.py   # Full-match analysis entry point
├── extract_rallies.py      # Rally extraction from video
├── detect_score_changes.py # Score change detection
├── score_ocr.py            # Scoreboard OCR
├── play_classifier.py      # Play type classification
├── player_tracker.py       # YOLO + ByteTrack player tracking
├── jersey_detector.py      # Jersey number detection
├── clip_extractor.py       # Rally video clip extraction
├── frame_extractor.py      # Frame extraction from video
├── downloader.py           # YouTube video downloader
├── exporter.py             # Excel/data export
├── stats_tracker.py        # Stat aggregation helpers
├── models.py               # Data models
├── generate_excel.py       # Seed data generation
└── requirements.txt
```

## Database Schema

Six main tables: **teams**, **players**, **seasons**, **games**, **sets**, **rallies**, plus **player_set_stats** and **player_detections** for stats and tracking data.

## License

This project is for personal/educational use.
