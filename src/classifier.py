import os
from groq import Groq

CATEGORIES = {
    'vagas':       ['vaga', 'emprego', 'oportunidade', 'contratação', 'hiring', 'job',
                    'linkedin', 'recrutador', 'recruiter', 'processo seletivo', 'candidatura',
                    'entrevista', 'interview', 'posição', 'position', 'oferta'],
    'treinamento': ['treinamento', 'curso', 'certificação', 'capacitação', 'training',
                    'udemy', 'coursera', 'alura', 'dio', 'bootcamp', 'mentoria'],
    'workshops':   ['workshop', 'webinar', 'evento', 'meetup', 'hackathon', 'palestra', 'summit'],
    'newsletters': ['newsletter', 'digest', 'weekly', 'semanal', 'unsubscribe', 'cancelar inscrição'],
    'financeiro':  ['fatura', 'boleto', 'pagamento', 'nota fiscal', 'invoice', 'cobrança', 'extrato'],
    'outros':      []
}

MEU_PERFIL = {
    'cargos': ['analista de dados', 'engenheiro de dados', 'data analyst', 'data engineer',
               'analista de bi', 'bi analyst', 'business intelligence', 'analytics engineer',
               'analytics', 'dados', 'data'],
    'senioridades': ['pleno', 'sênior', 'senior', 'sr.', 'sr ', 'pl.', 'pl ', 'mid-level', 'mid level'],
    'techs': ['python', 'sql', 'spark', 'dbt', 'airflow', 'power bi', 'tableau', 'looker',
              'bigquery', 'redshift', 'snowflake', 'databricks', 'aws', 'gcp', 'azure',
              'pandas', 'pyspark', 'kafka', 'datalake', 'data warehouse', 'etl', 'elt']
}

client = Groq(api_key=os.environ['GROQ_API_KEY'])
GROQ_MODEL = os.getenv('GROQ_MODEL', 'llama-3.1-8b-instant')


def classify_email(subject: str, snippet: str) -> str:
    text = f"{subject} {snippet}".lower()
    for category, keywords in CATEGORIES.items():
        if any(kw in text for kw in keywords):
            return category
    prompt = f"""Classifique este email em UMA das categorias: vagas, treinamento, workshops, newsletters, financeiro, outros.
Assunto: {subject}
Trecho: {snippet}
Responda APENAS com o nome da categoria, sem mais nada."""
    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=10,
        temperature=0
    )
    return (resp.choices[0].message.content or 'outros').strip().lower()


def _perfil_match_rapido(subject: str, snippet: str) -> bool:
    """Verifica rapidamente se o email tem chance de ser relevante para o perfil."""
    text = f"{subject} {snippet}".lower()
    tem_cargo = any(c in text for c in MEU_PERFIL['cargos'])
    tem_senioridade = any(s in text for s in MEU_PERFIL['senioridades'])
    # Relevante se mencionar cargo E (senioridade OU tech conhecida)
    tem_tech = any(t in text for t in MEU_PERFIL['techs'])
    return tem_cargo or (tem_tech and ('vaga' in text or 'job' in text or 'oportunidade' in text))


def analisar_vaga(email: dict) -> dict:
    """
    Usa Groq para extrair informações estruturadas de um email de vaga.
    Retorna dict com análise completa.
    """
    subject = email.get('subject', '')
    snippet = email.get('snippet', '')
    body    = email.get('body', '')[:1500]  # limite para não estourar tokens

    prompt = f"""Você é um assistente que analisa emails de recrutamento para um profissional de dados.

PERFIL DO CANDIDATO:
- Cargos desejados: Analista de Dados, Engenheiro de Dados, Analista de BI
- Senioridade: Pleno ou Sênior
- Tecnologias: Python, SQL, Spark, dbt, Airflow, Power BI, Tableau, BigQuery, Redshift, Snowflake, Databricks, AWS, GCP, Azure

EMAIL:
Assunto: {subject}
Trecho: {snippet}
Corpo: {body}

Responda EXATAMENTE neste formato JSON (sem markdown, sem explicação, só o JSON):
{{
  "cargo": "nome do cargo ou null",
  "empresa": "nome da empresa ou null",
  "senioridade": "junior/pleno/senior/nao_informado",
  "modalidade": "remoto/hibrido/presencial/nao_informado",
  "local": "cidade/estado ou null",
  "salario": "faixa salarial mencionada ou null",
  "techs_match": ["lista de tecnologias do meu perfil que a vaga menciona"],
  "status": "nova_vaga/entrevista_agendada/avanco_etapa/reprovado/proposta/aguardando/outro",
  "resumo": "resumo em 1-2 frases do que se trata o email",
  "relevante_para_perfil": true/false,
  "motivo_irrelevante": "motivo se nao relevante, senao null"
}}"""

    try:
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0
        )
        import json
        content = resp.choices[0].message.content or '{}'
        # Remove possível markdown
        content = content.strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
        analise = json.loads(content)
    except Exception as e:
        analise = {
            "cargo": None, "empresa": None, "senioridade": "nao_informado",
            "modalidade": "nao_informado", "local": None, "salario": None,
            "techs_match": [], "status": "outro",
            "resumo": snippet[:120],
            "relevante_para_perfil": False,
            "motivo_irrelevante": f"Erro na análise: {e}"
        }

    return analise


def classify_all(emails: list) -> dict:
    result = {cat: [] for cat in CATEGORIES}

    for email in emails:
        cat = classify_email(email['subject'], email['snippet'])
        if cat not in result:
            cat = 'outros'

        # Análise profunda apenas para vagas
        if cat == 'vagas':
            email['analise'] = analisar_vaga(email)
        
        result[cat].append(email)

    # Ordena vagas: primeiro as relevantes para o perfil, depois por status
    STATUS_ORDEM = {
        'entrevista_agendada': 0,
        'avanco_etapa':        1,
        'proposta':            2,
        'nova_vaga':           3,
        'aguardando':          4,
        'reprovado':           5,
        'outro':               6,
    }
    result['vagas'].sort(key=lambda e: (
        0 if e.get('analise', {}).get('relevante_para_perfil') else 1,
        STATUS_ORDEM.get(e.get('analise', {}).get('status', 'outro'), 6)
    ))

    return result