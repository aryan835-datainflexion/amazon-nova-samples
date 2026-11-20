"""Tests for the hardware-free robot pieces.

These exercise :class:`~voicebot.robot.fake.FakeReachy` and the
:func:`~voicebot.robot.make_robot` factory. They require no pipecat, no
reachy-mini SDK, and no AWS access.
"""

from __future__ import annotations

from voicebot.config import config_from_dict
from voicebot.robot import Robot, make_robot
from voicebot.robot.fake import FakeReachy


def test_fake_records_poses() -> None:
    robot = FakeReachy()
    robot.pose("listening")
    robot.pose("thinking", duration=0.25)

    assert robot.poses == [("listening", 0.5), ("thinking", 0.25)]


def test_fake_records_nods() -> None:
    robot = FakeReachy()
    assert robot.nods == 0
    robot.nod()
    robot.nod()
    assert robot.nods == 2


def test_fake_records_emotions() -> None:
    robot = FakeReachy()
    robot.play_emotion("welcoming1")
    robot.play_emotion("confused1", sound=False)

    assert robot.emotions == ["welcoming1", "confused1"]


def test_fake_lists_emotions() -> None:
    robot = FakeReachy()
    assert robot.list_emotions() == [
        "welcoming1",
        "confused1",
        "mini-deep-sleep",
        "curious1",
    ]


def test_fake_close() -> None:
    robot = FakeReachy()
    assert robot.closed is False
    robot.close()
    assert robot.closed is True


def test_make_robot_returns_fake_backend() -> None:
    cfg = config_from_dict({"robot": {"backend": "fake"}})
    robot = make_robot(cfg)

    assert isinstance(robot, FakeReachy)
    # The Protocol is runtime_checkable, so structural conformance is testable.
    assert isinstance(robot, Robot)


def test_make_robot_unknown_backend_raises() -> None:
    cfg = config_from_dict({"robot": {"backend": "nope"}})
    try:
        make_robot(cfg)
    except ValueError:
        pass
    else:  # pragma: no cover - the factory must reject unknown backends
        raise AssertionError("make_robot should raise ValueError for unknown backend")
