"""A pipecat frame processor that drives the robot from pipeline events.

:class:`ReachyDriver` observes frames flowing through a pipecat pipeline and
translates the interesting ones into (non-blocking) robot poses and emotion
moves. It never consumes or mutates frames: every frame it sees is pushed
downstream unchanged.

Placement matters. This processor MUST be placed AFTER ``transport.output()``
in the pipeline. ``BotStartedSpeakingFrame`` / ``BotStoppedSpeakingFrame`` are
emitted by the output transport and are therefore only visible downstream of
it; a driver placed before the output would never see the bot's speaking
state. User/transcription frames (``UserStartedSpeakingFrame`` etc.) flow
through from upstream, so they remain visible at that later position too.
"""

from __future__ import annotations

import logging

from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.frames.frames import (
    StartFrame, EndFrame, CancelFrame, ErrorFrame,
    UserStartedSpeakingFrame, UserStoppedSpeakingFrame,
    BotStartedSpeakingFrame, BotStoppedSpeakingFrame,
)

from voicebot.robot.base import Robot
from voicebot.config import EmotionConfig

logger = logging.getLogger(__name__)


class ReachyDriver(FrameProcessor):
    """Observe pipeline frames and drive the robot; pass frames through."""

    def __init__(
        self,
        robot: Robot,
        emotions: EmotionConfig,
        gestures: bool = True,
        emotion_sound: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._robot = robot
        self._emotions = emotions
        self._gestures = gestures
        # Whether emotion moves play their own recorded audio. Off by default so
        # the move's clip does not overlap Polly's speech (e.g. the greeting).
        self._emotion_sound = emotion_sound

    def handle_frame(self, frame) -> None:
        """Map a single frame to robot motion (best-effort, never raises).

        This is intentionally synchronous and free of pipecat push machinery so
        it can be unit-tested directly. The robot methods are themselves
        non-blocking, so calling them from here is safe.
        """

        try:
            if isinstance(frame, StartFrame):
                self._robot.nod()
                if self._gestures and self._emotions.on_start:
                    # Motion only at startup: this emotion fires at the same time
                    # as Polly's spoken greeting, so playing its recorded audio
                    # clip here would talk over the greeting. Other emotions
                    # (error/sleep) still honor emotion_sound below.
                    self._robot.play_emotion(self._emotions.on_start, sound=False)
            elif isinstance(frame, UserStartedSpeakingFrame):
                self._robot.pose("listening")
            elif isinstance(frame, UserStoppedSpeakingFrame):
                self._robot.pose("thinking")
            elif isinstance(frame, BotStartedSpeakingFrame):
                self._robot.pose("speaking")
            elif isinstance(frame, BotStoppedSpeakingFrame):
                self._robot.pose("neutral")
            elif isinstance(frame, ErrorFrame):
                if self._gestures and self._emotions.on_error:
                    self._robot.play_emotion(self._emotions.on_error, sound=self._emotion_sound)
            elif isinstance(frame, (EndFrame, CancelFrame)):
                if self._gestures and self._emotions.on_sleep:
                    self._robot.play_emotion(self._emotions.on_sleep, sound=self._emotion_sound)
                self._robot.pose("asleep")
        except Exception:  # best-effort: a robot cue must never break the pipeline
            logger.exception("ReachyDriver failed to handle frame %r", frame)

    async def process_frame(self, frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)  # required first
        self.handle_frame(frame)
        await self.push_frame(frame, direction)  # pass through unchanged
