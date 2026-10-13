from collections import deque
import time

IGNORED = {"NONE", "UNKNOWN"}


class Stabilizer:
    """Temporal debouncing for discrete gesture events.

    * A gesture must be seen on N consecutive confident frames before it fires.
    * NONE / UNKNOWN / low-confidence frames never fire anything.
    * LATCH: once a gesture has fired it will not fire again until it has been
      absent for `release_frames` frames (so a pinch fires ONCE per pinch, no
      matter how long it is held).
    * `stable` is the gesture that has been consistent for `release_frames`
      frames - used for continuous control (cursor / scroll / drag).
    """

    def __init__(self, frames=6, cooldown_ms=800, release_frames=3, overrides=None):
        self.frames = max(1, int(frames))
        self.cooldown = cooldown_ms / 1000
        self.release_frames = max(1, int(release_frames))
        self.overrides = dict(overrides or {})
        size = max([self.frames, self.release_frames, 3] + list(self.overrides.values())) + 2
        self.hist = deque(maxlen=size)
        self.last_trigger = -1e9
        self.latched = None
        self.stable = "NONE"

    def _need(self, g):
        return max(1, int(self.overrides.get(g, self.frames)))

    def _tail_all(self, value, n):
        if len(self.hist) < n:
            return False
        tail = list(self.hist)[-n:]
        return all(h == value for h in tail)

    def update(self, gesture, confidence, threshold, now=None):
        now = time.perf_counter() if now is None else now
        g = gesture if (confidence >= threshold and gesture not in IGNORED) else "NONE"
        self.hist.append(g)

        if self._tail_all(g, self.release_frames):
            self.stable = g
        if self.latched is not None and len(self.hist) >= self.release_frames:
            tail = list(self.hist)[-self.release_frames:]
            if all(h != self.latched for h in tail):
                self.latched = None

        event = None
        if g != "NONE" and g != self.latched and self._tail_all(g, self._need(g)) \
                and now - self.last_trigger >= self.cooldown:
            event = g
            self.latched = g
            self.last_trigger = now

        if event:
            state = "CONFIRMED"
        elif g == "NONE":
            state = "IDLE"
        elif g == self.latched:
            state = "HELD"
        else:
            state = "DETECTING"
        return event, state
