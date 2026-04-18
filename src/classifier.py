import os
from groq import Groq

CATEGORIES = {
    'vagas':       ['vaga', 'emprego', 'oportunidade', 'contratação', 'hiring', 'job', 'linkedin'],
    'treinamento': ['treinamento', 'curso', 'certificação', 'capacitação', 'training', 'udemy', 'coursera'],
    'workshops':   ['workshop', 'webinar', 'evento', 'meetup', 'hackathon', 'palestra'],
    'newsletters': ['newsletter', 'digest', 'weekly', 'semanal', 'unsubscribe'],
    'financeiro':  ['fatura', 'boleto', 'pagamento', 'nota fiscal', 'invoice', 'cobrança'],
    'outros':      []
}

client = Groq(api_key=os.environ['GROQ_API_KEY'])

def classify_email(subject: str, snippet: str) -> str:
    text = f"{subject} {snippet}".lower()
    
    # Primeiro tenta palavras-chave (rápido e grátis)
    for category, keywords in CATEGORIES.items():
        if any(kw in text for kw in keywords):
            return category
    
    # Fallback: usa IA para casos ambíguos
    prompt = f"""Classifique este email em UMA das categorias: vagas, treinamento, workshops, newsletters, financeiro, outros.
Assunto: {subject}
Trecho: {snippet}
Responda APENAS com o nome da categoria, nada mais."""

    resp = client.chat.completions.create(
        model="llama3-8b-8192",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=10,
        temperature=0
    )
    content = resp.choices[0].message.content
    return (content or 'outros').strip().lower()

def classify_all(emails: list) -> dict:
    result = {cat: [] for cat in CATEGORIES}
    for email in emails:
        cat = classify_email(email['subject'], email['snippet'])
        if cat not in result:
            cat = 'outros'
        result[cat].append(email)
    return result