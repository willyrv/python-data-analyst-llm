"""Tests qui ne démarrent pas PostgreSQL."""

from src.database import database_name
from src.tools.registry import dispatch
from src.tools.sql_safety import SqlSafetyError


def test_database_name_is_parsed_from_the_admin_url():
    assert database_name("postgresql+psycopg://olist:olist@localhost:5432/olist") == "olist"


def test_error_messages_hide_database_passwords():
    from src.config import Settings
    from src.database import redact_secrets

    settings = Settings(
        database_url="postgresql+psycopg://olist_ro:secret-ro@localhost:5432/olist",
        database_admin_url="postgresql+psycopg://olist:secret-admin@localhost:5432/olist",
    )
    message = redact_secrets("échec secret-ro puis secret-admin", settings)
    assert "secret-ro" not in message
    assert "secret-admin" not in message
    assert message.count("***") == 2


def test_dispatch_blocks_writes_before_any_connection(monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("connexion inattendue")

    monkeypatch.setattr("src.tools.sql.app_engine", fail)
    for sql in (
        "DROP TABLE orders",
        "DELETE FROM customers",
        "UPDATE orders SET order_status = 'x'",
    ):
        outcome = dispatch("query_database", {"sql": sql})
        assert outcome.error
        assert "interdit" in outcome.error.lower() or "autorisées" in outcome.error.lower()


def test_unknown_tool_is_an_error_result_not_an_exception():
    outcome = dispatch("run_shell", {"command": "ls"})
    assert outcome.error
    assert "inconnu" in outcome.error.lower()


def test_invalid_sql_arguments_do_not_raise():
    outcome = dispatch("query_database", {})
    assert outcome.error
    assert not isinstance(outcome.error, SqlSafetyError)
