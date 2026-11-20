from __future__ import annotations

import boto3

from .languages import same_language


class TranslateClient:
    def __init__(self, region: str):
        self._client = boto3.client("translate", region_name=region)

    def translate_text(
        self,
        text: str,
        source_language: str,
        target_language: str,
        skip_same_language: bool = True,
    ) -> str:
        if skip_same_language and same_language(source_language, target_language):
            return text

        response = self._client.translate_text(
            Text=text,
            SourceLanguageCode=source_language,
            TargetLanguageCode=target_language,
        )
        return response["TranslatedText"]
