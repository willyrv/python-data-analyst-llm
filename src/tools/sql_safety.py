"""Validation des SQL proposés par le LLM.

Le modèle propose une requête. Ce module décide si elle a le droit d'exister.
Seuls les SELECT et les WITH ... SELECT passent. Une seule instruction.
Les commentaires sont retirés avant l'analyse, pour qu'ils ne masquent rien.
"""

from __future__ import annotations

import re

class SqlSafetyError(ValueError):
    """Requête refusée avant d'atteindre PostgreSQL."""


# Mots qui ne doivent jamais apparaître comme jetons SQL hors littéraux.
_FORBIDDEN = {
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "truncate",
    "create",
    "grant",
    "revoke",
    "comment",
    "copy",
    "call",
    "execute",
    "prepare",
    "listen",
    "notify",
    "lock",
    "vacuum",
    "refresh",
    "reindex",
    "cluster",
    "discard",
    "merge",
    "into",
    "set",
    "reset",
    "begin",
    "commit",
    "rollback",
    "savepoint",
    "do",
}

# Fonctions qui liraient le disque, le réseau, ou bloqueraient la démo.
_FORBIDDEN_FUNCTIONS = {
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "pg_sleep",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "pg_read_server_files",
    "lo_import",
    "lo_export",
    "lo_from_bytea",
    "dblink",
    "dblink_exec",
}

_MAX_SQL_CHARS = 8_000
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def validate_readonly_sql(sql: str) -> str:
    """Retourne le SQL normalisé, ou lève SqlSafetyError.

    Le résultat n'a pas de point-virgule final : l'exécution l'enveloppe
    ensuite dans un SELECT ... LIMIT.
    """
    if sql is None or not str(sql).strip():
        raise SqlSafetyError("La requête SQL est vide.")
    raw = str(sql).strip()
    if "\x00" in raw:
        raise SqlSafetyError("Caractère nul refusé.")
    if len(raw) > _MAX_SQL_CHARS:
        raise SqlSafetyError(f"Requête trop longue (>{_MAX_SQL_CHARS} caractères).")

    without_comments = _strip_comments(raw)
    statements = _split_statements(without_comments)
    if not statements:
        raise SqlSafetyError("Aucune instruction SQL après nettoyage.")
    if len(statements) > 1:
        raise SqlSafetyError("Une seule instruction SELECT est autorisée.")

    statement = statements[0]
    tokens = _words_outside_strings(statement)
    if not tokens:
        raise SqlSafetyError("Aucun mot SQL reconnu.")

    first = tokens[0].lower()
    if first not in {"select", "with"}:
        raise SqlSafetyError(
            "Seules les requêtes SELECT ou WITH ... SELECT sont autorisées. "
            f"Mot trouvé : {tokens[0]}."
        )
    if first == "with" and not any(token.lower() == "select" for token in tokens):
        raise SqlSafetyError("Un WITH doit contenir un SELECT.")

    lowered = [token.lower() for token in tokens]
    for token in lowered:
        if token in _FORBIDDEN or token in _FORBIDDEN_FUNCTIONS:
            raise SqlSafetyError(f"Mot ou fonction interdit : {token}.")

    return statement.strip()


def _strip_comments(sql: str) -> str:
    out: list[str] = []
    i = 0
    length = len(sql)
    while i < length:
        char = sql[i]
        if char == "'":
            end = _end_of_string(sql, i)
            out.append(sql[i:end])
            i = end
            continue
        if sql.startswith("--", i):
            newline = sql.find("\n", i)
            i = length if newline < 0 else newline
            continue
        if sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            if end < 0:
                raise SqlSafetyError("Commentaire bloc non terminé.")
            i = end + 2
            continue
        out.append(char)
        i += 1
    return "".join(out)


def _end_of_string(sql: str, start: int) -> int:
    """`start` pointe sur le guillemet ouvrant. Gère les quotes doublées."""
    i = start + 1
    length = len(sql)
    while i < length:
        if sql[i] == "'":
            if i + 1 < length and sql[i + 1] == "'":
                i += 2
                continue
            return i + 1
        i += 1
    raise SqlSafetyError("Littéral SQL non terminé.")


def _split_statements(sql: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    i = 0
    length = len(sql)
    while i < length:
        char = sql[i]
        if char == "'":
            end = _end_of_string(sql, i)
            buf.append(sql[i:end])
            i = end
            continue
        if char == ";":
            statement = "".join(buf).strip()
            if statement:
                parts.append(statement)
            buf = []
            i += 1
            continue
        buf.append(char)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _words_outside_strings(sql: str) -> list[str]:
    words: list[str] = []
    i = 0
    length = len(sql)
    while i < length:
        if sql[i] == "'":
            i = _end_of_string(sql, i)
            continue
        match = _WORD.match(sql, i)
        if match:
            words.append(match.group(0))
            i = match.end()
            continue
        i += 1
    return words
