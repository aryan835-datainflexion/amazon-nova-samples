# Async Synthesis

For text beyond the synchronous 6,000-character limit, start an **asynchronous
task**. Polly synthesizes in the background and writes the audio to an S3
bucket you own; you poll for completion and can download the generated audio.

**APIs:** [`StartSpeechSynthesisTask`](https://docs.aws.amazon.com/polly/latest/APIReference/API_StartSpeechSynthesisTask.html), [`GetSpeechSynthesisTask`](https://docs.aws.amazon.com/polly/latest/APIReference/API_GetSpeechSynthesisTask.html), [`ListSpeechSynthesisTasks`](https://docs.aws.amazon.com/polly/latest/APIReference/API_ListSpeechSynthesisTasks.html)

## Setup

Complete the [shared setup](../README.md#shared-setup) from the `features/`
directory. You also need an **S3 bucket in the same Region** and permission to
write to it. Local downloads also require permission to read the generated
object.

Required IAM actions are `polly:StartSpeechSynthesisTask`,
`polly:GetSpeechSynthesisTask`, `polly:ListSpeechSynthesisTasks`,
`s3:PutObject`, and `s3:GetObject`.

## Run

```bash
cd 06-async-synthesis

# Set an existing S3 bucket in the same Region as Amazon Polly
# Use the bucket name only, not an s3:// URI
export POLLY_OUTPUT_BUCKET=my-bucket-polly-outputs

# The included sample has 6,477 characters, exceeding the synchronous limit
# Start a task, wait for completion, and download the generated MP3
# Defaults: Tiffany, generative engine, MP3
python async_synthesis.py start \
    --bucket "$POLLY_OUTPUT_BUCKET" \
    --text-file sample-long-text.txt \
    --wait \
    --download-to async-synthesis.mp3
```

The script generates a unique S3 key prefix, prints the completed object’s
exact S3 location and cleanup command, and downloads the audio locally.

## Additional commands

```bash
# Start from inline text without waiting
python async_synthesis.py start \
    --bucket "$POLLY_OUTPUT_BUCKET" \
    --text "A short asynchronous request."

# Poll the task ID printed by the start command
export POLLY_TASK_ID=...
python async_synthesis.py get --task-id "$POLLY_TASK_ID"

# List up to 20 completed tasks
python async_synthesis.py list --status completed
```

## Options (start)

| Flag | Default | Notes |
|---|---|---|
| `--bucket` | *(required)* | Output S3 bucket, same region as `--region` |
| `--key-prefix` | unique `polly/async-synthesis-*` value | Prefix for the output object key |
| `--text` / `--text-file` | *(one required)* | Inline text or a UTF-8 file |
| `--voice` | `Tiffany` | Voice ID |
| `--engine` | `generative` | `standard`, `neural`, `long-form`, or `generative` |
| `--format` | `mp3` | `mp3`, `ogg_vorbis`, or `pcm` |
| `--wait` | off | Poll every 5s until `completed`/`failed` |
| `--timeout` | `300` | Maximum seconds to wait with `--wait` |
| `--download-to` | — | Download completed audio locally; requires `--wait` |

## What to know

- **Output goes to S3, not back to you inline.** The response gives an
  `OutputUri`. With `--download-to`, the script downloads that exact object
  after the task completes.
- **Input limits are larger than synchronous synthesis.** A task accepts up to
  200,000 characters total, including SSML tags, with no more than 100,000
  billed characters. See the
  [`StartSpeechSynthesisTask` API reference](https://docs.aws.amazon.com/polly/latest/APIReference/API_StartSpeechSynthesisTask.html).
- **The included sample demonstrates the difference.**
  [`sample-long-text.txt`](sample-long-text.txt) contains 6,477 characters, so
  it exceeds the synchronous request limit while remaining quick to review.
- **IAM needs both services.** `polly:StartSpeechSynthesisTask` *and*
  `s3:PutObject` on the bucket. Local downloads require `s3:GetObject`, and
  the bucket must be in the same Region as the task.
- **Output prefixes are unique by default.** This gives each run a distinct,
  recognizable S3 object prefix.
- **Status flow:** `scheduled` → `inProgress` → `completed` (or `failed`, with
  a reason in `TaskStatusReason`). A failed task exits with an error.
- **Listing is paginated.** The `list` command follows `NextToken` until it
  reaches `--max` or there are no more tasks.
- **Task record retention.** Amazon Polly keeps the `SpeechSynthesisTask`
  record for 72 hours after the task starts. After that, `get` and `list` may
  no longer return its status or `OutputUri`. The generated audio is a separate
  object in your S3 bucket; it remains there until you delete it or an S3
  Lifecycle rule expires it. See the
  [`StartSpeechSynthesisTask` API reference](https://docs.aws.amazon.com/polly/latest/APIReference/API_StartSpeechSynthesisTask.html)
  and [S3 object deletion guidance](https://docs.aws.amazon.com/AmazonS3/latest/userguide/DeletingObjects.html).

## Expected output

```
Using S3 key prefix: polly/async-synthesis-a1b2c3d4e5f6
Started task (6477 characters):
  TaskId:      abcd1234-...
  Status:      scheduled
  Voice:       Tiffany  engine=generative
  ...
Polling until complete...
  status: inProgress
  status: completed

  OutputUri:   https://s3.us-east-1.amazonaws.com/my-bucket-polly-outputs/polly/async-synthesis-a1b2c3d4e5f6.abcd1234-....mp3
  S3Uri:       s3://my-bucket-polly-outputs/polly/async-synthesis-a1b2c3d4e5f6.abcd1234-....mp3

Clean up the S3 object with:
  aws s3 rm 's3://my-bucket-polly-outputs/polly/async-synthesis-a1b2c3d4e5f6.abcd1234-....mp3'

Downloaded audio to async-synthesis.mp3
Play it with: afplay async-synthesis.mp3   (macOS)  |  ffplay async-synthesis.mp3
```

## Cleanup

Run the exact `aws s3 rm` command printed by the script. Then remove the local
download:

```bash
# Replace this example with the exact S3Uri printed by your run
aws s3 rm 's3://my-bucket-polly-outputs/polly/async-synthesis-a1b2c3d4e5f6.abcd1234-....mp3'

rm -f async-synthesis.mp3
```

[Back to Features](../README.md)
