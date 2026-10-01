"""Boucle de l'agent.

Le LLM propose une action.
L'application la valide.
L'outil l'exécute.
Le résultat réel revient au modèle.

Le modèle n'est jamais la source de vérité.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from src.config import Settings, get_settings
from src.llm import LlmError, complete, create_client, usage_dict
from src.parsing import action_summary, assistant_payload, extract_tool_calls, strip_hidden_reasoning
from src.prompts import SYSTEM_PROMPT
from src.tools.registry import ToolOutcome, dispatch, known_tool_names, tool_schemas
from src.trace import Trace, TraceEvent

_TOOL_CONTENT_LIMIT = 12_000
_EMPTY_ANSWER = "Je ne sais pas répondre à partir des données disponibles."


class Step(BaseModel):
    summary: str
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    sql: str | None = None
    sql_origin: str | None = None
    result_text: str = ""
    columns: list[str] | None = None
    rows: list[dict[str, Any]] | None = None
    row_count: int | None = None
    chart_path: str | None = None
    analysis: str | None = None
    error: str | None = None
    duration_ms: float | None = None


class AgentResult(BaseModel):
    answer: str
    steps: list[Step] = Field(default_factory=list)
    events: list[TraceEvent] = Field(default_factory=list)
    used_tools: bool = False
    model: str
    llm_calls: int = 0
    tool_calls: int = 0
    total_ms: float = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None


def run_agent(
    question: str,
    settings: Settings | None = None,
    *,
    temperature: float | None = None,
    max_tool_rounds: int | None = None,
    debug: bool | None = None,
) -> AgentResult:
    """Pose une question. Chaque question est indépendante : pas d'historique envoyé au modèle."""
    settings = settings or get_settings()
    debug_on = settings.debug if debug is None else debug
    temperature = settings.temperature if temperature is None else temperature
    max_rounds = settings.max_tool_rounds if max_tool_rounds is None else max_tool_rounds
    started = time.perf_counter()
    trace = Trace(debug=debug_on)
    trace.add("LLM", "User question received")

    steps: list[Step] = []
    llm_calls = 0
    tool_calls = 0
    prompt_tokens = 0
    completion_tokens = 0
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    tools = tool_schemas()
    known = known_tool_names()

    def finish(answer: str, error: str | None = None) -> AgentResult:
        return AgentResult(
            answer=answer,
            steps=steps,
            events=trace.events,
            used_tools=tool_calls > 0,
            model=settings.model_name,
            llm_calls=llm_calls,
            tool_calls=tool_calls,
            total_ms=(time.perf_counter() - started) * 1000,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            error=error,
        )

    try:
        client = create_client(settings)
        for _ in range(max_rounds):
            request_debug = None
            if debug_on:
                request_debug = {
                    "model": settings.model_name,
                    "temperature": temperature,
                    "message_count": len(messages),
                    "messages": messages,
                    "tools": sorted(known),
                }
            llm_started = time.perf_counter()
            completion = complete(
                client,
                model=settings.model_name,
                messages=messages,
                tools=tools,
                temperature=temperature,
            )
            llm_calls += 1
            usage = usage_dict(completion)
            if usage:
                prompt_tokens += usage.get("prompt_tokens", 0)
                completion_tokens += usage.get("completion_tokens", 0)
            trace.add(
                "LLM",
                "Chat completion",
                duration_ms=(time.perf_counter() - llm_started) * 1000,
                debug={"tokens": usage, "request": request_debug} if debug_on else None,
            )
            if not completion.choices:
                raise LlmError("Le serveur LLM a renvoyé une réponse vide.")

            message = completion.choices[0].message
            calls = extract_tool_calls(message, known)
            if not calls:
                trace.add("LLM", "Generating final answer")
                answer = strip_hidden_reasoning(getattr(message, "content", None)) or _EMPTY_ANSWER
                return finish(answer)

            names = ", ".join(call.name for call in calls)
            trace.add("LLM", f"Calling {names}")
            messages.append(assistant_payload(message, calls))
            for call in calls:
                tool_calls += 1
                step = _run_tool(call, message, settings, trace)
                steps.append(step)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": step.result_text[:_TOOL_CONTENT_LIMIT],
                    }
                )
        trace.add("LLM", "Generating final answer")
        return finish(
            "Je n'ai pas pu conclure : le nombre maximum d'appels d'outils est atteint. "
            "Les résultats déjà calculés restent affichés. "
            "Vous pouvez reformuler la question ou augmenter la limite dans la barre latérale.",
            error="max_rounds",
        )
    except LlmError as exc:
        trace.add("ERROR", str(exc))
        return finish(str(exc), error=str(exc))


def _run_tool(call: Any, message: Any, settings: Settings, trace: Trace) -> Step:
    summary = action_summary(getattr(message, "content", None), call.name)
    trace.add("TOOL", call.name)
    started = time.perf_counter()
    if call.parse_error:
        outcome = ToolOutcome(content=f"Erreur : {call.parse_error}", error=call.parse_error)
    else:
        outcome = dispatch(call.name, call.arguments, settings)
    duration_ms = (time.perf_counter() - started) * 1000
    if outcome.sql:
        trace.add("SQL", outcome.sql)
    if outcome.analysis:
        trace.add("ANALYSIS", outcome.analysis)
    if outcome.error:
        trace.add("ERROR", outcome.error)
        trace.add("TOOL RESULT", "error")
    else:
        trace.add("TOOL RESULT", _result_label(outcome))
    return Step(
        summary=summary,
        tool=call.name,
        arguments=call.arguments,
        sql=outcome.sql,
        sql_origin=outcome.sql_origin,
        result_text=outcome.content,
        columns=outcome.columns,
        rows=outcome.rows,
        row_count=outcome.row_count,
        chart_path=outcome.chart_path,
        analysis=outcome.analysis,
        error=outcome.error,
        duration_ms=duration_ms,
    )


def _result_label(outcome: ToolOutcome) -> str:
    if outcome.row_count is not None:
        return f"{outcome.row_count} rows"
    if outcome.chart_path:
        return "chart"
    return "ok"
