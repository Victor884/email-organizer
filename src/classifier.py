import os
import json
import re
from groq import Groq
from functools import lru_cache

CATEGORIES = {
    'vagas':       ['vaga', 'emprego', 'oportunidade', 'contratação', 'hiring', 'job',
                    'linkedin', 'recrutador', 'recruiter', 'processo seletivo', 'candidatura',
                    'entrevista', 'interview', 'posição', 'position', 'oferta', 'estamos buscando',
                    'looking for', 'we are hiring', 'join our team', 'faça parte'],
    'treinamento': ['treinamento', 'curso', 'certificação', 'capacitação', 'training',
                    'udemy', 'coursera', 'alura', 'dio', 'bootcamp', 'mentoria'],
    'workshops':   ['workshop', 'webinar', 'evento', 'meetup', 'hackathon', 'palestra', 'summit'],
    'newsletters': ['newsletter', 'digest', 'weekly', 'semanal', 'unsubscribe', 'cancelar inscrição'],
    'financeiro':  ['fatura', 'boleto', 'pagamento', 'nota fiscal', 'invoice', 'cobrança', 'extrato'],
    'outros':      []
}

MEU_PERFIL = {
    'cargos': [
        'analista de dados', 'engenheiro de dados', 'data analyst', 'data engineer',
        'analista de bi', 'bi analyst', 'business intelligence', 'analytics engineer',
        'analytics', 'dados', 'data'
    ],
    'senioridades': [
        'pleno', 'sênior', 'senior', 'sr.', 'sr ', 'pl.', 'pl ',
        'mid-level', 'mid level', 'ii', 'iii'
    ],
    'techs': [
        'python', 'sql', 'spark', 'dbt', 'airflow', 'power bi', 'tableau', 'looker',
        'bigquery', 'redshift', 'snowflake', 'databricks', 'aws', 'gcp', 'azure',
        'pandas', 'pyspark', 'kafka', 'datalake', 'data warehouse', 'etl', 'elt',
        'metabase', 'superset', 'data studio', 'excel', 'google sheets'
    ]
}

client = Groq(api_key=os.environ['GROQ_API_KEY'])
GROQ_MODEL = os.getenv('GROQ_MODEL', 'gpt-4o-20b')  # Mudado para GPT OSS 20B (mais rápido)

# Compilar patterns de keywords uma só vez (melhora performance)
CATEGORY_PATTERNS = {}
for category, keywords in CATEGORIES.items():
    # Cria regex pattern para search mais eficiente
    CATEGORY_PATTERNS[category] = re.compile(
        '|'.join(re.escape(kw) for kw in keywords),
        re.IGNORECASE
    )


def classify_email(subject: str, snippet: str) -> str:
    text = f"{subject} {snippet}"
    for category, pattern in CATEGORY_PATTERNS.items():
        if pattern.search(text):  # Mais rápido que loop with 'any()'
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


