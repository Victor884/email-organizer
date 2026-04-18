from gmail_reader import get_emails_since_yesterday
from classifier import classify_all
from telegram_sender import send_digest

def main():
    print("Lendo emails...")
    emails = get_emails_since_yesterday()
    print(f"{len(emails)} emails encontrados.")
    
    print("Classificando...")
    classified = classify_all(emails)
    
    print("Enviando para o Telegram...")
    send_digest(classified)
    print("Digest enviado com sucesso!")

if __name__ == "__main__":
    main()