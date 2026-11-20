"""Constants for the podcast sample.

Everything you'd want to change lives here.
"""

# ---------------------------------------------------------------------------
# Region
# ---------------------------------------------------------------------------
#
# Pinned rather than taken from the profile, because Polly generative voices
# exist in only ten regions. An explicit region in code overrides whatever the
# profile sets, so --profile picks identity, not location.
# https://docs.aws.amazon.com/polly/latest/dg/generative-voices.html

AWS_REGION = "us-east-1"


# ---------------------------------------------------------------------------
# Bedrock — script writing
# ---------------------------------------------------------------------------
#
# Global cross-Region inference profiles. All three are reasoning models, all
# three work through the same Converse call, and all three return a
# `reasoningContent` block before the `text` block — see extract_text() in
# podcast_script.py.
#
# Verified against us-east-1 on 2026-08-25.

MODELS = {
    "GPT-5.6 Luna":       "global.openai.gpt-5.6-luna",
    "Claude Sonnet 5":    "global.anthropic.claude-sonnet-5",
    "Grok 4.6":           "global.xai.grok-4.6",
}

DEFAULT_MODEL = "GPT-5.6 Luna"

# All three models accept only maxTokens. Passing temperature or topP returns a
# ValidationException on every one of them:
#   Luna:     "This model doesn't support the temperature field"
#   Sonnet 5: "`temperature` is deprecated for this model"
#   Grok 4.6: "This model doesn't support the temperature field"
# Scripts are therefore non-deterministic and can't be pinned. The budget also
# has to cover reasoning tokens, not just the visible reply.
MAX_TOKENS = 4096

# Turns in a generated episode. Alternates host, cohost, host, cohost...
TURN_COUNT = 4


# ---------------------------------------------------------------------------
# Polly — speech synthesis
# ---------------------------------------------------------------------------

OUTPUT_FORMAT = "mp3"
SAMPLE_RATE = "24000"
CHUNK_SIZE = 4096

# The two speaking styles run on different engines and are mutually exclusive.
GENERATIVE_ENGINE = "generative"   # conversational, ~43 voices, 3-6s per turn
NEWSCASTER_ENGINE = "neural"       # newscaster style, 4 voices, ~0.5s per turn

# Voices that accept <amazon:domain name="news">.
#
# This is the one thing that has to be hardcoded. DescribeVoices reports
# SupportedEngines but has no field for speaking styles or SSML features, so
# newscaster capability is not discoverable from the API. Confirmed empirically
# on 2026-08-25 by sending a 1-character newscaster request to all 63 neural
# voices in us-east-1: exactly these four were accepted, every other voice
# returned "This voice does not support one of the used SSML features".
# https://docs.aws.amazon.com/polly/latest/dg/newscaster-tag.html
NEWSCASTER_VOICE_IDS = frozenset({"Joanna", "Matthew", "Amy", "Lupe"})


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT_NAME = "podcast"
