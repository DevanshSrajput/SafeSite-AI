import threading
import queue
import time


class VoiceAlertSystem:
    """Bilingual (English + Hindi) voice alert system using pyttsx3.

    Runs TTS on a dedicated daemon thread with a fresh engine per batch
    to avoid the pyttsx3 Windows hang bug. Queue is bounded and alerts
    have a per-type cooldown to prevent spam.
    """

    HINDI_TRANSLATIONS = {
        'No Helmet': 'हेलमेट नहीं पहना है',
        'No Safety Vest': 'सेफ्टी जैकेट नहीं पहनी है',
        'Zone Intrusion': 'प्रतिबंधित क्षेत्र में प्रवेश',
    }

    def __init__(self, enabled=True, rate=155, max_queue_size=2):
        self.enabled = enabled
        self.rate = rate
        self.alert_queue = queue.Queue(maxsize=max_queue_size)
        self._running = True
        self._last_alert = {}
        self._alert_cooldown = 8  # seconds between same alert type spoken aloud
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _speak(self, message):
        """Create a fresh pyttsx3 engine, speak, then dispose.

        A fresh engine per call avoids the COM / run-loop hang that
        pyttsx3 hits on Windows when the engine is reused across many
        runAndWait() cycles.
        """
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty('rate', self.rate)
            engine.setProperty('volume', 1.0)
            engine.say(message)
            engine.runAndWait()
            engine.stop()
        except Exception:
            pass

    def _worker(self):
        """Background worker that processes TTS alerts from the queue."""
        while self._running:
            try:
                message = self.alert_queue.get(timeout=1.0)
                if message is None:
                    break
                self._speak(message)
            except queue.Empty:
                continue

    def alert(self, violation_type, zone_name=''):
        """Queue a bilingual voice alert for a violation."""
        if not self.enabled:
            return

        # Per-type cooldown — same violation type won't speak again for N seconds
        now = time.time()
        alert_key = f"{violation_type}_{zone_name}"
        if alert_key in self._last_alert:
            if now - self._last_alert[alert_key] < self._alert_cooldown:
                return
        self._last_alert[alert_key] = now

        # Drop if queue is full — don't pile up stale announcements
        if self.alert_queue.full():
            # Drain the queue so only the freshest alert plays
            try:
                while not self.alert_queue.empty():
                    self.alert_queue.get_nowait()
            except queue.Empty:
                pass

        # English message
        if zone_name:
            en_msg = f"Warning. {violation_type} detected in {zone_name}."
        else:
            en_msg = f"Warning. {violation_type} detected."

        # Hindi message
        hi_violation = self.HINDI_TRANSLATIONS.get(violation_type, violation_type)
        if zone_name:
            hi_msg = f"चेतावनी। {zone_name} में {hi_violation}।"
        else:
            hi_msg = f"चेतावनी। {hi_violation}।"

        full_message = f"{en_msg} ... {hi_msg}"
        try:
            self.alert_queue.put_nowait(full_message)
        except queue.Full:
            pass

    def shutdown(self):
        self._running = False
        self.alert_queue.put(None)
        self._thread.join(timeout=3)

    def set_enabled(self, enabled):
        self.enabled = enabled
