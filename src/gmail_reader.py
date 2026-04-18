import os, base64, json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_service():
    token_data = json.loads(os.environ['GMAIL_TOKEN'])
    creds = Credentials.from_authorized_user_info(token_data, SCOPES)
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
            userId='me', messageId=msg['id'], format='full'
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