# SafeSite AI

SafeSite AI is a Flask-based construction safety monitoring app that uses YOLO models to detect workers, PPE compliance, and restricted-zone intrusions in real time.

## Best Model
```
https://drive.google.com/file/d/1keShImRescQkreYiGrvxLL_G49aH4vRY/view?usp=sharing
```

## Features

- Real-time video monitoring from a webcam or uploaded video file
- PPE violation detection for missing helmets and safety vests
- Restricted-zone creation and intrusion alerts
- Bilingual voice alerts
- Violation logging in a local SQLite database
- Dashboard analytics and PDF report generation

## Project Structure

```text
SafeSIteAI/
|-- app.py                  # Flask entry point
|-- detection/              # PPE and zone detection logic
|-- alerts/                 # Voice alert system
|-- database/               # SQLite access layer
|-- dashboard/              # Analytics and charts
|-- reports/                # PDF report generation
|-- templates/              # Flask HTML templates
|-- static/                 # CSS, JS, and generated screenshots
|-- zones/                  # Persisted restricted-zone definitions
|-- uploads/                # Uploaded video files
|-- runs/                   # YOLO training/inference outputs
|-- ppe detection.v3i.yolov8/  # Local dataset folder
|-- requirements.txt
|-- .gitignore
```

## Requirements

- Python 3.11+ recommended
- A webcam for live monitoring, or a local video file
- YOLO model weights placed in the project root:
  - `ppe_best.pt`
  - `yolov8n.pt`

## Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```powershell
python app.py
```

Then open `http://127.0.0.1:5000` in your browser.

## How It Works

- `yolov8n.pt` detects people in the frame.
- `ppe_best.pt` detects PPE items such as helmets and vests.
- A worker is flagged when their bounding box does not sufficiently overlap with the required PPE detections.
- Restricted zones are stored in `zones/zones.json`.
- Violations are stored in `database/safesiteai.db`.
- Incident screenshots are saved under `static/screenshots/`.

## Main Routes

- `/` live monitoring page
- `/dashboard` analytics dashboard
- `/reports` report generation page
- `/video_feed` MJPEG stream

API endpoints include:

- `POST /api/start`
- `POST /api/stop`
- `POST /api/upload_video`
- `GET /api/videos`
- `POST /api/toggle_detection`
- `POST /api/toggle_voice`
- `GET/POST /api/zones`
- `DELETE /api/zones/<name>`
- `POST /api/zones/clear`
- `GET /api/violations`
- `POST /api/report/generate`
- `GET /api/stats`
- `GET /api/recent_violations`

## Git Ignore Notes

The repository is configured to ignore local/generated artifacts such as:

- virtual environments and Python cache
- uploaded videos
- generated violation screenshots
- local SQLite databases
- YOLO training outputs in `runs/`
- large model weights like `*.pt`
- bulky dataset contents inside `ppe detection.v3i.yolov8/`

Dataset metadata files such as `data.yaml` and the Roboflow README files are still kept trackable.

## Notes

- `uploads/`, `static/screenshots/`, and the database file are created and updated locally at runtime.
- The dataset folder in this project appears to be intended for local experimentation/training, not for normal source control.
- If you want this project to be easier for other people to run, the next good step would be adding sample environment/setup notes for model downloads and OS-specific voice dependencies.
