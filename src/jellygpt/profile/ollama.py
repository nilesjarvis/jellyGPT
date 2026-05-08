from __future__ import annotations

import httpx


class OllamaError(RuntimeError):
    pass


def ollama_available(base_url: str, timeout_seconds: float = 3.0) -> bool:
    try:
        response = httpx.get(base_url.rstrip("/") + "/api/tags", timeout=timeout_seconds)
        return response.status_code == 200
    except Exception:
        return False


def generate_with_ollama(
    base_url: str,
    model: str,
    prompt: str,
    timeout_seconds: float = 120.0,
) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "top_p": 0.85,
            "num_predict": 900,
        },
    }
    try:
        response = httpx.post(base_url.rstrip("/") + "/api/generate", json=payload, timeout=timeout_seconds)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        raise OllamaError(f"Ollama generation failed: {exc}") from exc
    text = str(data.get("response", "")).strip()
    if not text:
        raise OllamaError("Ollama returned an empty response")
    return text
