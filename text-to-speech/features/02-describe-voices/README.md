# DescribeVoices

List the voices available in a region, filtered by engine or language, so you
know what to pass to `--voice` elsewhere.

**API:** [`DescribeVoices`](https://docs.aws.amazon.com/polly/latest/dg/API_DescribeVoices.html)

## Setup

Complete the [shared setup](../README.md#shared-setup) from the `features/`
directory.

## Run

```bash
cd 02-describe-voices

# All generative voices available in us-east-1
python describe_voices.py --engine generative --region us-east-1

# Generative voices with US English as their primary language in us-east-1
python describe_voices.py --engine generative --language-code en-US \
    --region us-east-1

# Generative voices that support Hindi as a primary or additional language
python describe_voices.py --engine generative --language-code hi-IN \
    --include-additional-languages --region us-east-1
```

Each command prints the filters sent to `DescribeVoices`, followed by the
matching voices. It does not generate audio, files, or AWS resources.

## Options

| Flag | Notes |
|---|---|
| `--engine` | Filter to voices supporting `standard`, `neural`, `long-form`, or `generative`; defaults to `generative` |
| `--language-code` | e.g. `en-US`, `es-ES`, `ja-JP` |
| `--include-additional-languages` | Include voices that support `--language-code` as an additional language |
| `-p/--profile`, `-r/--region` | Optional profile and Region overrides |

## What to know

- **Availability is regional.** The same call returns different voices in
  different regions — generative and long-form voices exist in a subset of
  regions. Run against the region you'll actually synthesize in.
- **Pagination.** `DescribeVoices` returns a `NextToken` when results span
  multiple pages. This example follows it until all voices are collected.
- **Additional languages need a language filter.** Use
  `--include-additional-languages` together with `--language-code`; otherwise
  it does not narrow the results.

## Expected output

```
DescribeVoices request:
  Region:                       us-east-1
  Engine:                       generative
  Language code:                en-US
  Include additional languages: no

Id            Language  Gender
----------------------------------------------------------------------
Matthew       en-US     Male
Tiffany       en-US     Female
...
----------------------------------------------------------------------
9 matching voice(s).
```

## Cleanup

None — these are read-only calls that create no resources or files.

[Back to Features](../README.md)
