"""ElevenLabs TTS generation, with a local cache and a conservative char budget."""

import hashlib
import json
import os
import urllib.request
from pathlib import Path

CACHE_DIR = Path("data/audio_cache")
MAX_CHARS_PER_RUN = 2000  # ponytail: conservative default; free tier is tight

# ponytail: the 6 native nl-NL voices the user added to their voice library
# can't be used -- ElevenLabs free tier blocks API access to library voices
# ("Free users cannot use library voices via the API"). Falling back to the
# account's original default premade voices; eleven_multilingual_v2 can
# still speak Dutch text with them, just without a native accent. Revisit if
# the account ever upgrades to a paid plan.
VOICE_IDS = [
    "EXAVITQu4vr4xnSDxMaL",  # Sarah (female, American)
    "CwhRBWXzGAHq8TQ4Fs17",  # Roger (male, American)
    "Xb7hH8MSUJpSbSDYk0k2",  # Alice (female, British)
    "onwK4e9ZLuTAKqWW03F9",  # Daniel (male, British)
]


def voice_for(index: int) -> str:
    return VOICE_IDS[index % len(VOICE_IDS)]


def _cache_path(text: str, voice_id: str) -> Path:
    key = hashlib.sha256(f"{voice_id}:{text}".encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"{key}.mp3"


def synthesize(text: str, voice_id: str) -> Path:
    """Return the cache path for text/voice, synthesizing via ElevenLabs if not cached."""
    path = _cache_path(text, voice_id)
    if path.exists():
        return path

    api_key = os.environ["ELEVENLABS_API_KEY"]
    body = json.dumps({"text": text, "model_id": "eleven_multilingual_v2"}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        data=body,
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        audio = resp.read()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
    return path
