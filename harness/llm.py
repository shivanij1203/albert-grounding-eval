"""Model client with a disk cache, so a rerun of the eval costs nothing and
reproduces the exact same responses."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 1500


class LLM(Protocol):
    model: str

    def complete(self, system: str, user: str) -> str: ...


def load_api_key(env_file: Path) -> str:
    """Read ANTHROPIC_API_KEY from the environment, else from a local .env file."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key and env_file.exists():
        for line in env_file.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "ANTHROPIC_API_KEY":
                key = value.strip().strip("\"'")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Export it, or put it in .env "
            "(which is gitignored) as ANTHROPIC_API_KEY=..."
        )
    return key


class CachedAnthropic:
    def __init__(self, api_key: str, cache_dir: Path, model: str = DEFAULT_MODEL) -> None:
        import anthropic  # imported here so tests never need the SDK

        self.model = model
        self._client = anthropic.Anthropic(api_key=api_key, max_retries=4)
        self._cache_dir = cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

    def _key(self, system: str, user: str) -> str:
        blob = json.dumps([self.model, MAX_TOKENS, system, user])
        return hashlib.sha256(blob.encode()).hexdigest()[:24]

    def complete(self, system: str, user: str) -> str:
        path = self._cache_dir / f"{self._key(system, user)}.json"
        if path.exists():
            return json.loads(path.read_text())["text"]
        msg = self._client.messages.create(
            model=self.model, max_tokens=MAX_TOKENS,
            system=system, messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        if not text:
            raise RuntimeError(f"empty completion (stop_reason={msg.stop_reason})")
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"model": self.model, "text": text}))
        tmp.replace(path)  # atomic, so parallel workers never read a half-written file
        return text
