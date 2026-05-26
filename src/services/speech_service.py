from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

TTS_VOICE = "ja-JP-NanamiNeural"
TTS_OUTPUT_FORMAT = "audio-16khz-128kbitrate-mono-mp3"


class SpeechService:
    def __init__(self, speech_key: str, speech_region: str):
        self._key = speech_key
        self._region = speech_region

    async def issue_token(self) -> str:
        url = f"https://{self._region}.api.cognitive.microsoft.com/sts/v1.0/issueToken"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={"Ocp-Apim-Subscription-Key": self._key},
                content="",
                timeout=10,
            )
            resp.raise_for_status()
            return resp.text

    async def synthesize(self, text: str, voice: str = TTS_VOICE) -> bytes:
        url = f"https://{self._region}.tts.speech.microsoft.com/cognitiveservices/v1"
        ssml = (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="ja-JP">'
            f'<voice name="{voice}">{_escape_xml(text)}</voice>'
            f"</speak>"
        )
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "Ocp-Apim-Subscription-Key": self._key,
                    "Content-Type": "application/ssml+xml",
                    "X-Microsoft-OutputFormat": TTS_OUTPUT_FORMAT,
                },
                content=ssml,
                timeout=30,
            )
            resp.raise_for_status()
            logger.info("TTS synthesized %d chars → %d bytes audio", len(text), len(resp.content))
            return resp.content


def _escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
