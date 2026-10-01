"""Client compatible OpenAI : vLLM, Ollama, Torus, OpenAI ou Gemini."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from src.config import Settings


class LlmError(RuntimeError):
    """Erreur montrable à l'écran, sans pile d'appel."""


def list_models(base_url: str, api_key: str, *, timeout: float = 20) -> list[str]:
    """Interroge GET {base_url}/models et renvoie les identifiants triés."""
    root = base_url.strip().rstrip("/")
    if not root:
        raise LlmError("Indiquez l'adresse du serveur de modèles.")
    if not root.startswith(("http://", "https://")):
        raise LlmError("L'adresse doit commencer par http:// ou https://.")
    request = Request(
        f"{root}/models",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key or 'dummy'}",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        detail = _without_secret(detail, api_key)[:300]
        raise LlmError(f"Liste des modèles refusée (HTTP {exc.code}). {detail}") from exc
    except TimeoutError as exc:
        raise LlmError("Le serveur n'a pas répondu à temps pour la liste des modèles.") from exc
    except URLError as exc:
        raise LlmError(f"Impossible de joindre {root}. {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise LlmError("La réponse de /models n'est pas du JSON.") from exc
    model_ids = extract_model_ids(payload)
    if not model_ids:
        raise LlmError("Le serveur n'a renvoyé aucun identifiant de modèle.")
    return model_ids


def extract_model_ids(payload: Any) -> list[str]:
    """Accepte le format OpenAI, Open WebUI et Gemini."""
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("data") or payload.get("models") or []
    else:
        items = []
    found: list[str] = []
    for item in items:
        if isinstance(item, str):
            model_id = item
        elif isinstance(item, dict):
            model_id = item.get("id") or item.get("name") or ""
        else:
            continue
        model_id = str(model_id).strip()
        if model_id.startswith("models/"):
            model_id = model_id.removeprefix("models/")
        if model_id:
            found.append(model_id)
    return sorted(set(found))


def create_client(settings: Settings) -> OpenAI:
    # max_retries=0 : sur scène, un échec doit être visible tout de suite.
    return OpenAI(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key or "dummy",
        timeout=settings.llm_timeout_s,
        max_retries=0,
    )


def complete(
    client: OpenAI,
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    temperature: float,
) -> Any:
    try:
        return client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=temperature,
        )
    except APITimeoutError as exc:
        raise LlmError(
            f"Le modèle n'a pas répondu dans le délai ({exc}). "
            "Réduisez la question ou augmentez LLM_TIMEOUT_S."
        ) from exc
    except APIConnectionError as exc:
        raise LlmError(
            "Impossible de joindre le serveur LLM. "
            "Vérifiez OPENAI_BASE_URL et que vLLM ou Ollama est démarré."
        ) from exc
    except APIStatusError as exc:
        detail = _status_detail(exc)
        if exc.status_code == 400 and "thought_signature" in detail.lower():
            raise LlmError(
                "Gemini a refusé l'historique d'outil : la thought_signature de l'appel précédent est absente. "
                f"Détail : {detail}"
            ) from exc
        if exc.status_code == 400 and "tool" in detail.lower():
            raise LlmError(
                "Le serveur a refusé les outils. "
                "Avec vLLM, ajoutez --enable-auto-tool-choice et un --tool-call-parser adapté au modèle. "
                f"Détail : {detail}"
            ) from exc
        raise LlmError(f"Le serveur LLM a renvoyé une erreur HTTP {exc.status_code}. {detail}") from exc


def usage_dict(completion: Any) -> dict[str, int] | None:
    usage = getattr(completion, "usage", None)
    if usage is None:
        return None
    data = {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }
    cleaned = {key: int(value) for key, value in data.items() if value is not None}
    return cleaned or None


def _status_detail(exc: APIStatusError) -> str:
    message = getattr(exc, "message", None) or str(exc)
    return " ".join(str(message).split())[:400]


def _without_secret(text: str, secret: str) -> str:
    if secret and secret != "dummy":
        return text.replace(secret, "***")
    return text
