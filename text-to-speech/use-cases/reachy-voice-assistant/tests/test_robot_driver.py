"""Tests for the ReachyDriver frame processor.

These require pipecat (for the frame classes) but no AWS, real robot, or
reachy-mini. We exercise ``handle_frame`` directly with real frame instances
and assert on what the ``FakeReachy`` recorded, rather than running the pipecat
push machinery.
"""

from __future__ import annotations

from pipecat.frames.frames import (
    StartFrame, EndFrame, CancelFrame, ErrorFrame,
    UserStartedSpeakingFrame, UserStoppedSpeakingFrame,
    BotStartedSpeakingFrame, BotStoppedSpeakingFrame,
)

from voicebot.config import EmotionConfig
from voicebot.robot.controller import ReachyDriver
from voicebot.robot.fake import FakeReachy


def _driver(gestures: bool = True) -> tuple[ReachyDriver, FakeReachy]:
    robot = FakeReachy()
    emotions = EmotionConfig()  # welcoming1 / confused1 / mini-deep-sleep
    return ReachyDriver(robot, emotions, gestures=gestures), robot


def test_start_frame_nods_and_plays_welcome():
    # StartFrame has all-default fields, so it constructs with no args.
    driver, robot = _driver()
    driver.handle_frame(StartFrame())
    assert robot.nods == 1
    assert robot.emotions == ["welcoming1"]


def test_start_frame_without_gestures_only_nods():
    # gestures=False must suppress the emotion move but keep the nod.
    driver, robot = _driver(gestures=False)
    driver.handle_frame(StartFrame())
    assert robot.nods == 1
    assert robot.emotions == []


def test_user_started_speaking_listens():
    driver, robot = _driver()
    driver.handle_frame(UserStartedSpeakingFrame())  # no constructor args
    assert robot.poses == [("listening", 0.5)]


def test_user_stopped_speaking_thinks():
    driver, robot = _driver()
    driver.handle_frame(UserStoppedSpeakingFrame())  # no constructor args
    assert robot.poses == [("thinking", 0.5)]


def test_bot_started_speaking_speaks():
    driver, robot = _driver()
    driver.handle_frame(BotStartedSpeakingFrame())  # no constructor args
    assert robot.poses == [("speaking", 0.5)]


def test_bot_stopped_speaking_returns_to_neutral():
    driver, robot = _driver()
    driver.handle_frame(BotStoppedSpeakingFrame())  # no constructor args
    assert robot.poses == [("neutral", 0.5)]


def test_error_frame_plays_confused():
    # ErrorFrame requires the mandatory ``error`` string.
    driver, robot = _driver()
    driver.handle_frame(ErrorFrame(error="boom"))
    assert robot.emotions == ["confused1"]
    assert robot.poses == []


def test_end_frame_sleeps_and_droops():
    # EndFrame's only field (reason) defaults to None, so no args are needed.
    driver, robot = _driver()
    driver.handle_frame(EndFrame())
    assert robot.emotions == ["mini-deep-sleep"]
    assert robot.poses == [("asleep", 0.5)]


def test_cancel_frame_sleeps_and_droops():
    # CancelFrame's only field (reason) defaults to None.
    driver, robot = _driver()
    driver.handle_frame(CancelFrame())
    assert robot.emotions == ["mini-deep-sleep"]
    assert robot.poses == [("asleep", 0.5)]


def test_end_frame_without_gestures_only_droops():
    driver, robot = _driver(gestures=False)
    driver.handle_frame(EndFrame())
    assert robot.emotions == []
    assert robot.poses == [("asleep", 0.5)]
