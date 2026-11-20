"""The robot contract shared by the real Reachy wrapper, the fake, and the
pipecat frame processor that drives them.

Design rules every implementation MUST follow:

* Every method is **non-blocking** and **best-effort**. Motion/emotion calls
  dispatch work to a background thread and return immediately, so they are safe
  to call from pipecat's asyncio event loop. They must never raise: a robot that
  is missing, disconnected, or mid-move should degrade silently (logged at most).
* Head angles in :data:`POSES` are in **degrees**; antennas are ``[left, right]``
  in **radians** (this matches the reachy-mini ``create_head_pose`` /
  ``goto_target`` API).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

# Named target poses. head: kwargs for create_head_pose (degrees);
# antennas: [left, right] in radians.
POSES: dict[str, dict] = {
    "neutral": {"head": {}, "antennas": [0.0, 0.0]},
    "listening": {"head": {"pitch": -6}, "antennas": [0.5, -0.5]},  # perked up
    "thinking": {"head": {"roll": 14}, "antennas": [0.1, -0.6]},  # quizzical tilt
    "speaking": {"head": {"pitch": -2}, "antennas": [0.35, 0.35]},  # lively, attentive
    "asleep": {"head": {"pitch": 20}, "antennas": [1.1, -1.1]},  # drooped
}


@runtime_checkable
class Robot(Protocol):
    """Minimal robot surface used by the voice assistant."""

    def pose(self, name: str, duration: float = 0.5) -> None:
        """Move to a named pose from :data:`POSES` over ``duration`` seconds."""

    def nod(self) -> None:
        """A single brief acknowledging nod."""

    def play_emotion(self, name: str, sound: bool = True) -> None:
        """Play a recorded emotion-library move by name (best-effort)."""

    def list_emotions(self) -> list[str]:
        """Return available emotion-move names (empty list if unavailable)."""

    def close(self) -> None:
        """Release the robot/daemon connection."""
