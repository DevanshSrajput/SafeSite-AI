import cv2
import numpy as np
import os
import time
from datetime import datetime
from ultralytics import YOLO

SCREENSHOTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'screenshots')


class PPEDetector:
    """Two-model PPE detector.

    - person_model (COCO YOLOv8n): detects persons in the frame.
    - ppe_model (custom-trained): detects PPE items (Helmet, Vest, Boots, Gloves).

    A person without an overlapping Helmet or Vest bbox is flagged as a violation.
    """

    PERSON_CLASS = 0  # COCO person class

    # Colors (BGR)
    COLOR_SAFE = (0, 200, 0)
    COLOR_HELMET = (0, 180, 0)
    COLOR_VEST = (180, 130, 0)
    COLOR_VIOLATION = (0, 0, 255)
    COLOR_ZONE_INTRUSION = (0, 165, 255)

    # IoU threshold to consider PPE as "belonging" to a person
    OVERLAP_THRESHOLD = 0.3

    def __init__(self, ppe_model_path='ppe_best.pt', person_model_path='yolov8n.pt', confidence=0.45):
        self.person_model = YOLO(person_model_path)
        self.ppe_model = YOLO(ppe_model_path)
        self.confidence = confidence
        self.violation_cooldown = {}
        self.cooldown_seconds = 3
        self.grid_size = 80  # bucket bbox positions to this grid to absorb jitter

        # Map PPE model class names to normalized names
        self.ppe_class_map = {}
        for cls_id, name in self.ppe_model.names.items():
            self.ppe_class_map[cls_id] = name

    def detect(self, frame):
        """Run both models on the frame. Returns (persons, ppe_items) lists."""
        # Detect persons with COCO model
        person_results = self.person_model(frame, conf=self.confidence, classes=[0], verbose=False)
        persons = []
        if person_results and person_results[0].boxes is not None:
            for box in person_results[0].boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                persons.append({
                    'class_id': 0,
                    'class_name': 'person',
                    'confidence': float(box.conf[0]),
                    'bbox': (x1, y1, x2, y2),
                    'center': ((x1 + x2) // 2, (y1 + y2) // 2)
                })

        # Detect PPE items with custom model
        ppe_results = self.ppe_model(frame, conf=self.confidence, verbose=False)
        ppe_items = []
        if ppe_results and ppe_results[0].boxes is not None:
            for box in ppe_results[0].boxes:
                cls_id = int(box.cls[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                ppe_items.append({
                    'class_id': cls_id,
                    'class_name': self.ppe_class_map.get(cls_id, 'unknown'),
                    'confidence': float(box.conf[0]),
                    'bbox': (x1, y1, x2, y2),
                    'center': ((x1 + x2) // 2, (y1 + y2) // 2)
                })

        return persons, ppe_items

    def _bbox_overlap(self, bbox_a, bbox_b):
        """Check if bbox_b overlaps with bbox_a (is PPE inside/near the person bbox)."""
        ax1, ay1, ax2, ay2 = bbox_a
        bx1, by1, bx2, by2 = bbox_b

        # Intersection
        ix1 = max(ax1, bx1)
        iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2)
        iy2 = min(ay2, by2)

        if ix1 >= ix2 or iy1 >= iy2:
            return 0.0

        intersection = (ix2 - ix1) * (iy2 - iy1)
        area_b = (bx2 - bx1) * (by2 - by1)

        if area_b == 0:
            return 0.0

        # What fraction of the PPE item overlaps with the person
        return intersection / area_b

    def check_ppe_violations(self, persons, ppe_items):
        """Check which persons are missing helmets or vests."""
        violations = []

        helmets = [p for p in ppe_items if p['class_name'].lower() == 'helmet']
        vests = [p for p in ppe_items if p['class_name'].lower() == 'vest']

        for person in persons:
            has_helmet = any(
                self._bbox_overlap(person['bbox'], h['bbox']) > self.OVERLAP_THRESHOLD
                for h in helmets
            )
            has_vest = any(
                self._bbox_overlap(person['bbox'], v['bbox']) > self.OVERLAP_THRESHOLD
                for v in vests
            )

            if not has_helmet:
                violations.append({**person, 'violation_type': 'No Helmet'})
            if not has_vest:
                violations.append({**person, 'violation_type': 'No Safety Vest'})

        return violations

    def make_violation_key(self, violation_type, bbox):
        """Create a grid-bucketed key so small bbox shifts don't bypass cooldown."""
        cx = (bbox[0] + bbox[2]) // 2
        cy = (bbox[1] + bbox[3]) // 2
        gx = cx // self.grid_size
        gy = cy // self.grid_size
        return f"{violation_type}_{gx}_{gy}"

    def should_alert(self, violation_key):
        """Rate-limit alerts to avoid spamming the same violation."""
        now = time.time()
        # Clean up old entries
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
        """Save a violation screenshot and return the relative path."""
        os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        filename = f'{violation_type.replace(" ", "_")}_{timestamp}.jpg'
        filepath = os.path.join(SCREENSHOTS_DIR, filename)
        cv2.imwrite(filepath, frame)
        return f'screenshots/{filename}'

    def annotate_frame(self, frame, persons, ppe_items, violations, zone_violations=None):
        """Draw bounding boxes and labels on the frame."""
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

        # Draw detected PPE items (small labels)
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
        """Draw a text label with a background rectangle."""
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.55
        thickness = 2
        (w, h), _ = cv2.getTextSize(text, font, scale, thickness)
        y = max(y, h + 5)
        cv2.rectangle(frame, (x, y - h - 5), (x + w + 5, y + 5), color, -1)
        cv2.putText(frame, text, (x + 2, y), font, scale, (255, 255, 255), thickness)
