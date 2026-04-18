import os
import requests
from datetime import datetime

ICONS = {
    'vagas':       '💼',
    'treinamento': '📚',
    'workshops':   '🎯',
    'newsletters': '📰',
    'financeiro':  '💰',
    'outros':      '📌'
}

def send_digest(classified: dict):
    token   = os.environ['TELEGRAM_TOKEN']
    chat_id = os.environ['TELEGRAM_CHAT_ID']
    
    total = sum(len(v) for v in classified.values())
    date  = datetime.now().strftime('%d/%m/%Y')
    
    msg = f"📬 *Digest de Emails — {date}*\n"
    msg += f"_{total} emails recebidos nas últimas 24h_\n\n"
    
    for category, emails in classified.items():
        if not emails:
            continue
        icon = ICONS.get(category, '📌')
        msg += f"{icon} *{category.capitalize()}* ({len(emails)})\n"
        for e in emails[:5]:  # máximo 5 por categoria
            sender = e['sender'].split('<')[0].strip()[:30]
            subject = e['subject'][:60]
            msg += f"  • {subject}\n    _de: {sender}_\n"
        if len(emails) > 5:
            msg += f"  _...e mais {len(emails) - 5}_\n"
        msg += "\n"
    
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}
    )