def analisar_vaga(email: dict) -> dict:
    subject = email.get('subject', '')
    snippet = email.get('snippet', '')
    body    = email.get('body', '')[:2000]

    prompt = f"""Você analisa emails de recrutamento para um profissional de dados.

PERFIL DO CANDIDATO:
- Cargos desejados: Analista de Dados, Engenheiro de Dados, Analista de BI
- Senioridade buscada: Pleno ou Sênior
- Tecnologias dominadas: Python, SQL, Spark, dbt, Airflow, Power BI, Tableau, Looker,
  BigQuery, Redshift, Snowflake, Databricks, AWS, GCP, Azure, Pandas, PySpark, Kafka

EMAIL:
Assunto: {subject}
Trecho: {snippet}
Corpo: {body}

DEFINICOES DE STATUS:
- "vaga_potencial": email com listagem de vagas abertas (newsletters de emprego, LinkedIn Jobs,
  Gupy digest, Catho, InfoJobs) onde o candidato AINDA NAO se inscreveu. Pode conter varias vagas.
- "nova_vaga": recrutador entrou em contato diretamente sobre UMA vaga especifica ja direcionada ao candidato.
- "entrevista_agendada": confirmacao ou convite para entrevista.
- "avanco_etapa": aprovacao para proxima fase do processo.
- "proposta": oferta formal de emprego.
- "aguardando": candidato esta em processo mas sem novidades.
- "reprovado": candidato foi reprovado.
- "outro": email de recrutamento que nao se encaixa nos anteriores.

INSTRUCOES IMPORTANTES:
- Sempre busque e extraia URLs/links diretos para candidatar-se ou acessar a vaga
- Procure por links HTTP(S), URLs encurtadas (bit.ly, tinyurl, etc) e links em markdown [texto](url)
- Para vagas_potenciais de newsletters, extraia a URL/link de cada vaga individual listada
- Se nao encontrar link direto, coloque null

Responda EXATAMENTE neste JSON sem markdown e sem texto extra:
{{
  "cargo": "cargo principal ou null",
  "empresa": "empresa ou null",
  "senioridade": "junior/pleno/senior/nao_informado",
  "modalidade": "remoto/hibrido/presencial/nao_informado",
  "local": "cidade/estado ou null",
  "salario": "faixa salarial ou null",
  "techs_match": ["tecnologias do perfil mencionadas"],
  "link": "URL direta para a vaga ou null",
  "status": "nova_vaga/vaga_potencial/entrevista_agendada/avanco_etapa/reprovado/proposta/aguardando/outro",
  "vagas_potenciais": [
    {{
      "cargo": "nome do cargo",
      "empresa": "empresa ou null",
      "senioridade": "pleno/senior/junior/nao_informado",
      "modalidade": "remoto/hibrido/presencial/nao_informado",
      "local": "cidade ou null",
      "salario": "faixa ou null",
      "techs_match": ["techs que batem com o perfil"],
      "relevante": true,
      "link": "URL direta para a vaga ou null"
    }}
  ],
  "resumo": "resumo em 1-2 frases do email",
  "relevante_para_perfil": true/false,
  "motivo_irrelevante": "motivo se nao relevante, senao null"
}}

Preencha "vagas_potenciais" SOMENTE quando status for "vaga_potencial", listando cada vaga encontrada.
Marque "relevante" como true apenas para cargos Analista/Engenheiro de Dados ou BI Pleno/Senior.
Se nao houver vagas potenciais use lista vazia []."""

    try:
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0
        )
        content = (resp.choices[0].message.content or '{}').strip()
        content = content.removeprefix('```json').removeprefix('```').removesuffix('```').strip()
        analise = json.loads(content)
        if 'vagas_potenciais' not in analise:
            analise['vagas_potenciais'] = []
    except json.JSONDecodeError as e:
        # JSON inválido da IA - fallback básico
        analise = {
            "cargo": None, "empresa": None, "senioridade": "nao_informado",
            "modalidade": "nao_informado", "local": None, "salario": None,
            "techs_match": [], "link": None, "status": "outro",
            "vagas_potenciais": [],
            "resumo": snippet[:120],
            "relevante_para_perfil": False,
            "motivo_irrelevante": f"JSON inválido da API"
        }
    except Exception as e:
        # Outras falhas (timeout, rate limit, etc)
        print(f"Erro na análise da vaga: {e}")
        analise = {
            "cargo": None, "empresa": None, "senioridade": "nao_informado",
            "modalidade": "nao_informado", "local": None, "salario": None,
            "techs_match": [], "link": None, "status": "outro",
            "vagas_potenciais": [],
            "resumo": snippet[:120],
            "relevante_para_perfil": False,
            "motivo_irrelevante": f"Erro de API: {type(e).__name__}"
        }

    return analise


def classify_all(emails: list) -> dict:
    result = {cat: [] for cat in CATEGORIES}

    for email in emails:
        cat = classify_email(email['subject'], email['snippet'])
        if cat not in result:
            cat = 'outros'
        if cat == 'vagas':
            email['analise'] = analisar_vaga(email)
        result[cat].append(email)

    STATUS_ORDEM = {
        'entrevista_agendada': 0,
        'avanco_etapa':        1,
        'proposta':            2,
        'nova_vaga':           3,
        'vaga_potencial':      4,
        'aguardando':          5,
        'reprovado':           6,
        'outro':               7,
    }
    result['vagas'].sort(key=lambda e: (
        0 if e.get('analise', {}).get('relevante_para_perfil') else 1,
        STATUS_ORDEM.get(e.get('analise', {}).get('status', 'outro'), 7)
    ))

    return result