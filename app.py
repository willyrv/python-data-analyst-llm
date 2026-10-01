"""Interface de démonstration.

Le fil à l'écran suit le parcours réel :
question, action, outil, SQL, résultat, graphique, réponse.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from src.agent import AgentResult, run_agent
from src.config import get_settings
from src.database import database_status
from src.demo import DEMOS
from src.llm import LlmError, list_models
from src.llm_providers import PROVIDERS, apply_provider, default_llm_state, provider_by_id

st.set_page_config(
    page_title="Small Models, Big Data",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(
    """
    <style>
        .block-container { padding-top: 1.4rem; max-width: 1180px; }
        textarea { font-size: 1.15rem !important; }
        h1 { letter-spacing: -0.03em; }
    </style>
    """,
    unsafe_allow_html=True,
)

settings = get_settings()
if "history" not in st.session_state:
    st.session_state.history = []
for _key, _value in default_llm_state(settings).items():
    if _key not in st.session_state:
        st.session_state[_key] = _value

with st.sidebar:
    st.header("Modèle")
    st.selectbox(
        "Fournisseur",
        options=[provider.id for provider in PROVIDERS],
        format_func=lambda provider_id: provider_by_id(provider_id).label,
        key="llm_provider",
        on_change=apply_provider,
        args=(st.session_state,),
    )
    st.caption(provider_by_id(st.session_state.llm_provider).hint)
    st.text_input("Adresse du serveur", key="llm_base_url")
    st.text_input("Clé API", type="password", key="llm_api_key")
    st.session_state.keys_by_provider[st.session_state.llm_provider] = st.session_state.llm_api_key
    if st.button("Lister les modèles", use_container_width=True):
        try:
            found = list_models(st.session_state.llm_base_url, st.session_state.llm_api_key)
            st.session_state.available_models = found
            st.session_state.model_list_error = ""
            if found and st.session_state.llm_model_select not in found:
                st.session_state.llm_model_select = found[0]
        except LlmError as exc:
            st.session_state.model_list_error = str(exc)
    if st.session_state.model_list_error:
        st.error(st.session_state.model_list_error)
    elif st.session_state.available_models:
        st.caption(f"{len(st.session_state.available_models)} modèles disponibles")
    model_options = list(st.session_state.available_models)
    if st.session_state.llm_model_select not in model_options:
        model_options = [st.session_state.llm_model_select, *model_options]
    st.selectbox("Modèle", options=model_options, key="llm_model_select")
    st.caption(
        "Les clés lues au démarrage préremplissent chaque fournisseur. "
        "Une modification dans cette session n'est pas réécrite sur le disque."
    )

    st.header("Session")
    status = database_status(settings)
    if status.ok:
        st.success(f"PostgreSQL connecté — rôle {status.user}")
    else:
        st.error(f"PostgreSQL indisponible — {status.message}")
    temperature = st.slider("Température", min_value=0.0, max_value=1.0, value=float(settings.temperature), step=0.1)
    max_rounds = st.slider(
        "Limite de tours d'outils",
        min_value=1,
        max_value=12,
        value=int(settings.max_tool_rounds),
    )
    debug = st.toggle("Mode debug", value=bool(settings.debug))
    st.caption("Le LLM propose une action. L'application la valide. L'outil l'exécute.")
    st.caption("Les identifiants PostgreSQL ne sont pas envoyés au modèle.")
    if st.button("Reset conversation", use_container_width=True):
        st.session_state.history = []
        st.session_state.question = ""
        st.rerun()

st.title("Small Models, Big Data")
st.caption("Mêlée Tech 2026 — le modèle interroge les données par des outils. Il n'est pas la source de vérité.")

demo_columns = st.columns(3)
for column, demo in zip(demo_columns, DEMOS, strict=True):
    if column.button(demo.button, use_container_width=True):
        st.session_state.question = demo.question
        st.session_state.autorun = True
        st.rerun()

def _render_exchange(question: str, result: AgentResult, *, debug: bool, show_question: bool = True) -> None:
    if show_question:
        st.subheader("Question")
        st.write(question)

    st.subheader("Parcours")
    if not result.steps:
        st.caption("Aucun outil n'a été appelé.")
    for index, step in enumerate(result.steps, start=1):
        st.markdown(f"**{index}. {step.summary}**")
        caption = f"Outil `{step.tool}`"
        if debug and step.duration_ms is not None:
            caption += f" — {step.duration_ms:.0f} ms"
        st.caption(caption)
        if step.sql:
            origin = (
                "SQL proposé par le modèle, validé puis exécuté par l'application"
                if step.sql_origin == "model"
                else "SQL écrit par l'application, avec paramètres liés"
            )
            st.caption(origin)
            st.code(step.sql, language="sql")
        if step.error:
            st.error(step.error)
        elif step.tool == "search_reviews" and step.rows:
            st.caption(f"{step.row_count or len(step.rows)} avis")
            for review in step.rows:
                score = review.get("review_score")
                delay = review.get("delay_days")
                title = review.get("title") or ""
                header = f"Note {score}/5"
                if delay is not None:
                    header += f" — retard {delay} jours"
                if title:
                    header += f" — {title}"
                st.markdown(f"**{header}**")
                st.write(review.get("comment") or "")
        elif step.columns and step.rows is not None:
            st.dataframe(pd.DataFrame(step.rows), use_container_width=True, hide_index=True)
            if step.row_count is not None:
                st.caption(f"{step.row_count} lignes renvoyées")
        elif step.result_text and not step.chart_path:
            language = "json" if step.analysis else None
            st.code(step.result_text, language=language)
        if step.chart_path and Path(step.chart_path).exists():
            st.image(step.chart_path, use_container_width=True)

    if not result.used_tools:
        st.warning(
            "Aucune donnée n'a été consultée. "
            "Cette réponse ne vient pas de PostgreSQL ni des outils d'analyse."
        )
    if result.error == "max_rounds":
        st.info("Limite de tours atteinte. Les étapes ci-dessus ont bien été exécutées.")

    st.subheader("Réponse")
    st.write(result.answer)

    with st.expander("Journal", expanded=False):
        st.code("\n".join(_event_line(event) for event in result.events) or "(vide)")

    if debug:
        with st.expander("Debug", expanded=False):
            st.write(
                {
                    "model": result.model,
                    "llm_calls": result.llm_calls,
                    "tool_calls": result.tool_calls,
                    "total_ms": round(result.total_ms),
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                }
            )
            for event in result.events:
                if not event.debug and event.duration_ms is None:
                    continue
                st.markdown(f"**{event.kind}** — {event.message}")
                if event.duration_ms is not None:
                    st.caption(f"{event.duration_ms:.0f} ms")
                if event.debug:
                    st.code(json.dumps(event.debug, ensure_ascii=False, indent=2, default=str), language="json")


def _event_line(event) -> str:
    if event.kind == "SQL":
        return f"[SQL]\n{event.message}"
    return f"[{event.kind}] {event.message}"


if "question" not in st.session_state:
    st.session_state.question = ""

st.text_area(
    "Question",
    key="question",
    height=140,
    placeholder="Posez une question sur les commandes, les délais ou les avis.",
)
autorun = bool(st.session_state.pop("autorun", False))
analyze = st.button("Analyser", type="primary")
question = st.session_state.get("question", "").strip()

if (analyze or autorun) and question:
    runtime = settings.model_copy(
        update={
            "openai_base_url": st.session_state.llm_base_url.strip(),
            "openai_api_key": st.session_state.llm_api_key,
            "model_name": st.session_state.llm_model_select.strip(),
        }
    )
    if not runtime.openai_base_url or not runtime.model_name:
        st.error("Indiquez l'adresse du serveur et un modèle.")
    else:
        with st.spinner("Le modèle choisit des outils et les données répondent…"):
            result = run_agent(
                question,
                runtime,
                temperature=temperature,
                max_tool_rounds=max_rounds,
                debug=debug,
            )
        st.session_state.history.append({"question": question, "result": result.model_dump()})
elif analyze or autorun:
    st.info("Écrivez une question, ou utilisez un bouton de démonstration.")

if st.session_state.history:
    latest = st.session_state.history[-1]
    _render_exchange(latest["question"], AgentResult.model_validate(latest["result"]), debug=debug)
    older = list(reversed(st.session_state.history[:-1]))
    if older:
        st.divider()
        st.subheader("Questions précédentes")
        for exchange in older:
            with st.expander(exchange["question"]):
                _render_exchange(
                    exchange["question"],
                    AgentResult.model_validate(exchange["result"]),
                    debug=debug,
                    show_question=False,
                )
