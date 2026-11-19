# Features

This section contains focused examples of individual Amazon Polly capabilities.
Each example demonstrates one feature with as little unrelated setup as
possible. Together they cover Amazon Polly operations.

Availability can vary by AWS Region, voice, language, and engine. Check the requirements documented by each example before running it.

## Shared setup

Examples 01–06 and 08 require Python 3.10 or later and share `boto3`. From
the repository root:

```bash
cd text-to-speech/features
python3.10 -m venv .venv
source .venv/bin/activate          # macOS / Linux
pip install -r requirements.txt
```

Configure AWS credentials using the guidance in
[Getting Started](../getting-started/#configure-aws-access). These boto3
scripts accept `--profile` and an optional `--region` override; otherwise
boto3 uses the configured Region. Never store credentials in source files.
Requests to Amazon Polly may incur AWS charges.

The [bidirectional streaming example](07-bidi-streaming/) requires Python 3.12
or later and uses the experimental AWS SDK for Python v4 in a separate virtual
environment. Follow the setup in its README.

## Feature index

| Example | APIs covered | Status |
| --- | --- | --- |
| [01-synthesize-speech](01-synthesize-speech/) | `SynthesizeSpeech` | Ready |
| [02-describe-voices](02-describe-voices/) | `DescribeVoices` | Ready |
| [03-voice-control-ssml](03-voice-control-ssml/) | `SynthesizeSpeech` (SSML) | Ready |
| [04-speech-marks](04-speech-marks/) | `SynthesizeSpeech` (JSON marks) | Ready |
| [05-lexicons](05-lexicons/) | `PutLexicon`, `GetLexicon`, `ListLexicons`, `DeleteLexicon` | Ready |
| [06-async-synthesis](06-async-synthesis/) | `StartSpeechSynthesisTask`, `GetSpeechSynthesisTask`, `ListSpeechSynthesisTasks` | Ready |
| [07-bidi-streaming](07-bidi-streaming/) | `StartSpeechSynthesisStream` | Experimental Python SDK |
| [08-voice-cloning](08-voice-cloning/) | `CreateVoice`, `GetVoice`, `DeleteVoice`, synthesis with a cloned voice | Ready |

The bidirectional streaming API is generally available, but example 07 uses
the separate experimental Polly SDK for Python v4.

## Prerequisites

Examples may require an AWS account, least-privilege Amazon Polly permissions, configured AWS credentials, and a supported runtime. Never store credentials in source files. Requests to Amazon Polly may incur AWS charges.

If you need help configuring Python, AWS credentials, a Region, or IAM
permissions, refer to [Getting Started](../getting-started/).

## Adding an example

Create a dedicated directory containing:

- A concise README with setup and run commands
- Minimal source code for one capability
- Expected output and supported configurations
- Cleanup steps when the example creates resources or local audio files

[Back to the project README](../README.md)
