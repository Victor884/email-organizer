import hashlib
import json
import os
from datetime import datetime, timedelta
from gmail_reader import get_emails_since_yesterday
from classifier import classify_all
from telegram_sender import send_digest

CACHE_FILE = 'processed_emails.json'  # Armazena hashes de emails processados

def get_email_hash(email: dict) -> str:
    """Gera hash único do email para detectar duplicatas."""
    key = f"{email['subject']}{email['sender']}{email.get('snippet', '')}"
    return hashlib.md5(key.encode()).hexdigest()

def load_cache() -> dict:
    """Carrega cache de emails processados (últimos 7 dias)."""
    if not os.path.exists(CACHE_FILE):
        return {}
    
    try:
        with open(CACHE_FILE, 'r') as f:
            cache = json.load(f)
        
        # Remove entradas com mais de 7 dias
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        cache = {k: v for k, v in cache.items() if v.get('date', '') > cutoff}
        return cache
    except:
        return {}

def save_cache(cache: dict):
    """Salva cache atualizado."""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"Aviso: não foi possível salvar cache ({e})")

def main():
    print("Lendo emails...")
    emails = get_emails_since_yesterday()
    print(f"{len(emails)} emails encontrados.")
    
    # Carrega cache de processados
    cache = load_cache()
    
    # Filtra emails já processados (evita reprocessar)
    emails_novos = []
    for email in emails:
        email_hash = get_email_hash(email)
        if email_hash not in cache:
            emails_novos.append(email)
    
    if not emails_novos:
        print(f"Todos os {len(emails)} emails já foram processados. Abortando.")
        return
    
    print(f"Processando {len(emails_novos)} emails novos (ignorando {len(emails) - len(emails_novos)} duplicatas)...")
    
    print("Classificando...")
    classified = classify_all(emails_novos)
    
    print("Enviando para o Telegram...")
    send_digest(classified)
    
    # Atualiza cache com novos emails
    for email in emails_novos:
        email_hash = get_email_hash(email)
        cache[email_hash] = {'date': datetime.now().isoformat()}
    save_cache(cache)
    
    print("Digest enviado com sucesso!")

if __name__ == "__main__":
    main()