import cv2
import numpy as np
import os
import time
import threading
from datetime import datetime
from ultralytics import YOLO

SCREENSHOTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'screenshots')


class PPEDetector:
    """Two-model PPE detector with threaded inference.

    - person_model (COCO YOLOv8n): detects persons in the frame.
    - ppe_model (custom-trained): detects PPE items (Helmet, Vest, Boots, Gloves).

    Detection runs in a background thread. The main thread reads cached results
    so the video stream is never blocked by inference.
    """

    PERSON_CLASS = 0

    # Colors (BGR)
    COLOR_SAFE = (0, 200, 0)
    COLOR_HELMET = (0, 180, 0)
    COLOR_VEST = (180, 130, 0)
    COLOR_VIOLATION = (0, 0, 255)
    COLOR_ZONE_INTRUSION = (0, 165, 255)

    def __init__(self, ppe_model_path='ppe_best.pt', person_model_path='yolov8n.pt',
                 person_confidence=0.50, ppe_confidence=0.40):
        self.person_model = YOLO(person_model_path)
        self.ppe_model = YOLO(ppe_model_path)
        self.person_confidence = person_confidence
        self.ppe_confidence = ppe_confidence
        self.violation_cooldown = {}
        self.cooldown_seconds = 5
        self.grid_size = 100  # larger grid = fewer distinct buckets = less spam

        self.ppe_class_map = {}
        for cls_id, name in self.ppe_model.names.items():
            self.ppe_class_map[cls_id] = name

        # --- Threaded detection state ---
        self._detect_lock = threading.Lock()
        self._latest_frame = None
        self._new_frame_event = threading.Event()
        self._cached_persons = []
        self._cached_ppe_items = []
        self._cached_violations = []
        self._running = True
        self._thread = threading.Thread(target=self._detection_worker, daemon=True)
        self._thread.start()

    def _detection_worker(self):
        """Background thread that continuously runs inference on the latest frame."""
        while self._running:
            self._new_frame_event.wait(timeout=0.5)
            self._new_frame_event.clear()

            with self._detect_lock:
                frame = self._latest_frame

            if frame is None:
                continue

            # Run both models
            persons = self._run_person_detection(frame)
            ppe_items = self._run_ppe_detection(frame)
            violations = self._check_violations(persons, ppe_items)

            with self._detect_lock:
                self._cached_persons = persons
                self._cached_ppe_items = ppe_items
                self._cached_violations = violations

    def submit_frame(self, frame):
        """Submit a frame for background detection (non-blocking)."""
        with self._detect_lock:
            self._latest_frame = frame.copy()
        self._new_frame_event.set()

    def get_results(self):
        """Get the latest cached detection results (non-blocking)."""
        with self._detect_lock:
            return (list(self._cached_persons),
                    list(self._cached_ppe_items),
                    list(self._cached_violations))

    def shutdown(self):
        self._running = False
        self._new_frame_event.set()
        self._thread.join(timeout=3)

    def _run_person_detection(self, frame):
        results = self.person_model(frame, conf=self.person_confidence, classes=[0], verbose=False)
        persons = []
        if results and results[0].boxes is not None:
            for box in results[0].boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                persons.append({
                    'class_id': 0,
                    'class_name': 'person',
                    'confidence': float(box.conf[0]),
                    'bbox': (x1, y1, x2, y2),
                    'center': ((x1 + x2) // 2, (y1 + y2) // 2)
                })
        return persons

    def _run_ppe_detection(self, frame):
        results = self.ppe_model(frame, conf=self.ppe_confidence, verbose=False)
        ppe_items = []
        if results and results[0].boxes is not None:
            for box in results[0].boxes:
                cls_id = int(box.cls[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                ppe_items.append({
                    'class_id': cls_id,
                    'class_name': self.ppe_class_map.get(cls_id, 'unknown'),
                    'confidence': float(box.conf[0]),
                    'bbox': (x1, y1, x2, y2),
                    'center': ((x1 + x2) // 2, (y1 + y2) // 2)
                })
        return ppe_items

    def _is_helmet_near_person(self, person_bbox, helmet_bbox):
        """Check if a helmet is near the top of a person's bounding box."""
        px1, py1, px2, py2 = person_bbox
        hx1, hy1, hx2, hy2 = helmet_bbox
        person_h = py2 - py1
        person_w = px2 - px1

        # Helmet center
        hcx = (hx1 + hx2) // 2
        hcy = (hy1 + hy2) // 2

        # Helmet should be within the horizontal span of the person (with margin)
        margin_x = person_w * 0.3
        if hcx < px1 - margin_x or hcx > px2 + margin_x:
            return False

        # Helmet should be near the top 45% of the person
        head_zone_bottom = py1 + person_h * 0.45
        # Allow helmet to be slightly above the person bbox (hat sticking up)
        head_zone_top = py1 - person_h * 0.15

        if hcy < head_zone_top or hcy > head_zone_bottom:
            return False

        return True

    def _is_vest_near_person(self, person_bbox, vest_bbox):
        """Check if a vest overlaps with the torso area of a person."""
        px1, py1, px2, py2 = person_bbox
        vx1, vy1, vx2, vy2 = vest_bbox
        person_h = py2 - py1
        person_w = px2 - px1

        # Vest center
        vcx = (vx1 + vx2) // 2
        vcy = (vy1 + vy2) // 2

        # Vest should be within the horizontal span (with margin)
        margin_x = person_w * 0.3
        if vcx < px1 - margin_x or vcx > px2 + margin_x:
            return False

        # Vest should be in the middle 20%-75% of the person (torso area)
        torso_top = py1 + person_h * 0.15
        torso_bottom = py1 + person_h * 0.80

        if vcy < torso_top or vcy > torso_bottom:
            return False

        return True

    def _check_violations(self, persons, ppe_items):
        """Check which persons are missing helmets or vests using spatial matching."""
        violations = []

        helmets = [p for p in ppe_items if p['class_name'].lower() == 'helmet']
        vests = [p for p in ppe_items if p['class_name'].lower() == 'vest']

        for person in persons:
            has_helmet = any(
                self._is_helmet_near_person(person['bbox'], h['bbox'])
                for h in helmets
            )
            has_vest = any(
                self._is_vest_near_person(person['bbox'], v['bbox'])
                for v in vests
            )

            if not has_helmet:
                violations.append({**person, 'violation_type': 'No Helmet'})
            if not has_vest:
                violations.append({**person, 'violation_type': 'No Safety Vest'})

        return violations

    def check_ppe_violations(self, persons, ppe_items):
        """Public API — kept for compatibility."""
        return self._check_violations(persons, ppe_items)

    def make_violation_key(self, violation_type, bbox):
        cx = (bbox[0] + bbox[2]) // 2
        cy = (bbox[1] + bbox[3]) // 2
        gx = cx // self.grid_size
        gy = cy // self.grid_size
        return f"{violation_type}_{gx}_{gy}"

    def should_alert(self, violation_key):
        now = time.time()
        self.violation_cooldown = {
            k: t for k, t in self.violation_cooldown.items()
            if now - t < self.cooldown_seconds * 3
        }
        if violation_key in self.violation_cooldown:
            if now - self.violation_cooldown[violation_key] < self.cooldown_seconds:
                return False
        self.violation_cooldown[violation_key] = now
        return True

    def save_screenshot(self, frame, violation_type):
        os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        filename = f'{violation_type.replace(" ", "_")}_{timestamp}.jpg'
        filepath = os.path.join(SCREENSHOTS_DIR, filename)
        cv2.imwrite(filepath, frame)
        return f'screenshots/{filename}'

    def annotate_frame(self, frame, persons, ppe_items, violations, zone_violations=None):
        annotated = frame.copy()

        violation_persons = set()
        for v in violations:
            violation_persons.add(v['bbox'])
        if zone_violations:
            for v in zone_violations:
                violation_persons.add(v['bbox'])

        # Draw safe persons (green)
        for p in persons:
            if p['bbox'] not in violation_persons:
                x1, y1, x2, y2 = p['bbox']
                cv2.rectangle(annotated, (x1, y1), (x2, y2), self.COLOR_SAFE, 2)
                label = f"Worker OK ({p['confidence']:.0%})"
                self._put_label(annotated, label, x1, y1 - 10, self.COLOR_SAFE)

        # Draw detected PPE items (thin boxes)
        for item in ppe_items:
            x1, y1, x2, y2 = item['bbox']
            name = item['class_name']
            if name.lower() == 'helmet':
                color = self.COLOR_HELMET
            elif name.lower() == 'vest':
                color = self.COLOR_VEST
            else:
                color = (180, 180, 0)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 1)
            cv2.putText(annotated, name, (x1, y1 - 4),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        # Draw PPE violations (red, thick)
        for v in violations:
            x1, y1, x2, y2 = v['bbox']
            cv2.rectangle(annotated, (x1, y1), (x2, y2), self.COLOR_VIOLATION, 3)
            label = f"{v['violation_type']} ({v['confidence']:.0%})"
            self._put_label(annotated, label, x1, y1 - 10, self.COLOR_VIOLATION)

        # Draw zone intrusion violations (orange, thick)
        if zone_violations:
            for v in zone_violations:
                x1, y1, x2, y2 = v['bbox']
                cv2.rectangle(annotated, (x1, y1), (x2, y2), self.COLOR_ZONE_INTRUSION, 3)
                label = f"ZONE INTRUSION: {v.get('zone_name', '')} ({v['confidence']:.0%})"
                self._put_label(annotated, label, x1, y1 - 10, self.COLOR_ZONE_INTRUSION)

        # Timestamp overlay
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cv2.putText(annotated, ts, (10, annotated.shape[0] - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        return annotated

    def _put_label(self, frame, text, x, y, color):
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.55
        thickness = 2
        (w, h), _ = cv2.getTextSize(text, font, scale, thickness)
        y = max(y, h + 5)
        cv2.rectangle(frame, (x, y - h - 5), (x + w + 5, y + 5), color, -1)
        cv2.putText(frame, text, (x + 2, y), font, scale, (255, 255, 255), thickness)
