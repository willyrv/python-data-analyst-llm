"""Télécharge le dataset Olist depuis Kaggle et le décompresse.

Le jeton n'est pas dans ce fichier. Il est lu depuis
`.secrets/kaggle_api_token` (une ligne, jeton KGAT_…) ou, à défaut,
depuis `kaggle_API_token.txt` à la racine, qui est alors déplacé
vers cet emplacement et restreint au propriétaire.

Usage :
    python scripts/download_olist.py
    python scripts/download_olist.py --output data/olist
    python scripts/download_olist.py --force
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRETS_DIR = ROOT / ".secrets"
TOKEN_PATH = SECRETS_DIR / "kaggle_api_token"
LEGACY_TOKEN_PATH = ROOT / "kaggle_API_token.txt"
DEFAULT_OUTPUT = ROOT / "data" / "olist"
DATASET = "olistbr/brazilian-ecommerce"
DOWNLOAD_URL = "https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce"
# L'archive Olist décompressée fait quelques centaines de Mo. Au-delà, on refuse.
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024

REQUIRED_FILES = (
    "olist_customers_dataset.csv",
    "olist_orders_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "product_category_name_translation.csv",
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Télécharge le dataset Brazilian E-Commerce (Olist) depuis Kaggle."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Dossier de destination (défaut : {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Retélécharge même si les CSV sont déjà présents.",
    )
    parser.add_argument(
        "--keep-zip",
        action="store_true",
        help="Conserve l'archive après décompression.",
    )
    args = parser.parse_args()
    output = args.output.expanduser().resolve()

    if not args.force and _dataset_ready(output):
        print(f"Dataset déjà présent dans {output}")
        return

    token = _load_token()
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "brazilian-ecommerce.zip"
    try:
        _download(DOWNLOAD_URL, token, archive)
        extracted = _extract_archives(archive, output)
    except Exception as exc:
        print(_redact(str(exc), token), file=sys.stderr)
        raise SystemExit(1) from None

    if not args.keep_zip and archive.exists():
        archive.unlink()

    missing = [name for name in REQUIRED_FILES if not (output / name).is_file()]
    if missing:
        print(
            "Téléchargement terminé, mais ces fichiers manquent :\n  "
            + "\n  ".join(missing),
            file=sys.stderr,
        )
        raise SystemExit(1)

    print(f"Dataset prêt dans {output} ({len(extracted)} fichier(s) extrait(s)).")
    print(f"Import : python scripts/load_olist.py {output}")


def _dataset_ready(output: Path) -> bool:
    return all((output / name).is_file() for name in REQUIRED_FILES)


def _load_token() -> str:
    """Lit le jeton, et range un fichier legacy dans `.secrets/` si besoin."""
    if TOKEN_PATH.is_file():
        token = _read_secret(TOKEN_PATH)
        _restrict(SECRETS_DIR, TOKEN_PATH)
        if LEGACY_TOKEN_PATH.is_file():
            LEGACY_TOKEN_PATH.unlink()
            print(f"Fichier en clair supprimé : {LEGACY_TOKEN_PATH.name}")
        return token

    if LEGACY_TOKEN_PATH.is_file():
        token = _read_secret(LEGACY_TOKEN_PATH)
        _write_secret(TOKEN_PATH, token)
        LEGACY_TOKEN_PATH.unlink()
        print(f"Jeton déplacé vers {TOKEN_PATH.relative_to(ROOT)} (lecture propriétaire seulement).")
        return token

    raise SystemExit(
        "Jeton Kaggle introuvable.\n"
        f"Créez {TOKEN_PATH.relative_to(ROOT)} avec le jeton sur une seule ligne, "
        "puis relancez ce script. Ne le collez pas dans le code."
    )


def _read_secret(path: Path) -> str:
    token = path.read_text(encoding="utf-8").strip()
    if not token or "\n" in token:
        raise SystemExit(f"{path} doit contenir le jeton sur une seule ligne.")
    if token.startswith("{"):
        raise SystemExit(
            f"{path} ressemble à un JSON. Ce script attend le jeton brut "
            "(celui qui commence par KGAT_), pas un fichier kaggle.json."
        )
    return token


def _write_secret(path: Path, token: str) -> None:
    path.parent.mkdir(mode=0o700, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, (token + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(path, 0o600)


def _restrict(directory: Path, token_file: Path) -> None:
    os.chmod(directory, 0o700)
    os.chmod(token_file, 0o600)


def _download(url: str, token: str, destination: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/zip",
            "User-Agent": "olist-download/1.0",
        },
        method="GET",
    )
    opener = urllib.request.build_opener(_DropAuthOnRedirect())
    temporary = destination.with_suffix(destination.suffix + ".partial")
    try:
        with opener.open(request, timeout=120) as response:
            content_type = response.headers.get("Content-Type", "")
            if "json" in content_type or "html" in content_type:
                body = response.read(4096).decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"Kaggle n'a pas renvoyé une archive ({response.status}, {content_type}) : "
                    f"{_redact(body, token)}"
                )
            total = int(response.headers.get("Content-Length") or 0)
            _stream_to(response, temporary, total)
    except urllib.error.HTTPError as exc:
        temporary.unlink(missing_ok=True)
        body = exc.read(4096).decode("utf-8", errors="replace")
        detail = _error_detail(_redact(body, token))
        raise RuntimeError(
            f"Téléchargement refusé par Kaggle ({exc.code}). {detail}"
        ) from None
    except urllib.error.URLError as exc:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Réseau indisponible : {exc.reason}") from None
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    with temporary.open("rb") as handle:
        magic = handle.read(2)
    if temporary.stat().st_size < 4 or magic != b"PK":
        temporary.unlink(missing_ok=True)
        raise RuntimeError("La réponse Kaggle n'est pas une archive zip.")
    temporary.replace(destination)
    print(f"Archive enregistrée : {destination.name} ({destination.stat().st_size // (1024 * 1024)} Mo)")


def _stream_to(response: object, destination: Path, total: int) -> None:
    written = 0
    next_report = 8 * 1024 * 1024
    with destination.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)  # type: ignore[attr-defined]
            if not chunk:
                break
            handle.write(chunk)
            written += len(chunk)
            if written >= next_report:
                if total:
                    print(f"  {written // (1024 * 1024)} / {total // (1024 * 1024)} Mo")
                else:
                    print(f"  {written // (1024 * 1024)} Mo")
                next_report += 8 * 1024 * 1024


def _error_detail(body: str) -> str:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        message = payload.get("message") or payload.get("error") or payload.get("title")
        if isinstance(message, str) and message.strip():
            return message.strip()
    compact = " ".join(body.split())
    if not compact:
        return "Vérifiez que le jeton est valide et que les conditions du dataset ont été acceptées."
    return compact[:300]


class _DropAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    """N'envoie pas le jeton au serveur de stockage après une redirection."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None
        host = urlparse(newurl).hostname or ""
        if host not in {"www.kaggle.com", "kaggle.com"}:
            redirected.remove_header("Authorization")
        return redirected


