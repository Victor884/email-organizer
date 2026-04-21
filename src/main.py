"""
main.py
─────────────────────────────────────────────────────────────────────────────
Orquestrador do pipeline de digest de emails.

Fluxo:
  1. Busca emails não-lidos das últimas 24h (gmail_reader)
  2. Filtra emails já processados (cache local em JSON)
  3. Classifica e analisa com LLM (classifier)
  4. Envia digest formatado ao Telegram (telegram_sender)
  5. Atualiza o cache

Cache:
  - Arquivo: processed_emails.json
  - Chave:   MD5(subject + sender + snippet)
  - TTL:     7 dias (entradas mais antigas são descartadas na leitura)
─────────────────────────────────────────────────────────────────────────────
"""

import hashlib
import json
import os
from datetime import datetime, timedelta

from classifier import classify_all
from gmail_reader import get_emails_since_yesterday
from telegram_sender import send_digest

# ─────────────────────────────────────────────────────────────────────────────
#  CACHE
# ─────────────────────────────────────────────────────────────────────────────

_CACHE_FILE = "processed_emails.json"
_CACHE_TTL_DAYS = 7


def _email_hash(email: dict) -> str:
    key = f"{email['subject']}{email['sender']}{email.get('snippet', '')}"
    return hashlib.md5(key.encode()).hexdigest()


def _load_cache() -> dict:
    if not os.path.exists(_CACHE_FILE):
        return {}
    try:
        with open(_CACHE_FILE) as f:
            cache = json.load(f)
        cutoff = (datetime.now() - timedelta(days=_CACHE_TTL_DAYS)).isoformat()
        return {k: v for k, v in cache.items() if v.get("date", "") > cutoff}
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    try:
        with open(_CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception as exc:
        print(f"[main] Aviso: não foi possível salvar cache ({exc})")


# ─────────────────────────────────────────────────────────────────────────────
#  PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    # 1. Busca emails
    print("[1/4] Buscando emails...")
    emails = get_emails_since_yesterday()
    print(f"      {len(emails)} email(s) encontrado(s).")

    # 2. Filtra duplicatas
    cache       = _load_cache()
    novos       = [e for e in emails if _email_hash(e) not in cache]
    ignorados   = len(emails) - len(novos)

    if not novos:
        print(f"[2/4] Todos os {len(emails)} emails já foram processados. Nada a fazer.")
        return

    print(f"[2/4] {len(novos)} novo(s) | {ignorados} já processado(s) — ignorado(s).")

    # 3. Classifica e analisa
    print("[3/4] Classificando e analisando...")
    classified = classify_all(novos)

    totais = {cat: len(lst) for cat, lst in classified.items() if lst}
    print(f"      Resultado: {totais}")

    # 4. Envia para o Telegram
    print("[4/4] Enviando digest ao Telegram...")
    send_digest(classified)

    # 5. Persiste cache
    agora = datetime.now().isoformat()
    for email in novos:
        cache[_email_hash(email)] = {"date": agora}
    _save_cache(cache)

    print("✅  Digest enviado com sucesso.")


if __name__ == "__main__":
    main()