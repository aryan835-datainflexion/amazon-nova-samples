# Bidirectional Streaming

`StartSpeechSynthesisStream` lets an application send text and receive speech
over the same connection. This example uses three prewritten text fragments to
simulate text arriving incrementally from an application. It adds a one-second
pause between fragments only to make the concurrent send and receive activity
easy to see in the terminal. A real application should send each fragment as
soon as it becomes available. The returned audio events are saved to an MP3
file.

The example uses the experimental
[AWS SDK for Python v4 Polly client](https://github.com/aws/aws-sdk-python/tree/develop/clients/aws-sdk-polly)
because boto3 does not yet expose this bidirectional API. The API is generally
available, but this experimental Python client is not yet listed as a supported
SDK and may change before version 1.0.

**API:** [`StartSpeechSynthesisStream`](https://docs.aws.amazon.com/polly/latest/dg/API_StartSpeechSynthesisStream.html)

## Setup

This example requires Python 3.12 or later and uses a separate virtual
environment:

```bash
cd features/07-bidi-streaming
python3.12 -m venv .venv
source .venv/bin/activate          # macOS / Linux
pip install -r requirements.txt
```

Configure AWS credentials and a Region:

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_DEFAULT_REGION=us-east-1
export AWS_SESSION_TOKEN=...       # Include only for temporary credentials
```

The role or user needs permission to call
`polly:StartSpeechSynthesisStream`. Never store credentials in source files.
Requests to Amazon Polly may incur AWS charges.

## Run

```bash
python bidi_streaming_synthesis.py

# Optional overrides
python bidi_streaming_synthesis.py \
    --region us-east-1 \
    --voice Tiffany \
    --output bidi-streaming.mp3
```

The script uses the generative engine with Tiffany and saves the returned audio
as `bidi-streaming.mp3`.

The send and receive functions start together and remain active at the same
time. While `send_text` submits text fragments to Polly, `save_audio` listens
for audio events and writes them to the MP3 file. Audio reception does not
need to wait until every text fragment has been sent. `asyncio.gather()` waits
until both operations are complete:

```python
await asyncio.gather(
    send_text(stream.input_stream),
    save_audio(output_stream),
)
```

## Expected output

The exact order of the send and receive messages can vary:

```text
Sending text 1/3: Amazon Polly receives this text in separate events.
Sending text 2/3: It can begin returning audio before all the input text is available.
Receiving audio...
Sending text 3/3: This is bidirectional streaming.
Text input closed.
Wrote 123,456 bytes of audio to bidi-streaming.mp3.
```

Play the file on macOS:

```bash
afplay bidi-streaming.mp3
```

## Cleanup

```bash
rm -f bidi-streaming.mp3
```

The implementation follows the official
[Polly bidirectional streaming examples](https://github.com/aws/aws-sdk-python/tree/develop/clients/aws-sdk-polly/examples).

[Back to Features](../README.md)
