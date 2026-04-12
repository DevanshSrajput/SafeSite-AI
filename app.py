import os
import sys
import cv2
import json
import time
import threading
from datetime import datetime
from flask import (Flask, render_template, Response, request,
                   jsonify, send_file)
from werkzeug.utils import secure_filename

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from detection.detector import PPEDetector
from detection.zone_monitor import ZoneMonitor
from alerts.voice_alert import VoiceAlertSystem
from reports.report_generator import generate_report
from dashboard.analytics import generate_dashboard_data
from database.db import log_violation, get_violations, get_violation_stats, init_db

app = Flask(__name__)

# --- Configuration ---
VIDEO_SOURCE = 0  # 0 = webcam, or path to video file like 'video.mp4'
CONFIDENCE_PERSON = 0.50
CONFIDENCE_PPE = 0.40
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
ALLOWED_VIDEO_EXT = {'mp4', 'avi', 'mkv', 'mov', 'wmv', 'flv', 'webm'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max upload

# --- Initialize modules ---
detector = PPEDetector(ppe_model_path='ppe_best.pt', person_model_path='yolov8n.pt',
                       person_confidence=CONFIDENCE_PERSON, ppe_confidence=CONFIDENCE_PPE)
zone_monitor = ZoneMonitor()
voice_alert = VoiceAlertSystem(enabled=True)

# --- Global state ---
camera = None
camera_lock = threading.Lock()
is_monitoring = False
frame_count = 0
detection_active = True
voice_enabled = True


def get_camera():
    """Get or create the video capture object."""
    global camera
    with camera_lock:
        if camera is None or not camera.isOpened():
            camera = cv2.VideoCapture(VIDEO_SOURCE)
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        return camera


def release_camera():
    """Release the video capture object."""
    global camera
    with camera_lock:
        if camera is not None:
            camera.release()
            camera = None


def generate_frames():
    """Generator: yield annotated MJPEG frames for the video feed.

    Detection runs in a background thread (detector._detection_worker).
    This generator only submits frames and reads cached results, so the
    video stream is never blocked by inference.
    """
    global frame_count, is_monitoring

    cam = get_camera()
    is_monitoring = True

    # For video files, throttle to original FPS so playback looks natural
    is_video_file = isinstance(VIDEO_SOURCE, str)
    if is_video_file:
        fps = cam.get(cv2.CAP_PROP_FPS)
        if fps <= 0 or fps > 120:
            fps = 25.0
        frame_delay = 1.0 / fps
    else:
        frame_delay = 1.0 / 30  # cap webcam at ~30 FPS

    # Keep last-known results so every frame gets annotated
    last_persons = []
    last_ppe_items = []
    last_violations = []
    last_zone_violations = []
    processed_result_id = None  # track which detection batch we already logged

    while is_monitoring:
        frame_start = time.time()

        with camera_lock:
            if cam is None or not cam.isOpened():
                break
            success, frame = cam.read()

        if not success:
            if is_video_file:
                with camera_lock:
                    cam.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            break

        frame_count += 1

        if detection_active:
            # Submit every 3rd frame to the background detector
            if frame_count % 3 == 0:
                detector.submit_frame(frame)

            # Always read cached results (non-blocking)
            persons, ppe_items, violations = detector.get_results()

            # Build a fingerprint to know if these are NEW results
            result_id = None
            if persons or ppe_items or violations:
                result_id = id(persons)  # changes each time detector produces new list
                last_persons = persons
                last_ppe_items = ppe_items
                last_violations = violations
                last_zone_violations = zone_monitor.check_intrusions(persons)

            # Only log/alert when we get genuinely new detection results
            if result_id is not None and result_id != processed_result_id:
                processed_result_id = result_id

                for v in last_violations:
                    vkey = detector.make_violation_key(v['violation_type'], v['bbox'])
                    if detector.should_alert(vkey):
                        screenshot_path = detector.save_screenshot(frame, v['violation_type'])
                        log_violation(
                            violation_type=v['violation_type'],
                            zone_name='',
                            screenshot_path=screenshot_path,
                            confidence_score=v['confidence']
                        )
                        voice_alert.alert(v['violation_type'])

                for v in last_zone_violations:
                    vkey = detector.make_violation_key(f"zone_{v['zone_name']}", v['bbox'])
                    if detector.should_alert(vkey):
                        screenshot_path = detector.save_screenshot(frame, 'Zone_Intrusion')
                        log_violation(
                            violation_type='Zone Intrusion',
                            zone_name=v['zone_name'],
                            screenshot_path=screenshot_path,
                            confidence_score=v['confidence']
                        )
                        voice_alert.alert('Zone Intrusion', v['zone_name'])

            # Annotate every frame with latest cached results
            zone_monitor.draw_zones_on_frame(frame)
            frame = detector.annotate_frame(frame, last_persons, last_ppe_items,
                                             last_violations, last_zone_violations)
        else:
            zone_monitor.draw_zones_on_frame(frame)

        # Encode frame to JPEG
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ret:
            continue

        # Throttle to target FPS
        elapsed = time.time() - frame_start
        wait = frame_delay - elapsed
        if wait > 0:
            time.sleep(wait)

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

    release_camera()


# ===================== ROUTES =====================

@app.route('/')
def index():
    """Live monitoring page."""
    zones = zone_monitor.get_zones_for_drawing()
    return render_template('index.html', zones=json.dumps(zones))


@app.route('/dashboard')
def dashboard():
    """Analytics dashboard page."""
    charts = generate_dashboard_data()
    return render_template('dashboard.html', charts=charts)


@app.route('/reports')
def reports_page():
    """Report generation page."""
    return render_template('reports.html')


@app.route('/video_feed')
def video_feed():
    """MJPEG video stream endpoint."""
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/start', methods=['POST'])
def start_monitoring():
    """Start the video monitoring."""
    global is_monitoring, VIDEO_SOURCE
    data = request.get_json() or {}
    source = data.get('source', '0')

    # Determine video source
    if source == '0' or source == 'webcam':
        VIDEO_SOURCE = 0
    else:
        # Check uploads folder first, then treat as raw path
        upload_path = os.path.join(UPLOAD_FOLDER, source)
        if os.path.isfile(upload_path):
            VIDEO_SOURCE = upload_path
        elif os.path.isfile(source):
            VIDEO_SOURCE = source
        else:
            return jsonify({'error': f'Video file not found: {source}'}), 404

    release_camera()
    is_monitoring = True
    return jsonify({'status': 'started', 'source': str(VIDEO_SOURCE)})


@app.route('/api/upload_video', methods=['POST'])
def upload_video():
    """Upload a video file for processing."""
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400

    file = request.files['video']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_VIDEO_EXT:
        return jsonify({'error': f'Invalid format. Allowed: {", ".join(ALLOWED_VIDEO_EXT)}'}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    return jsonify({'status': 'uploaded', 'filename': filename})


@app.route('/api/videos', methods=['GET'])
def list_videos():
    """List available uploaded videos."""
    videos = []
    for f in os.listdir(UPLOAD_FOLDER):
        ext = f.rsplit('.', 1)[-1].lower() if '.' in f else ''
        if ext in ALLOWED_VIDEO_EXT:
            path = os.path.join(UPLOAD_FOLDER, f)
            size_mb = os.path.getsize(path) / (1024 * 1024)
            videos.append({'filename': f, 'size_mb': round(size_mb, 1)})
    return jsonify({'videos': videos})


@app.route('/api/stop', methods=['POST'])
def stop_monitoring():
    """Stop the video monitoring."""
    global is_monitoring
    is_monitoring = False
    release_camera()
    return jsonify({'status': 'stopped'})


@app.route('/api/toggle_detection', methods=['POST'])
def toggle_detection():
    """Toggle PPE detection on/off."""
    global detection_active
    detection_active = not detection_active
    return jsonify({'detection_active': detection_active})


@app.route('/api/toggle_voice', methods=['POST'])
def toggle_voice():
    """Toggle voice alerts on/off."""
    global voice_enabled
    voice_enabled = not voice_enabled
    voice_alert.set_enabled(voice_enabled)
    return jsonify({'voice_enabled': voice_enabled})


# --- Zone Management ---

@app.route('/api/zones', methods=['GET'])
def get_zones():
    """Get all defined zones."""
    return jsonify({'zones': zone_monitor.get_zones_for_drawing()})


@app.route('/api/zones', methods=['POST'])
def add_zone():
    """Add a new restricted zone."""
    data = request.get_json()
    name = data.get('name', f'Zone {len(zone_monitor.zones) + 1}')
    points = data.get('points', [])
    color = data.get('color', '#FF0000')

    if len(points) < 3:
        return jsonify({'error': 'A zone needs at least 3 points'}), 400

    zone = zone_monitor.add_zone(name, points, color)
    return jsonify({'status': 'created', 'zone': zone})


@app.route('/api/zones/<name>', methods=['DELETE'])
def delete_zone(name):
    """Delete a zone by name."""
    zone_monitor.remove_zone(name)
    return jsonify({'status': 'deleted'})


@app.route('/api/zones/clear', methods=['POST'])
def clear_zones():
    """Clear all zones."""
    zone_monitor.clear_zones()
    return jsonify({'status': 'cleared'})


# --- Reports ---

@app.route('/api/violations', methods=['GET'])
def get_violations_api():
    """Get violation logs, optionally filtered by date range."""
    start = request.args.get('start_date', '')
    end = request.args.get('end_date', '')
    vtype = request.args.get('violation_type', '')
    violations = get_violations(start or None, end or None, vtype or None)
    return jsonify({'violations': violations, 'total': len(violations)})


@app.route('/api/report/generate', methods=['POST'])
def generate_report_api():
    """Generate and download a PDF incident report."""
    data = request.get_json() or {}
    start_date = data.get('start_date', '')
    end_date = data.get('end_date', '')

    if not start_date or not end_date:
        today = datetime.now().strftime('%Y-%m-%d')
        start_date = start_date or today
        end_date = end_date or today

    violations = get_violations(start_date, end_date)
    pdf_bytes = generate_report(violations, start_date, end_date)

    import io
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'SafeSiteAI_Report_{start_date}_to_{end_date}.pdf'
    )


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get violation statistics for the dashboard."""
    stats = get_violation_stats()
    return jsonify(stats)


@app.route('/api/recent_violations', methods=['GET'])
def recent_violations():
    """Get the 10 most recent violations for the live feed sidebar."""
    violations = get_violations()
    return jsonify({'violations': violations[:10]})


if __name__ == '__main__':
    init_db()
    print('\n' + '=' * 60)
    print('  SafeSite AI — Real-Time Safety Monitoring System')
    print('  Open http://127.0.0.1:5000 in your browser')
    print('=' * 60 + '\n')
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
