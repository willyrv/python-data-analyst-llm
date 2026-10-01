"""Parsing des tool calls, sans serveur LLM."""

from src.parsing import action_summary, assistant_payload, extract_tool_calls, strip_hidden_reasoning
from src.tools.registry import known_tool_names


class _Function:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _Call:
    def __init__(self):
        self.id = "call_1"
        self.function = _Function("query_database", '{"sql": "SELECT 1"}')


class _Message:
    def __init__(self, content, tool_calls):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, **_kwargs):
        return {
            "role": "assistant",
            "content": self.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in self.tool_calls
            ],
            "refusal": None,
        }


def test_hidden_reasoning_is_removed():
    text = strip_hidden_reasoning("<think>plan secret</think>Voici la réponse.")
    assert "secret" not in text
    assert text == "Voici la réponse."


def test_long_reasoning_is_replaced_by_a_short_action_summary():
    summary = action_summary("Étape " * 80, "query_database")
    assert summary == "J'interroge PostgreSQL en lecture seule."


def test_short_model_sentence_is_kept():
    summary = action_summary("Je vais interroger les commandes et les avis.", "query_database")
    assert summary.startswith("Je vais interroger")


def test_native_tool_call_wins_over_json_in_the_text():
    message = _Message(
        content='```json\n{"tool": "search_reviews", "arguments": {}}\n```',
        tool_calls=[_Call()],
    )
    calls = extract_tool_calls(message, known_tool_names())
    assert len(calls) == 1
    assert calls[0].name == "query_database"
    assert calls[0].arguments["sql"] == "SELECT 1"


def test_json_fallback_when_the_model_does_not_fill_tool_calls():
    message = _Message(
        content='```json\n{"tool": "search_reviews", "arguments": {"only_late": true, "max_score": 2}}\n```',
        tool_calls=[],
    )
    calls = extract_tool_calls(message, known_tool_names())
    assert calls[0].name == "search_reviews"
    assert calls[0].arguments["only_late"] is True


def test_unknown_json_tool_is_left_as_a_final_answer():
    message = _Message(content='{"tool": "run_shell", "arguments": {}}', tool_calls=[])
    assert extract_tool_calls(message, known_tool_names()) == []


def test_assistant_payload_keeps_the_gemini_thought_signature():
    from openai.types.chat import ChatCompletionMessage

    message = ChatCompletionMessage.model_validate(
        {
            "role": "assistant",
            "content": "<think>secret</think>Je lance la requête.",
            "tool_calls": [
                {
                    "id": "function-call-1",
                    "type": "function",
                    "function": {"name": "query_database", "arguments": '{"sql": "SELECT 1"}'},
                    "extra_content": {"google": {"thought_signature": "SIG"}},
                },
                {
                    "id": "function-call-2",
                    "type": "function",
                    "function": {"name": "create_chart", "arguments": '{"chart_type": "bar", "x": "cat"}'},
                },
            ],
        }
    )
    payload = assistant_payload(message, extract_tool_calls(message, known_tool_names()))
    assert "secret" not in (payload["content"] or "")
    first, second = payload["tool_calls"]
    assert first["extra_content"]["google"]["thought_signature"] == "SIG"
    assert first["function"]["name"] == "query_database"
    assert "extra_content" not in second


def test_assistant_payload_drops_think_tags_and_extra_fields():
    message = _Message(content="<think>secret</think>Je lance la requête.", tool_calls=[_Call()])
    payload = assistant_payload(message, extract_tool_calls(message, known_tool_names()))
    assert "secret" not in (payload["content"] or "")
    assert "refusal" not in payload
    assert payload["tool_calls"][0]["function"]["name"] == "query_database"
