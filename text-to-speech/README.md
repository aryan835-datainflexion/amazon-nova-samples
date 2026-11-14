# Text-to-speech with Amazon Polly

Amazon Polly is a fully managed service that turns text into lifelike speech.
You can use it to add spoken content to applications, create audio from
articles, improve accessibility, and build voice-enabled experiences.

This folder contains Python examples to help you make your first Amazon Polly
request and explore capabilities such as voices, SSML, speech marks, lexicons,
asynchronous synthesis, and bidirectional streaming. If you are new to Amazon
Polly, start with the guided quickstart and then explore the focused feature
examples.

## Explore the samples

### [Getting started](getting-started/)

A guided quickstart that discovers voices compatible with a selected speech
engine, validates the chosen voice, synthesizes text, and saves the audio.

### [Features](features/)

Focused examples of individual Amazon Polly capabilities:

| Example | APIs covered |
| --- | --- |
| [01-synthesize-speech](features/01-synthesize-speech/) | `SynthesizeSpeech` |
| [02-describe-voices](features/02-describe-voices/) | `DescribeVoices` |
| [03-voice-control-ssml](features/03-voice-control-ssml/) | `SynthesizeSpeech` with SSML |
| [04-speech-marks](features/04-speech-marks/) | `SynthesizeSpeech` with speech marks |
| [05-lexicons](features/05-lexicons/) | `PutLexicon`, `GetLexicon`, `ListLexicons`, `DeleteLexicon` |
| [06-async-synthesis](features/06-async-synthesis/) | `StartSpeechSynthesisTask`, `GetSpeechSynthesisTask`, `ListSpeechSynthesisTasks` |
| [07-bidi-streaming](features/07-bidi-streaming/) | `StartSpeechSynthesisStream` using the experimental AWS SDK for Python |

## Prerequisites

- An AWS account with Amazon Polly permissions
- Configured AWS credentials and an AWS Region
- Python 3.10 or later for most examples

The bidirectional streaming example requires Python 3.12 or later and has
separate setup instructions. See each example's README for exact requirements
and run commands. These samples are intended for learning and prototyping, and
Amazon Polly requests may incur AWS charges.
