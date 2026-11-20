#!/usr/bin/env python3
"""Architecture diagram for the Reachy voice assistant (built, not target).

    python diagrams/render_architecture.py   ->  ../architecture.png

Everything drawn here exists in the code today:
  * the local pipecat app (app.py / src/voicebot) owns mic+speaker via
    LocalAudioTransport and calls three AWS services;
  * the ReachyDriver frame processor drives a Reachy Mini (sim or real).
Read the emitted PNG after every change (see the architecture-diagram skill).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from diagram_lib import CAT, Edge, Node, Spec, Zone, render  # noqa: E402

# Columns encode the trust boundary: cols 0-1 = the local machine (laptop),
# col 2 = AWS Cloud. Rows stack the three AWS services on the right.
NODES = {
    "USER":   Node(0, 1, "user.png", "Person", "speaks & listens", "user"),
    "APP":    Node(1, 1, "> _", "pipecat app (app.py)",
                   "LocalAudioTransport + Silero VAD", "compute"),
    "DRIVER": Node(1, 2, "RD", "ReachyDriver",
                   "FrameProcessor: speech -> motion", "compute"),
    "ROBOT":  Node(0, 2, "RM", "Reachy Mini",
                   "MuJoCo sim OR USB robot (localhost daemon)", "network"),

    "STT":    Node(2, 0, "transcribe.png", "Amazon Transcribe",
                   "streaming speech-to-text", "ml"),
    "LLM":    Node(2, 1, "bedrock.png", "Amazon Bedrock",
                   "LLM - Claude Sonnet 4.5 (default)", "ml"),
    "TTS":    Node(2, 2, "polly.png", "Amazon Polly",
                   "text-to-speech (child voice)", "ml"),
}

# Labels are numbered to trace ONE conversation turn in order (1 -> 10). Each AWS
# service is a request/response round trip, so it gets a forward and a return
# arrow (bowed apart with `curve` so they don't overlap).
EDGES = [
    Edge("USER", "APP", "1. speaks (mic)", nudge_y=0.16),

    Edge("APP", "STT", "2. stream audio", curve=0.16, nudge_y=0.20),
    Edge("STT", "APP", "3. transcript", curve=0.16, nudge_x=-0.30, nudge_y=-0.30),

    Edge("APP", "LLM", "4. transcript as context", curve=0.14, nudge_y=0.20),
    Edge("LLM", "APP", "5. reply text", curve=0.14, nudge_y=-0.28),

    Edge("APP", "TTS", "6. reply text", curve=-0.16, nudge_y=0.20),
    Edge("TTS", "APP", "7. speech audio", curve=-0.16, nudge_x=-0.10, nudge_y=-0.30),

    Edge("APP", "USER", "8. replies (speaker)", curve=-0.32, nudge_y=-0.34),

    # 9 & 10 run alongside 6-8: the driver reacts to the bot's speaking frames.
    Edge("APP", "DRIVER", "9. speech / turn frames", nudge_x=0.70),
    Edge("DRIVER", "ROBOT", "10. poses, nod, emotions", nudge_y=0.14),
]

ZONES = [
    Zone(["USER", "APP", "DRIVER", "ROBOT"], "Local machine (laptop)",
         CAT["compute"], pad=0.42, dash=(0, (6, 4))),
    Zone(["STT", "LLM", "TTS"], "AWS Cloud  ·  us-west-2",
         "#232f3e", pad=0.42, dash=(0, (7, 4))),
]

SPEC = Spec(
    title="Reachy voice assistant - component architecture (built)",
    subtitle="All-AWS speech pipeline on pipecat, driving a Reachy Mini robot",
    nodes=NODES,
    edges=EDGES,
    zones=ZONES,
    inside_cols={2},
    icon_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons"),
    cx={0: 2.1, 1: 6.3, 2: 11.2},
    cy={0: 6.5, 1: 4.2, 2: 1.9},
    # Arrow colour follows its SOURCE component (the library tints each edge with
    # the source tile's category colour). Spell that out so it is not read as a
    # hidden meaning.
    legend=[
        ("solid", CAT["compute"], "sent by the pipecat app (request / audio out / robot command)"),
        ("solid", CAT["ml"], "returned by an AWS service (transcript / reply / speech)"),
        ("solid", CAT["user"], "spoken by the person (mic in)"),
    ],
    note=(
        "Notes:\n"
        "•  The numbers on the arrows (1-10) trace a single conversation turn in order; "
        "each AWS service has a request arrow and a return arrow.\n"
        "•  Arrow colour = the component the arrow leaves (see legend): orange = the "
        "pipecat app, teal = an AWS service returning data, dark = the person.\n"
        "•  The pipecat app runs on the laptop and owns the microphone and speaker "
        "(LocalAudioTransport); Silero VAD detects end-of-turn.\n"
        "•  Amazon Transcribe, Bedrock, and Polly are the only cloud dependencies — "
        "audio and text stream to AWS and back; no persistent AWS resources are created.\n"
        "•  The LLM is swappable in config.yaml (Claude Sonnet 4.5 default; Nova, Opus 4.8, "
        "Grok, and OpenAI options documented there).\n"
        "•  ReachyDriver observes speaking/turn frames and drives the Reachy Mini — the same "
        "code targets the MuJoCo simulator or a real USB robot (decided by which daemon runs)."
    ),
)

if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "architecture.png")
    raise SystemExit(render(SPEC, out))
