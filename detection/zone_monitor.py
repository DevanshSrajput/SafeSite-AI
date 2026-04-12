import json
import os
import numpy as np
from shapely.geometry import Point, Polygon

ZONES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'zones', 'zones.json')


class ZoneMonitor:
    def __init__(self):
        self.zones = []
        self.load_zones()

    def load_zones(self):
        """Load zone definitions from zones.json."""
        try:
            with open(ZONES_FILE, 'r') as f:
                data = json.load(f)
                self.zones = data.get('zones', [])
        except (FileNotFoundError, json.JSONDecodeError):
            self.zones = []

    def save_zones(self):
        """Save current zone definitions to zones.json."""
        os.makedirs(os.path.dirname(ZONES_FILE), exist_ok=True)
        with open(ZONES_FILE, 'w') as f:
            json.dump({'zones': self.zones}, f, indent=2)

    def add_zone(self, name, points, color='#FF0000'):
        """Add a new restricted zone. Points is a list of [x, y] pairs."""
        zone = {
            'name': name,
            'points': points,
            'color': color
        }
        self.zones.append(zone)
        self.save_zones()
        return zone

    def remove_zone(self, name):
        """Remove a zone by name."""
        self.zones = [z for z in self.zones if z['name'] != name]
        self.save_zones()

    def clear_zones(self):
        """Remove all zones."""
        self.zones = []
        self.save_zones()

    def check_intrusions(self, detections):
        """
        Check if any detected person's center point falls within a restricted zone.
        Returns a list of intrusion violations.
        """
        intrusions = []

        if not self.zones:
            return intrusions

        for detection in detections:
            if detection.get('class_id') != 0:  # only check persons
                continue

            cx, cy = detection['center']
            point = Point(cx, cy)

            for zone in self.zones:
                poly_points = zone['points']
                if len(poly_points) < 3:
                    continue

                polygon = Polygon(poly_points)
                if polygon.contains(point):
                    intrusions.append({
                        **detection,
                        'violation_type': 'Zone Intrusion',
                        'zone_name': zone['name']
                    })

        return intrusions

    def get_zones_for_drawing(self):
        """Return zones formatted for the frontend canvas overlay."""
        return self.zones

    def draw_zones_on_frame(self, frame):
        """Draw zone polygons on a video frame using OpenCV."""
        import cv2

        for zone in self.zones:
            points = zone['points']
            if len(points) < 3:
                continue

            pts = np.array(points, dtype=np.int32).reshape((-1, 1, 2))

            # Parse hex color to BGR
            hex_color = zone.get('color', '#FF0000').lstrip('#')
            r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
            bgr_color = (b, g, r)

            # Semi-transparent overlay
            overlay = frame.copy()
            cv2.fillPoly(overlay, [pts], bgr_color)
            cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)

            # Draw zone border
            cv2.polylines(frame, [pts], True, bgr_color, 2)

            # Label the zone
            cx = int(np.mean([p[0] for p in points]))
            cy = int(np.mean([p[1] for p in points]))
            cv2.putText(frame, zone['name'], (cx - 30, cy),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        return frame
