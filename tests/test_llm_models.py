"""Liste des modèles et raccourcis de fournisseurs, sans réseau."""

import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

from src.config import Settings
from src.llm import LlmError, extract_model_ids, list_models
from src.llm_providers import apply_provider, default_llm_state, detect_provider


def test_extract_ids_from_openai_and_openwebui_payloads():
    payload = {"data": [{"id": "gpt-4.1"}, {"id": "qwen2.5:7b", "name": "Qwen"}]}
    assert extract_model_ids(payload) == ["gpt-4.1", "qwen2.5:7b"]


def test_extract_ids_strips_the_gemini_models_prefix():
    payload = {"data": [{"id": "models/gemini-2.5-flash"}, {"name": "models/gemini-2.5-pro"}]}
    assert extract_model_ids(payload) == ["gemini-2.5-flash", "gemini-2.5-pro"]


def test_detect_provider_from_the_base_url():
    assert detect_provider("https://gentl.torus.ai/api") == "torus"
    assert detect_provider("https://api.openai.com/v1") == "openai"
    assert detect_provider("https://generativelanguage.googleapis.com/v1beta/openai/") == "google"
    assert detect_provider("http://localhost:8000/v1") == "local"
    assert detect_provider("http://10.0.0.8:8000/v1") == "custom"


def test_default_state_keeps_the_startup_server():
    settings = Settings(
        openai_base_url="https://gentl.torus.ai/api",
        openai_api_key="torus-secret",
        model_name="qwen",
    )
    state = default_llm_state(settings)
    assert state["llm_provider"] == "torus"
    assert state["llm_base_url"] == "https://gentl.torus.ai/api"
    assert state["llm_api_key"] == "torus-secret"
    assert state["llm_model_select"] == "qwen"


def test_default_state_loads_each_provider_key_without_replacing_the_local_one(monkeypatch):
    monkeypatch.setenv("TORUS_API_KEY", "torus-from-env")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-from-env")
    monkeypatch.setenv("OPENAI_CLOUD_API_KEY", "openai-from-env")
    settings = Settings(
        openai_base_url="http://localhost:11434/v1",
        openai_api_key="ollama",
        model_name="qwen3:14b",
    )
    state = default_llm_state(settings)
    assert state["llm_provider"] == "local"
    assert state["llm_api_key"] == "ollama"
    assert state["keys_by_provider"]["local"] == "ollama"
    assert state["keys_by_provider"]["torus"] == "torus-from-env"
    assert state["keys_by_provider"]["google"] == "gemini-from-env"
    assert state["keys_by_provider"]["openai"] == "openai-from-env"


def test_switching_provider_restores_its_saved_key():
    state = {
        "llm_provider": "openai",
        "llm_base_url": "https://gentl.torus.ai/api",
        "llm_api_key": "torus-secret",
        "keys_by_provider": {"openai": "sk-openai", "torus": "torus-secret", "google": "", "local": "", "custom": ""},
        "available_models": ["old-model"],
        "model_list_error": "non",
    }
    apply_provider(state)
    assert state["llm_base_url"] == "https://api.openai.com/v1"
    assert state["llm_api_key"] == "sk-openai"
    assert state["available_models"] == []
    assert state["model_list_error"] == ""


def test_list_models_reads_the_json_catalog(monkeypatch):
    payload = json.dumps({"data": [{"id": "b-model"}, {"id": "a-model"}]}).encode()

    class _Response:
        def read(self):
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("src.llm.urlopen", lambda *_args, **_kwargs: _Response())
    assert list_models("https://gentl.torus.ai/api", "secret") == ["a-model", "b-model"]


def test_list_models_hides_the_api_key_from_http_errors(monkeypatch):
    def _deny(*_args, **_kwargs):
        raise HTTPError(
            url="https://api.openai.com/v1/models",
            code=401,
            msg="unauthorized",
            hdrs=None,
            fp=BytesIO(b'{"error":"invalid key sk-secret-value"}'),
        )

    monkeypatch.setattr("src.llm.urlopen", _deny)
    with pytest.raises(LlmError, match="401") as caught:
        list_models("https://api.openai.com/v1", "sk-secret-value")
    assert "sk-secret-value" not in str(caught.value)
    assert "***" in str(caught.value)
