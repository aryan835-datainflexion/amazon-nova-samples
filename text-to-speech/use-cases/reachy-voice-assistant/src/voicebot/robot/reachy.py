"""Real robot backend: a thin wrapper around the ``reachy-mini`` SDK.

This wrapper implements the :class:`voicebot.robot.base.Robot` protocol using
only the parts of reachy-mini that the voice assistant needs: named head/antenna
poses, a quick nod, and playback of recorded emotion-library moves. It owns
*no* audio or camera resources -- pipecat drives the microphone and speaker, so
we never call the SDK's media/recording helpers here.

Two design rules from ``base.py`` shape everything below:

* **Non-blocking:** the reachy-mini ``goto_target``/``async_play_move`` calls
  block for their whole ``duration``. To keep pipecat's asyncio loop responsive
  we push that work onto a single-worker background thread. Using one worker
  (``max_workers=1``) also serialises motions so they never fight each other.
* **Best-effort:** a missing or disconnected robot must degrade silently. Every
  worker body is wrapped in try/except and merely logged; exceptions never
  propagate back to the caller.

The reachy-mini imports are done *lazily* (inside ``__init__``/methods) so that
merely importing this module never fails on a machine without the SDK.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from voicebot.robot.base import POSES

logger = logging.getLogger(__name__)

# The published emotion-library repo used by reachy-mini's RecordedMoves.
_EMOTIONS_REPO = "pollen-robotics/reachy-mini-emotions-library"


class ReachyRobot:
    """Robot backend backed by a live ``reachy-mini`` daemon connection.

    Whether this talks to a simulator or real hardware is decided by which
    reachy-mini daemon is running locally, not by anything in this code.
    """

    def __init__(self, gestures_enabled: bool = True) -> None:
        # Import lazily so importing this module is safe without the SDK.
        from reachy_mini import ReachyMini

        # Auto-connects to the local daemon (sim vs real decided by the daemon).
        self._mini = ReachyMini()

        # Serialise all motion on a single background worker so blocking SDK
        # calls never stall the caller's event loop, and moves don't overlap.
        self._executor = ThreadPoolExecutor(max_workers=1)

        self._gestures_enabled = gestures_enabled
        # Emotion moves are loaded lazily on first use (they hit the network /
        # disk). When gestures are disabled we never load them at all.
        self._moves = None
        self._moves_loaded = False

    # -- internal helpers -------------------------------------------------

    def _submit(self, fn) -> None:
        """Dispatch ``fn`` to the background worker, best-effort.

        Even the act of submitting is guarded: once ``close()`` has shut the
        executor down, ``submit`` raises ``RuntimeError`` which we swallow.
        """

        try:
            self._executor.submit(fn)
        except Exception:  # pragma: no cover - executor already shut down
            logger.debug("Could not submit robot job (executor closed?)", exc_info=True)

    def _get_moves(self):
        """Lazily construct and cache the ``RecordedMoves`` handle.

        Returns ``None`` if gestures are disabled or the library cannot be
        loaded (best-effort: callers treat ``None`` as "no emotions").
        """

        if not self._gestures_enabled:
            return None
        if not self._moves_loaded:
            self._moves_loaded = True  # only attempt to load once
            try:
                from reachy_mini.motion.recorded_move import RecordedMoves

                self._moves = RecordedMoves(_EMOTIONS_REPO)
            except Exception:
                logger.warning("Failed to load emotion library", exc_info=True)
                self._moves = None
        return self._moves

    # -- Robot protocol ---------------------------------------------------

    def pose(self, name: str, duration: float = 0.5) -> None:
        """Move to a named pose from :data:`POSES` over ``duration`` seconds."""

        spec = POSES.get(name)
        if spec is None:
            logger.debug("Unknown pose %r; ignoring", name)
            return

        def job() -> None:
            try:
                from reachy_mini.utils import create_head_pose

                head = create_head_pose(**spec["head"], degrees=True)
                self._mini.goto_target(
                    head=head,
                    antennas=spec["antennas"],
                    duration=duration,
                )
            except Exception:
                logger.warning("pose(%r) failed", name, exc_info=True)

        self._submit(job)

    def nod(self) -> None:
        """A single brief acknowledging nod (pitch down, then back to neutral)."""

        def job() -> None:
            try:
                from reachy_mini.utils import create_head_pose

                # Dip the head forward...
                self._mini.goto_target(
                    head=create_head_pose(pitch=12, degrees=True),
                    duration=0.3,
                )
                # ...then return to neutral.
                self._mini.goto_target(
                    head=create_head_pose(),
                    duration=0.3,
                )
            except Exception:
                logger.warning("nod() failed", exc_info=True)

        self._submit(job)

    def play_emotion(self, name: str, sound: bool = True) -> None:
        """Play a recorded emotion-library move by name (best-effort)."""

        # No-op entirely when gestures are disabled.
        if not self._gestures_enabled:
            return

        def job() -> None:
            try:
                moves = self._get_moves()
                if moves is None:
                    return
                move = moves.get(name)
                if move is None:  # unknown/missing move -> swallow
                    logger.debug("Unknown emotion move %r; ignoring", name)
                    return
                # async_play_move is a coroutine; run it to completion here on
                # the worker thread (which has no running event loop).
                asyncio.run(self._mini.async_play_move(move, sound=sound))
            except Exception:
                logger.warning("play_emotion(%r) failed", name, exc_info=True)

        self._submit(job)

    def list_emotions(self) -> list[str]:
        """Return available emotion-move names (empty list if unavailable)."""

        try:
            moves = self._get_moves()
            if moves is None:
                return []
            return list(moves.list_moves())
        except Exception:
            logger.debug("list_emotions() failed", exc_info=True)
            return []

    def close(self) -> None:
        """Release the robot/daemon connection and stop the worker thread."""

        try:
            # Stop accepting new jobs and let any in-flight motion finish.
            self._executor.shutdown(wait=True)
        except Exception:
            logger.debug("Executor shutdown failed", exc_info=True)
        try:
            self._mini.__exit__(None, None, None)
        except Exception:
            logger.debug("ReachyMini teardown failed", exc_info=True)
