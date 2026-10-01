"""Serveurs de modèles proposés dans l'interface.

Tous exposent une API de chat compatible OpenAI. Le choix ne change pas
la boucle de l'agent : seule l'adresse, la clé et l'identifiant du modèle changent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from src.config import Settings


@dataclass(frozen=True)
class LlmProvider:
    id: str
    label: str
    base_url: str
    hint: str


PROVIDERS: tuple[LlmProvider, ...] = (
    LlmProvider(
        id="torus",
        label="Torus (Open WebUI)",
        base_url="https://gentl.torus.ai/api",
        hint="Clé créée dans gentl.torus.ai → Settings → Account → API Keys.",
    ),
    LlmProvider(
        id="openai",
        label="OpenAI",
        base_url="https://api.openai.com/v1",
        hint="Clé API OpenAI. Choisissez un modèle qui accepte les tool calls.",
    ),
    LlmProvider(
        id="google",
        label="Google Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        hint="Clé Gemini. Cette adresse est le point d'accès compatible OpenAI.",
    ),
    LlmProvider(
        id="local",
        label="vLLM ou Ollama local",
        base_url="http://localhost:8000/v1",
        hint="vLLM écoute souvent le port 8000. Ollama : http://localhost:11434/v1.",
    ),
    LlmProvider(
        id="custom",
        label="Adresse personnalisée",
        base_url="",
        hint="Collez l'URL d'une API compatible OpenAI.",
    ),
)

_BY_ID = {provider.id: provider for provider in PROVIDERS}


def provider_by_id(provider_id: str) -> LlmProvider:
    return _BY_ID[provider_id]


def detect_provider(base_url: str) -> str:
    """Retrouve le fournisseur à partir de l'URL déjà configurée."""
    url = base_url.strip().lower().rstrip("/")
    if "generativelanguage.googleapis.com" in url:
        return "google"
    if "api.openai.com" in url:
        return "openai"
    if "torus.ai" in url:
        return "torus"
    if "localhost" in url or "127.0.0.1" in url:
        return "local"
    return "custom"


def default_llm_state(settings: Settings) -> dict:
    """Valeurs initiales de la barre latérale. Les clés restent dans la session."""
    provider_id = detect_provider(settings.openai_base_url)
    keys = {provider.id: "" for provider in PROVIDERS}
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
    torus_key = os.getenv("TORUS_API_KEY") or ""
    openai_cloud_key = os.getenv("OPENAI_CLOUD_API_KEY") or ""
    if gemini_key:
        keys["google"] = gemini_key
    if torus_key:
        keys["torus"] = torus_key
    if openai_cloud_key:
        keys["openai"] = openai_cloud_key
    # La clé du .env correspond au serveur de départ, même si une clé dédiée existe.
    keys[provider_id] = settings.openai_api_key
    return {
        "llm_provider": provider_id,
        "llm_base_url": settings.openai_base_url,
        "llm_api_key": settings.openai_api_key,
        "llm_model_select": settings.model_name,
        "keys_by_provider": keys,
        "available_models": [],
        "model_list_error": "",
    }


def apply_provider(state: dict) -> None:
    """Raccourci de fournisseur : remplit l'URL et restaure la clé déjà saisie."""
    provider = provider_by_id(state["llm_provider"])
    if provider.base_url:
        state["llm_base_url"] = provider.base_url
    keys = state["keys_by_provider"]
    state["llm_api_key"] = keys.get(provider.id, "")
    state["available_models"] = []
    state["model_list_error"] = ""
