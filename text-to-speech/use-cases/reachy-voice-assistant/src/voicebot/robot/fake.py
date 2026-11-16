"""In-process test double implementing the :class:`Robot` protocol.

``FakeReachy`` needs no hardware and imports neither reachy-mini nor pipecat, so
it is safe to use in unit tests and on CI. Instead of moving anything it simply
records every call, letting tests assert what the assistant asked the robot to
do. Every method is trivial, synchronous, and never raises.
"""

from __future__ import annotations


class FakeReachy:
    """A no-hardware robot that records the calls made against it."""

    def __init__(self) -> None:
        # Recorded calls, for test assertions.
        self.poses: list[tuple[str, float]] = []
        self.nods: int = 0
        self.emotions: list[str] = []
        self.closed: bool = False

    def pose(self, name: str, duration: float = 0.5) -> None:
        self.poses.append((name, duration))

    def nod(self) -> None:
        self.nods += 1

    def play_emotion(self, name: str, sound: bool = True) -> None:
        self.emotions.append(name)

    def list_emotions(self) -> list[str]:
        # A small, fixed catalogue mirroring the real emotion library.
        return ["welcoming1", "confused1", "mini-deep-sleep", "curious1"]

    def close(self) -> None:
        self.closed = True
