import time


class MetricsTracker:
    def __init__(self):
        self.start_session()

    def start_session(self):
        self.session_started_at = time.monotonic()
        self.first_done_at = None
        self.last_drift_at = None
        self.last_refocus_at = None
        self.drift_events = 0
        self.refocus_successes = 0
        self.stuck_events = 0
        self.done_events = 0

    def mark_done(self):
        self.done_events += 1
        if self.first_done_at is None:
            self.first_done_at = time.monotonic()

    def mark_stuck(self):
        self.stuck_events += 1

    def mark_drift(self):
        self.drift_events += 1
        self.last_drift_at = time.monotonic()
        self.last_refocus_at = None

    def mark_refocus(self):
        self.last_refocus_at = time.monotonic()
        if self.last_drift_at is not None:
            self.refocus_successes += 1

    def snapshot(self):
        initiation = None
        if self.first_done_at is not None:
            initiation = round(self.first_done_at - self.session_started_at, 2)

        return_time = None
        if self.last_drift_at is not None and self.last_refocus_at is not None:
            return_time = round(self.last_refocus_at - self.last_drift_at, 2)

        rate = None
        if self.drift_events:
            rate = round(self.refocus_successes / self.drift_events, 3)

        return {
            "task_initiation_latency_s": initiation,
            "return_to_task_time_s": return_time,
            "drift_events": self.drift_events,
            "refocus_successes": self.refocus_successes,
            "intervention_success_rate": rate,
            "stuck_events": self.stuck_events,
            "done_events": self.done_events,
        }
