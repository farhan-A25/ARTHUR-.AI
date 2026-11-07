"""Scheduler: runs named jobs on a fixed interval in daemon threads (Builder D)."""

import threading


class Scheduler:
    def __init__(self):
        self._jobs = []
        self._stop = threading.Event()
        self._threads = []

    def schedule(self, name, interval_s, fn):
        """Register a job. Must be called before start()."""
        self._jobs.append({"name": name, "interval_s": interval_s, "fn": fn})

    def _loop(self, job):
        while not self._stop.is_set():
            try:
                job["fn"]()
            except Exception as e:  # a failing job must not kill the loop
                print("[scheduler:%s] error: %s" % (job["name"], e), flush=True)
            # Wait interruptibly so stop() returns promptly.
            self._stop.wait(job["interval_s"])

    def start(self):
        """Spawn one daemon thread per scheduled job."""
        for job in self._jobs:
            t = threading.Thread(
                target=self._loop,
                args=(job,),
                name="scheduler-%s" % job["name"],
                daemon=True,
            )
            t.start()
            self._threads.append(t)
        return self

    def stop(self):
        """Signal all job loops to exit."""
        self._stop.set()
        return self
