import threading
import queue
import pyttsx3
import time


class VoiceAlertSystem:
    """Bilingual (English + Hindi) voice alert system using pyttsx3.

    Runs TTS on a dedicated daemon thread with a queue so it never
    blocks the video pipeline.
    """

    HINDI_TRANSLATIONS = {
        'No Helmet': 'हेलमेट नहीं पहना है',
        'No Safety Vest': 'सेफ्टी जैकेट नहीं पहनी है',
        'Zone Intrusion': 'प्रतिबंधित क्षेत्र में प्रवेश',
    }

    def __init__(self, enabled=True, rate=160, max_queue_size=3):
        self.enabled = enabled
        self.rate = rate
        self.max_queue_size = max_queue_size
        self.alert_queue = queue.Queue(maxsize=max_queue_size)
        self._running = True
        self._last_alert = {}
        self._alert_cooldown = 5  # seconds between same alert type
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _create_engine(self):
        """Create a fresh pyttsx3 engine (must be done in the worker thread)."""
        engine = pyttsx3.init()
        engine.setProperty('rate', self.rate)
        engine.setProperty('volume', 1.0)
        return engine

    def _worker(self):
        """Background worker that processes TTS alerts from the queue."""
        engine = self._create_engine()

        while self._running:
            try:
                message = self.alert_queue.get(timeout=1.0)
                if message is None:  # shutdown sentinel
                    break
                try:
                    engine.say(message)
                    engine.runAndWait()
                except Exception:
                    # pyttsx3 can occasionally error; recreate engine
                    try:
                        engine = self._create_engine()
                    except Exception:
                        pass
            except queue.Empty:
                continue

    def alert(self, violation_type, zone_name=''):
        """Queue a bilingual voice alert for a violation."""
        if not self.enabled:
            return

        # Per-type cooldown so the same alert doesn't repeat too fast
        now = time.time()
        alert_key = f"{violation_type}_{zone_name}"
        if alert_key in self._last_alert:
            if now - self._last_alert[alert_key] < self._alert_cooldown:
                return
        self._last_alert[alert_key] = now

        # Drop alert if queue is full (don't pile up stale announcements)
        if self.alert_queue.full():
            return

        # English alert
        if zone_name:
            en_msg = f"Warning. {violation_type} detected in {zone_name}."
        else:
            en_msg = f"Warning. {violation_type} detected."

        # Hindi alert
        hi_violation = self.HINDI_TRANSLATIONS.get(violation_type, violation_type)
        if zone_name:
            hi_msg = f"चेतावनी। {zone_name} में {hi_violation}।"
        else:
            hi_msg = f"चेतावनी। {hi_violation}।"

        full_message = f"{en_msg} ... {hi_msg}"
        self.alert_queue.put_nowait(full_message)

    def shutdown(self):
        """Stop the worker thread."""
        self._running = False
        self.alert_queue.put(None)  # sentinel
        self._thread.join(timeout=3)

    def set_enabled(self, enabled):
        self.enabled = enabled
