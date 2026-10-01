"""Le validateur SQL est le filet visible pendant la conférence."""

import pytest

from src.tools.sql import execute_select
from src.tools.sql_safety import SqlSafetyError, validate_readonly_sql


def test_select_is_accepted():
    sql = validate_readonly_sql("SELECT * FROM orders LIMIT 10")
    assert sql.lower().startswith("select")


def test_with_select_is_accepted():
    sql = validate_readonly_sql("WITH data AS (SELECT 1 AS x) SELECT * FROM data")
    assert sql.lower().startswith("with")


def test_review_comment_column_is_not_a_comment_statement():
    validate_readonly_sql("SELECT review_comment_message FROM reviews LIMIT 10")


def test_drop_is_rejected():
    with pytest.raises(SqlSafetyError):
        validate_readonly_sql("DROP TABLE orders;")


def test_delete_is_rejected():
    with pytest.raises(SqlSafetyError):
        validate_readonly_sql("DELETE FROM customers")


def test_update_is_rejected():
    with pytest.raises(SqlSafetyError):
        validate_readonly_sql("UPDATE orders SET order_status = 'canceled'")


def test_insert_and_alter_are_rejected():
    with pytest.raises(SqlSafetyError):
        validate_readonly_sql("INSERT INTO orders VALUES (1)")
    with pytest.raises(SqlSafetyError):
        validate_readonly_sql("ALTER TABLE orders ADD COLUMN x int")


def test_stacked_statements_are_rejected():
    with pytest.raises(SqlSafetyError):
        validate_readonly_sql("SELECT * FROM orders; DROP TABLE orders;")


def test_data_modifying_cte_is_rejected():
    with pytest.raises(SqlSafetyError):
        validate_readonly_sql(
            "WITH deleted AS (DELETE FROM orders RETURNING *) SELECT * FROM deleted"
        )


def test_select_into_is_rejected():
    with pytest.raises(SqlSafetyError):
        validate_readonly_sql("SELECT * INTO copy_orders FROM orders")


def test_file_read_function_is_rejected():
    with pytest.raises(SqlSafetyError):
        validate_readonly_sql("SELECT pg_read_file('/etc/passwd')")


def test_drop_hidden_in_a_comment_then_a_second_statement_is_rejected():
    with pytest.raises(SqlSafetyError):
        validate_readonly_sql("SELECT 1; -- harmless\nDROP TABLE orders")


def test_comment_alone_does_not_authorize_a_select_after_drop_keyword_in_comment():
    # Le DROP est dans un commentaire : il ne reste qu'un SELECT, donc c'est valide.
    sql = validate_readonly_sql("/* DROP TABLE orders */ SELECT 1 AS ok")
    assert sql.upper().startswith("SELECT")


def test_forbidden_word_inside_a_string_literal_is_allowed():
    sql = validate_readonly_sql("SELECT 'a; DROP TABLE orders' AS message")
    assert "DROP" in sql


def test_trailing_semicolon_is_still_one_statement():
    sql = validate_readonly_sql("SELECT * FROM orders LIMIT 10;")
    assert not sql.endswith(";")


def test_in_predicate_is_not_confused_with_into():
    validate_readonly_sql("SELECT * FROM orders WHERE order_status IN ('delivered', 'shipped')")


def test_empty_sql_is_rejected():
    with pytest.raises(SqlSafetyError):
        validate_readonly_sql("   ")


def test_rejected_sql_does_not_open_the_database(monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("la base ne doit pas être contactée")

    monkeypatch.setattr("src.tools.sql.app_engine", fail)
    with pytest.raises(SqlSafetyError):
        execute_select("DROP TABLE orders;", max_rows=10)
    with pytest.raises(SqlSafetyError):
        execute_select("DELETE FROM customers", max_rows=10)
    with pytest.raises(SqlSafetyError):
        execute_select("UPDATE orders SET order_status = 'x'", max_rows=10)


def test_like_percent_is_sent_literally(monkeypatch):
    captured: dict[str, str] = {}

    class _Cursor:
        description = [("label",)]

        def execute(self, sql):
            captured["sql"] = sql

        def fetchall(self):
            return [("ok",)]

        def close(self):
            return None

    class _Driver:
        def cursor(self):
            return _Cursor()

    class _Pool:
        driver_connection = _Driver()

    class _Conn:
        connection = _Pool()

    class _Engine:
        def connect(self):
            return self

        def __enter__(self):
            return _Conn()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("src.tools.sql.app_engine", lambda _settings=None: _Engine())
    result = execute_select("SELECT '%livre%' AS label", max_rows=5)
    assert "%livre%" in captured["sql"]
    assert result.rows == [{"label": "ok"}]
