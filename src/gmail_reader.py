"""
gmail_reader.py
─────────────────────────────────────────────────────────────────────────────
Responsabilidade única: autenticar na API do Gmail e buscar emails recentes.
Retorna lista de dicts com as chaves: subject, sender, snippet, body.
─────────────────────────────────────────────────────────────────────────────
"""

import base64
import json
import os
from datetime import datetime, timedelta

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Máximo de mensagens a buscar por execução (evita estourar quota)
_MAX_EMAILS = 50
# Caracteres do corpo que o classifier efetivamente usa
_BODY_CHARS  = 500


# ─────────────────────────────────────────────────────────────────────────────
#  AUTENTICAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

def _build_credentials(token_data: dict) -> Credentials:
    """
    Monta Credentials a partir do dict do GMAIL_TOKEN.
    Prefere o fluxo OAuth completo (com refresh_token); usa token temporário
    como fallback para testes locais.
    """
    token         = token_data.get("token") or token_data.get("access_token")
    client_id     = token_data.get("client_id")     or os.getenv("GMAIL_CLIENT_ID")
    client_secret = token_data.get("client_secret") or os.getenv("GMAIL_CLIENT_SECRET")
    refresh_token = token_data.get("refresh_token") or os.getenv("GMAIL_REFRESH_TOKEN")

    # Fluxo completo com refresh automático (recomendado para GitHub Actions)
    if token and client_id and client_secret and refresh_token:
        return Credentials.from_authorized_user_info(
            {
                "token":         token,
                "client_id":     client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "token_uri":     token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
                "scopes":        token_data.get("scopes", SCOPES),
            },
            SCOPES,
        )

    # Fallback: access token temporário (expira em ~1h, ok para testes locais)
    if token:
        return Credentials(token=token, scopes=SCOPES)

    raise ValueError(
        "GMAIL_TOKEN inválido: inclua ao menos 'token'/'access_token'.\n"
        "Para uso estável no GitHub Actions, adicione também:\n"
        "  client_id, client_secret, refresh_token\n"
        "(dentro do JSON ou em secrets separados: GMAIL_CLIENT_ID, "
        "GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN)"
    )


def _get_service():
    """Lê GMAIL_TOKEN do ambiente e retorna o serviço autenticado."""
    raw = os.environ.get("GMAIL_TOKEN")
    if not raw:
        raise EnvironmentError(
            "GMAIL_TOKEN não configurado.\n"
            "Execute auth_interactive.py e adicione o JSON resultante "
            "ao GitHub Secrets."
        )

    try:
        token_data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("GMAIL_TOKEN não está em JSON válido.") from exc

    if not isinstance(token_data, dict):
        raise ValueError("GMAIL_TOKEN deve ser um objeto JSON (chaves e valores).")

    return build("gmail", "v1", credentials=_build_credentials(token_data))


# ─────────────────────────────────────────────────────────────────────────────
#  EXTRAÇÃO DO CORPO
# ─────────────────────────────────────────────────────────────────────────────

def _extract_body(payload: dict) -> str:
    """
    Extrai o texto puro do email.
    Prefere text/plain; ignora HTML para economizar tokens no LLM.
    """
    # Email multipart (preferência: text/plain)
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

    # Email simples (body direto no payload)
    data = payload.get("body", {}).get("data", "")
    if data:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

    return ""


# ─────────────────────────────────────────────────────────────────────────────
#  BUSCA DE EMAILS
# ─────────────────────────────────────────────────────────────────────────────

def get_emails_since_yesterday() -> list[dict]:
    """
    Retorna emails não-lidos das últimas 24h.
    Cada item: { subject, sender, snippet, body }
    """
    service = _get_service()
    since   = (datetime.now() - timedelta(days=1)).strftime("%Y/%m/%d")

    result = service.users().messages().list(
        userId="me",
        q=f"after:{since} is:unread",
    ).execute()

    emails: list[dict] = []
    for msg in result.get("messages", [])[:_MAX_EMAILS]:
        data    = service.users().messages().get(
            userId="me", id=msg["id"], format="full"
        ).execute()
        headers = {h["name"]: h["value"] for h in data["payload"]["headers"]}

        emails.append({
            "subject": headers.get("Subject", "(sem assunto)"),
            "sender":  headers.get("From", ""),
            "snippet": data.get("snippet", ""),
            "body":    _extract_body(data["payload"])[:_BODY_CHARS],
        })

    return emails