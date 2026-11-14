# Lexicons

Store and apply pronunciation lexicons — PLS documents that customize how Polly
says specific words (expand acronyms, fix names, override pronunciation by
phoneme). This example walks through the full lexicon lifecycle.

**APIs:** [`PutLexicon`](https://docs.aws.amazon.com/polly/latest/APIReference/API_PutLexicon.html), [`GetLexicon`](https://docs.aws.amazon.com/polly/latest/APIReference/API_GetLexicon.html), [`ListLexicons`](https://docs.aws.amazon.com/polly/latest/APIReference/API_ListLexicons.html), [`DeleteLexicon`](https://docs.aws.amazon.com/polly/latest/APIReference/API_DeleteLexicon.html), [`SynthesizeSpeech`](https://docs.aws.amazon.com/polly/latest/APIReference/API_SynthesizeSpeech.html) (to apply)

## Setup

Complete the [shared setup](../README.md#shared-setup) from the `features/`
directory. The workflow requires `polly:PutLexicon`, `polly:GetLexicon`,
`polly:ListLexicons`, `polly:DeleteLexicon`, and `polly:SynthesizeSpeech`.

## Run

```bash
cd 05-lexicons

# Synthesis defaults to the generative engine with Tiffany.

# 1. Upload the sample PLS document under a name
python lexicons.py put --name MyLexicon --file example.pls

# 2. Apply it during synthesis — "AWS" is expanded, "Polly" gets its IPA
# Output: lexicon-applied.mp3
python lexicons.py apply --name MyLexicon --text "Try AWS with Polly."

# 3. Delete the stored lexicon
python lexicons.py delete --name MyLexicon
```

## Additional commands

Run these after uploading the lexicon and before deleting it:

```bash
# List stored lexicons in the configured Region
python lexicons.py list

# Inspect the stored PLS document and its metadata
python lexicons.py get --name MyLexicon
```

## The sample lexicon

[`example.pls`](example.pls) contains two lexemes:

- `AWS` → alias `Amazon Web Services` (acronym expansion)
- `Polly` → IPA `ˈpɑːli` (pronunciation override)

## Options

| Command and flag | Default | Notes |
|---|---|---|
| `put --name` | required | Lexicon name containing 1–20 alphanumeric characters |
| `put --file` | `example.pls` | PLS document to upload |
| `apply --text` | `Try AWS with Polly.` | Text synthesized with the lexicon |
| `apply --voice` | `Tiffany` | Voice ID |
| `apply --engine` | `generative` | `standard`, `neural`, `long-form`, or `generative` |
| `apply -o/--output` | `lexicon-applied.mp3` | Generated audio filename |
| `-p/--profile`, `-r/--region` | configured values | Optional AWS profile and Region overrides |

## What to know

- **Lexicons are regional.** A lexicon stored in `us-east-1` isn't visible in
  `us-west-2`. Store it in the region you synthesize in.
- **Updates are eventually consistent.** Immediately applying a newly stored
  lexicon may return `LexiconNotFoundException`. Wait a few seconds and retry.
- **Names are replaceable.** Uploading another lexicon with the same name
  overwrites the existing lexicon.
- **Valid PLS required.** The document must conform to the W3C PLS schema and
  declare an `alphabet` (`ipa` or `x-sampa`) and `xml:lang`. Malformed content
  returns `InvalidLexiconException`.
- **`LanguageCode` must match.** A lexicon applies only when its language
  matches the voice's language.
- **Apply up to 5 lexicons per request** via `LexiconNames`.
- **Listing is paginated.** The example follows `NextToken` until all lexicons
  in the configured Region have been returned.

## Expected output

```
$ python lexicons.py put --name MyLexicon --file example.pls
Stored lexicon 'MyLexicon' from example.pls in us-east-1.

$ python lexicons.py apply --name MyLexicon --text "Try AWS with Polly."
Wrote lexicon-applied.mp3 with lexicon 'MyLexicon' applied in us-east-1.
Play it with: afplay lexicon-applied.mp3   (macOS)  |  ffplay lexicon-applied.mp3

$ python lexicons.py delete --name MyLexicon
Deleted lexicon 'MyLexicon' from us-east-1.
```

## Cleanup

```bash
python lexicons.py delete --name MyLexicon
rm -f lexicon-applied.mp3
```

Stored lexicons persist and count against a per-region limit until deleted.

[Back to Features](../README.md)