def _extract_archives(archive: Path, output: Path) -> list[str]:
    extracted = _safe_extract(archive, output)
    nested = [output / name for name in extracted if name.lower().endswith(".zip")]
    for child in nested:
        if child.is_file():
            extracted.extend(_safe_extract(child, output))
            child.unlink()
    return extracted


def _safe_extract(archive: Path, output: Path) -> list[str]:
    output = output.resolve()
    names: list[str] = []
    with zipfile.ZipFile(archive) as bundle:
        infos = bundle.infolist()
        total = sum(info.file_size for info in infos)
        if total > MAX_UNCOMPRESSED_BYTES:
            raise RuntimeError(
                f"Archive trop volumineuse ({total} octets décompressés, "
                f"plafond {MAX_UNCOMPRESSED_BYTES})."
            )
        for info in infos:
            _reject_unsafe_member(info, output)
        for info in infos:
            bundle.extract(info, output)
            if not info.is_dir():
                names.append(info.filename)
    return names


def _reject_unsafe_member(info: zipfile.ZipInfo, output: Path) -> None:
    name = info.filename
    parts = Path(name).parts
    if not name or name.startswith(("/", "\\")) or ".." in parts:
        raise RuntimeError(f"Chemin refusé dans l'archive : {name}")
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise RuntimeError(f"Lien symbolique refusé dans l'archive : {name}")
    target = (output / name).resolve()
    if target != output and output not in target.parents:
        raise RuntimeError(f"Chemin hors du dossier de destination : {name}")


def _redact(message: str, secret: str) -> str:
    if secret and secret in message:
        return message.replace(secret, "***")
    return message


if __name__ == "__main__":
    main()
