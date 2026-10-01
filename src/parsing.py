"""Extraction des tool calls et nettoyage du texte affiché.

Certains petits modèles écrivent l'appel en JSON dans le message au lieu
d'utiliser le champ tool_calls. On accepte ce repli, puis on valide quand même.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_THINK_OPEN = re.compile(r"<think>.*", re.IGNORECASE | re.DOTALL)
_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.IGNORECASE | re.DOTALL)

_DEFAULT_SUMMARIES = {
    "inspect_database_schema": "Je consulte le schéma pour choisir les bonnes tables.",
    "query_database": "J'interroge PostgreSQL en lecture seule.",
    "analyze_dataframe": "Je calcule des statistiques à partir des données extraites.",
    "create_chart": "Je génère un graphique à partir des données.",
    "search_reviews": "Je récupère les avis clients qui correspondent à la question.",
}


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str
    parse_error: str | None = None


def strip_hidden_reasoning(text: str | None) -> str:
    """Retire les balises de réflexion. Elles ne vont ni à l'écran ni dans le prompt suivant."""
    if not text:
        return ""
    cleaned = _THINK_BLOCK.sub("", text)
    cleaned = _THINK_OPEN.sub("", cleaned)
    return cleaned.strip()


def action_summary(model_text: str | None, tool_name: str) -> str:
    """Une phrase affichable. Le texte long est traité comme une réflexion et masqué."""
    text = strip_hidden_reasoning(model_text)
    text = _FENCE.sub("", text)
    text = re.sub(r"\{[^{}]*\"tool\"[^{}]*\}", "", text)
    line = " ".join(text.split())
    if 0 < len(line) <= 280:
        return line
    return _DEFAULT_SUMMARIES.get(tool_name, "J'utilise un outil pour consulter les données.")


def extract_tool_calls(message: Any, known_tools: set[str]) -> list[ToolCall]:
    native = _native_calls(message)
    if native:
        return native
    content = _message_content(message)
    return _fallback_calls(content, known_tools)


def assistant_payload(message: Any, calls: list[ToolCall]) -> dict[str, Any]:
    """Message assistant à renvoyer au serveur.

    On retire le texte de réflexion, mais on conserve extra_content.
    Gemini 3 y place thought_signature et refuse le tour suivant si elle manque.
    """
    raw_calls = _raw_tool_call_dicts(message)
    if raw_calls:
        return {
            "role": "assistant",
            "content": strip_hidden_reasoning(_message_content(message)) or None,
            "tool_calls": [_clean_tool_call(raw) for raw in raw_calls],
        }
    content = strip_hidden_reasoning(_message_content(message))
    content = _FENCE.sub("", content).strip()
    return {
        "role": "assistant",
        "content": content or None,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": call.raw_arguments or json.dumps(call.arguments, ensure_ascii=False),
                },
            }
            for call in calls
        ],
    }


def _raw_tool_call_dicts(message: Any) -> list[dict[str, Any]]:
    raw_calls = _get(message, "tool_calls") or []
    dumped: list[dict[str, Any]] = []
    for raw in raw_calls:
        if isinstance(raw, dict):
            dumped.append(raw)
            continue
        if hasattr(raw, "model_dump"):
            payload = raw.model_dump(exclude_none=True)
            if isinstance(payload, dict):
                dumped.append(payload)
                continue
        function = _get(raw, "function") or {}
        dumped.append(
            {
                "id": _get(raw, "id"),
                "type": _get(raw, "type") or "function",
                "function": {
                    "name": _get(function, "name"),
                    "arguments": _get(function, "arguments") or "{}",
                },
            }
        )
    return dumped


def _clean_tool_call(raw: dict[str, Any]) -> dict[str, Any]:
    function = raw.get("function") or {}
    arguments = function.get("arguments") or "{}"
    if not isinstance(arguments, str):
        arguments = json.dumps(arguments, ensure_ascii=False)
    cleaned: dict[str, Any] = {
        "id": raw.get("id"),
        "type": raw.get("type") or "function",
        "function": {"name": function.get("name"), "arguments": arguments},
    }
    extra = raw.get("extra_content")
    if isinstance(extra, dict) and extra:
        cleaned["extra_content"] = extra
    return cleaned


def _native_calls(message: Any) -> list[ToolCall]:
    raw_calls = _get(message, "tool_calls") or []
    calls: list[ToolCall] = []
    for raw in raw_calls:
        function = _get(raw, "function") or {}
        name = _get(function, "name") or ""
        raw_arguments = _get(function, "arguments") or "{}"
        arguments, error = _parse_arguments(raw_arguments)
        calls.append(
            ToolCall(
                id=_get(raw, "id") or f"call_{uuid.uuid4().hex[:8]}",
                name=name,
                arguments=arguments,
                raw_arguments=raw_arguments if isinstance(raw_arguments, str) else json.dumps(raw_arguments),
                parse_error=error,
            )
        )
    return calls


def _fallback_calls(content: str, known_tools: set[str]) -> list[ToolCall]:
    for candidate in _json_candidates(content):
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        name = obj.get("tool") or obj.get("name")
        arguments = obj.get("arguments", obj.get("parameters", {}))
        if name in known_tools and isinstance(arguments, dict):
            return [
                ToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    name=str(name),
                    arguments=arguments,
                    raw_arguments=json.dumps(arguments, ensure_ascii=False),
                )
            ]
    return []


def _json_candidates(content: str) -> list[str]:
    text = strip_hidden_reasoning(content)
    found = [match.group(1) for match in _FENCE.finditer(text)]
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        found.append(stripped)
    return found


def _parse_arguments(raw: Any) -> tuple[dict[str, Any], str | None]:
    if isinstance(raw, dict):
        return raw, None
    if not raw:
        return {}, None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, f"Arguments JSON illisibles : {exc.msg}"
    if not isinstance(parsed, dict):
        return {}, "Les arguments doivent être un objet JSON."
    return parsed, None


def _message_content(message: Any) -> str:
    content = _get(message, "content")
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return str(content)


def _get(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)
