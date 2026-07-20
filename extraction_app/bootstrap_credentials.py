"""
Genere les identifiants du compte unique au tout premier lancement.

Si extraction_app/data/config_local.json n'existe pas encore, cree un
utilisateur "admin" avec un mot de passe aleatoire fort, affiche UNE SEULE
FOIS en clair dans la console (a noter immediatement -- il n'est jamais
reaffiche ensuite), et sauvegarde uniquement son empreinte (hash + sel) sur
disque. Ce fichier est dans .gitignore : il ne doit jamais etre versionne.
"""

from __future__ import annotations

import hashlib
import json
import secrets

from extraction_app.config import CONFIG_LOCAL_PATH, DATA_DIR

DEFAULT_USERNAME = "admin"
PBKDF2_ITERATIONS = 260_000


def _hash_password(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return digest.hex()


def ensure_credentials() -> None:
    """Cree config_local.json avec un mot de passe genere si absent. Idempotent."""
    if CONFIG_LOCAL_PATH.exists():
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    password = secrets.token_urlsafe(12)
    salt = secrets.token_bytes(16)
    payload = {
        "username": DEFAULT_USERNAME,
        "salt": salt.hex(),
        "password_hash": _hash_password(password, salt),
        "iterations": PBKDF2_ITERATIONS,
    }
    with open(CONFIG_LOCAL_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("=" * 70)
    print("Identifiants generes pour extraction_app (affiches une seule fois) :")
    print(f"  utilisateur : {DEFAULT_USERNAME}")
    print(f"  mot de passe : {password}")
    print("Note-le maintenant. Pour le changer, supprime extraction_app/data/")
    print("config_local.json et relance le serveur (un nouveau sera genere).")
    print("=" * 70)


def verify_password(username: str, password: str) -> bool:
    if not CONFIG_LOCAL_PATH.exists():
        return False
    with open(CONFIG_LOCAL_PATH, "r", encoding="utf-8") as f:
        creds = json.load(f)
    if username != creds["username"]:
        return False
    salt = bytes.fromhex(creds["salt"])
    expected = creds["password_hash"]
    candidate = _hash_password(password, salt)
    return secrets.compare_digest(candidate, expected)
