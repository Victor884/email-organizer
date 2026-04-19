import os, base64, json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


def _build_credentials_from_env(token_data: dict) -> Credentials:
    # Formato esperado pelo from_authorized_user_info.
    token = token_data.get('token') or token_data.get('access_token')
    client_id = token_data.get('client_id') or os.environ.get('GMAIL_CLIENT_ID')
    client_secret = token_data.get('client_secret') or os.environ.get('GMAIL_CLIENT_SECRET')
    refresh_token = token_data.get('refresh_token') or os.environ.get('GMAIL_REFRESH_TOKEN')

    if token and client_id and client_secret and refresh_token:
        normalized = {
            'token': token,
            'client_id': client_id,
            'client_secret': client_secret,
            'refresh_token': refresh_token,
            'token_uri': token_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
            'scopes': token_data.get('scopes', SCOPES),
        }
        return Credentials.from_authorized_user_info(normalized, SCOPES)

    # Fallback: permite execução com access token temporário sem refresh.
    if token:
        return Credentials(token=token, scopes=SCOPES)

    raise ValueError(
        "GMAIL_TOKEN inválido: informe JSON com ao menos 'token' ou 'access_token'. "
        "Para uso estável no Actions, inclua também client_id, client_secret e refresh_token "
        "(no GMAIL_TOKEN ou em secrets separados GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN)."
    )

def get_service():
    """Carrega credenciais do ambiente (GMAIL_TOKEN) e retorna o serviço Gmail."""
    token_json_str = os.environ.get('GMAIL_TOKEN')
    
    if not token_json_str:
        raise ValueError(
            "Variável de ambiente GMAIL_TOKEN não configurada.\n"
            "Execute: python auth_interactive.py\n"
            "E copie o JSON resultante para GitHub Secrets"
        )

    try:
        token_data = json.loads(token_json_str)
    except json.JSONDecodeError as exc:
        raise ValueError("GMAIL_TOKEN não está em JSON válido.") from exc

    if not isinstance(token_data, dict):
        raise ValueError("GMAIL_TOKEN deve ser um objeto JSON.")

    creds = _build_credentials_from_env(token_data)
    return build('gmail', 'v1', credentials=creds)

def get_emails_since_yesterday():
    service = get_service()
    since = (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d')
    result = service.users().messages().list(
        userId='me', q=f'after:{since} is:unread'
    ).execute()
    
    emails = []
    for msg in result.get('messages', [])[:50]:  # max 50
        data = service.users().messages().get(
            userId='me', id=msg['id'], format='full'
        ).execute()
        
        headers = {h['name']: h['value'] for h in data['payload']['headers']}
        body = extract_body(data['payload'])
        emails.append({
            'subject': headers.get('Subject', '(sem assunto)'),
            'sender':  headers.get('From', ''),
            'snippet': data.get('snippet', ''),
            'body':    body[:500]
        })
    return emails

def extract_body(payload):
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain':
                data = part['body'].get('data', '')
                return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
    data = payload.get('body', {}).get('data', '')
    if data:
        return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
    return ''