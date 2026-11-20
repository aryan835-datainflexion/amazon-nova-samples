---
name: reachy-voice-assistant
description: Set up, run, and troubleshoot the all-AWS Reachy Mini voice assistant in text-to-speech/use-cases/reachy-voice-assistant (Amazon Transcribe STT -> Amazon Bedrock LLM -> Amazon Polly TTS, wired with pipecat, driving a Reachy Mini simulator or real robot). Use when asked to install, configure, launch, smoke-test, or debug this voice assistant / voice robot; when a run fails with no audio, AccessDeniedException, mjpython errors, echo loops, or credential/model-access problems; or when changing its Polly voice, Bedrock model, robot backend, or pipeline code.
---

# Reachy voice assistant

This is a spoken voice assistant on a Reachy Mini desk robot (real USB robot,
MuJoCo simulator, or an in-process fake). The project lives at
`text-to-speech/use-cases/reachy-voice-assistant/` (paths below are relative to
the `text-to-speech` folder). Its `README.md` is the authority for commands,
and `config.yaml` is the authority for default settings. Read both before
making deep changes.

Pipeline: `mic → Transcribe → user aggregator (Silero VAD) → Bedrock → Polly →
speaker → ReachyDriver` (robot poses, nods, emotions). English only. It uses
pay-per-use APIs and creates no AWS resources.

## 1. Golden rules (most failures come from these)

- **Use a plain pip `venv` on Python 3.11 or 3.12, never `uv`.** `uv`'s managed
  interpreters aren't macOS framework builds, which breaks MuJoCo's `mjpython`
  simulator GUI. `pyproject.toml` requires `>=3.11,<3.13`, and the system
  Python may be too new.
- **Install dependencies only from `requirements.txt` / `requirements-dev.txt`.**
  Don't add one-off `pip install X` steps or list dependencies in
  `pyproject.toml`; that file is packaging metadata only
  (`pip install -e . --no-deps` puts `voicebot` on the import path).
- **Install PortAudio before PyAudio** (macOS: `brew install portaudio`).
- **Nova Sonic is out of scope.** It's speech-to-speech and would replace
  Transcribe and Polly. The LLM here is a Bedrock text model.

## 2. Workflow

Run everything from `use-cases/reachy-voice-assistant/`, with the virtual
environment there activated. Commands run in separate shells don't keep
`cd` or `source .venv/bin/activate`, so repeat them in each one.

1. **Set up:** create the venv with Python 3.11/3.12 and run
   `pip install -r requirements.txt`. Add `requirements-dev.txt` for tests and
   the notebook.
2. **Run offline checks** (no AWS, robot, or audio needed):
   `PYTHONPATH=src pytest`, then `python app.py --check` (imports, resolved
   Region/model/voice/backend, whether credentials are present).
3. **Check AWS access** (read-only first):
   `aws sts get-caller-identity`. Then confirm that **Bedrock model access**
   is enabled for `llm.model_id` in the configured Region. A single short
   `aws bedrock-runtime converse` call is a cheap billed check. Ask before
   making it.
4. **Smoke-test with the fake robot:** `python app.py --robot fake`. This tests
   the full speech loop with the local mic and speaker and needs no daemon.
   Tell the user charges run continuously while it's running (the mic and the
   Transcribe stream stay open). Stop it with `Ctrl+C`.
5. **Add a robot:** start one daemon in its own terminal, then run
   `python app.py --robot reachy` in another:
   - Real Reachy Mini Lite (USB): `reachy-mini-daemon` (plain Python; add
     `-p /dev/cu.usbmodem<serial>` if auto-detection fails). The first
     connection may reflash motor firmware. Don't unplug it while that runs.
   - Simulator: `mjpython -m reachy_mini.daemon.app.main --sim --scene minimal`.

The README's walkthrough notebook (`walkthrough.ipynb`) is an optional guided
path through the same checks.

## 3. Configuration

Edit `config.yaml`. The environment variables `AWS_REGION`,
`BEDROCK_MODEL_ID`, `POLLY_VOICE`, `ROBOT_BACKEND`, and `LOG_LEVEL` override it.
An exported `AWS_REGION` silently overrides the file.

- **Voice:** set `tts.style` (`child`, `expressive`, `adult_female`,
  `adult_male`) to use a preset, or leave it `null` and set
  `tts.voice`/`engine`/`pitch`/`rate` yourself. Pitch works only on the
  standard engine; generative rejects it. The youngest-sounding voices need
  standard + pitch, which is less expressive, so it's a trade-off.
- **Model:** `llm.model_id`. Alternatives are listed in `config.yaml`, and some
  require `temperature: null`. `latency: null` is the safe default; some
  model/Region pairs reject `performanceConfig`. Enable model access before
  switching.
- **Robot:** `robot.backend` (`reachy|fake`), `robot.gestures`,
  `robot.emotion_sound`, `robot.emotions.*`.
- **Turn-taking:** `vad.stop_secs`.
- **Audio:** `audio.mic` (`reachy|laptop`). `audio.input_device_index` /
  `output_device_index` pin exact devices and take priority over `audio.mic`.
  Replies always play through the robot's speaker unless the output device is
  pinned.

## 4. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `AccessDeniedException` from Bedrock | Enable model access for that model in the configured Region; grant both the inference-profile and the foundation-model ARNs |
| Assistant answers itself / loops | Acoustic echo. The pipeline mutes the mic while the robot speaks; check that the mute strategy wasn't removed. Headphones alone don't help, because output goes to the robot's speaker |
| Robot mic picks up speech poorly | Known weakness of the robot's mic array: set `audio.mic: laptop` |
| No or garbled audio, device errors | Check that PortAudio is installed; read the `Audio devices: …` startup log line; pin device indices |
| PortAudio can't open the robot's sound card (Lite) | The daemon holds it: `reachy-mini-daemon --no-media`, or `robot.emotion_sound: false` |
| `mjpython: command not found` / sim GUI won't open | You're in a `uv` environment; recreate the venv with `python3.12 -m venv` |
| `No module named 'aiobotocore'` / `'pyaudio'` | Run `pip install -r requirements.txt` in the right venv |
| Audio works but the robot doesn't move | Check the daemon is running (UI at <http://localhost:8000>). The driver is best-effort and swallows robot errors by design |

## 5. Editing the code

- pipecat wiring: `src/voicebot/pipeline.py`. Robot mapping:
  `src/voicebot/robot/controller.py`. SDK wrapper: `src/voicebot/robot/reachy.py`.
- The code targets **pipecat 1.7's** universal context API (`LLMContext` +
  `LLMContextAggregatorPair`, VAD on the user aggregator, `settings=` objects,
  submodule imports like `pipecat.services.aws.stt`). Don't revert to pre-1.0
  patterns.
- `ReachyDriver` must stay **after** `transport.output()`, because only
  downstream processors see `BotStartedSpeakingFrame` / `BotStoppedSpeakingFrame`.
- Run `PYTHONPATH=src pytest` and `python app.py --check` after every change.

## 6. Cleanup

Nothing persistent is created in AWS. Stop the app and daemon (`Ctrl+C`).
Remove the venv with `rm -rf .venv` (after `deactivate`) if asked.
