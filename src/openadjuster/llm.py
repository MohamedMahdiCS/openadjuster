"""Minimal client for a local Ollama model with JSON-schema constrained output."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from typing import Any

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434") + "/api/chat"
DEFAULT_MODEL = os.environ.get("OPENADJUSTER_MODEL", "bonsai-2:4b")


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0


class LocalModel:
    def __init__(self, model: str = DEFAULT_MODEL, timeout: int = 600) -> None:
        self.model = model
        self.timeout = timeout
        self.usage = Usage()

    def json(
        self, system: str, user: str, schema: dict[str, Any], images: list[str] | None = None
    ) -> dict[str, Any]:
        """One structured call. `system` holds our instructions; `user` holds document data."""
        body = {
            "model": self.model,
            "stream": False,
            "think": False,
            "format": schema,
            # Same context size as the benchmark baselines, so Ollama never reloads the model
            # between them; num_predict caps runaway answers.
            "options": {"temperature": 0, "num_ctx": 16384, "num_predict": 1200},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user, "images": images or []},
            ],
        }
        start = time.time()
        req = urllib.request.Request(
            OLLAMA_URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            reply = json.load(resp)
        self.usage.calls += 1
        self.usage.seconds += time.time() - start
        self.usage.prompt_tokens += reply.get("prompt_eval_count", 0)
        self.usage.output_tokens += reply.get("eval_count", 0)
        try:
            result: dict[str, Any] = json.loads(reply["message"]["content"])
        except json.JSONDecodeError:
            result = {}
        return result
