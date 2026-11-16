"""Robot layer: the :class:`Robot` contract plus a backend factory.

Import this package to pick a robot backend from configuration without pulling
in the reachy-mini SDK unless it is actually needed -- the real backend is
imported lazily inside :func:`make_robot`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import POSES, Robot

if TYPE_CHECKING:  # avoid a runtime import cycle / heavy import at module load
    from voicebot.config import Config

__all__ = ["POSES", "Robot", "make_robot"]


def make_robot(cfg: "Config") -> Robot:
    """Return a robot backend selected by ``cfg.robot.backend``.

    * ``"fake"``   -> :class:`~voicebot.robot.fake.FakeReachy` (no hardware).
    * ``"reachy"`` -> :class:`~voicebot.robot.reachy.ReachyRobot` (SDK).

    Any other value raises :class:`ValueError`. The reachy-mini-backed class is
    imported lazily so this module stays importable without the SDK installed.
    """

    backend = cfg.robot.backend
    if backend == "fake":
        from .fake import FakeReachy

        return FakeReachy()
    if backend == "reachy":
        from .reachy import ReachyRobot

        return ReachyRobot(gestures_enabled=cfg.robot.gestures)
    raise ValueError(f"Unknown robot backend: {backend!r}")
