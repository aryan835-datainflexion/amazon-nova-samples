from __future__ import annotations


TRANSCRIBE_TO_TRANSLATE = {
    "ar-SA": "ar",
    "de-DE": "de",
    "en-AU": "en",
    "en-GB": "en",
    "en-US": "en",
    "es-ES": "es",
    "es-US": "es",
    "fr-CA": "fr",
    "fr-FR": "fr",
    "hi-IN": "hi",
    "it-IT": "it",
    "ja-JP": "ja",
    "ko-KR": "ko",
    "pt-BR": "pt",
    "zh-CN": "zh",
    "zh-TW": "zh-TW",
}


def transcribe_locale_to_translate_code(locale: str | None) -> str:
    if not locale:
        return "auto"
    return TRANSCRIBE_TO_TRANSLATE.get(locale, locale.split("-")[0])


def same_language(source_code: str, target_code: str) -> bool:
    if source_code == "auto":
        return False
    return source_code.split("-")[0].lower() == target_code.split("-")[0].lower()


def detected_transcribe_language(result) -> str | None:
    language_code = getattr(result, "language_code", None)
    if language_code:
        return language_code

    language_identification = getattr(result, "language_identification", None)
    if not language_identification:
        return None

    best = max(
        language_identification,
        key=lambda item: getattr(item, "score", 0.0) or 0.0,
        default=None,
    )
    return getattr(best, "language_code", None) if best is not None else None
