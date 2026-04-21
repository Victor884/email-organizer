"""
classifier.py
─────────────────────────────────────────────────────────────────────────────
Responsabilidade única: classificar e analisar emails via Groq.
A formatação Telegram fica toda em telegram_sender.py.

Fluxo por email:
  1. classify_email()  → categoria via regex (fallback: LLM, 10 tokens)
  2. analisar_vaga()   → análise estruturada via LLM → retorna EmailAnalise
  3. classify_all()    → orquestra tudo, devolve dict[categoria → lista]
─────────────────────────────────────────────────────────────────────────────
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from groq import Groq

# ─────────────────────────────────────────────────────────────────────────────
#  CLIENTE & MODELO
# ─────────────────────────────────────────────────────────────────────────────

client     = Groq(api_key=os.environ["GROQ_API_KEY"])
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama3-70b-8192")

# ─────────────────────────────────────────────────────────────────────────────
#  SCHEMA DE SAÍDA  (dataclasses funcionam como contrato + documentação)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VagaPotencial:
    cargo:       Optional[str]
    empresa:     Optional[str]
    senioridade: str                    # junior | pleno | senior | nao_informado
    modalidade:  str                    # remoto | hibrido | presencial | nao_informado
    local:       Optional[str]
    salario:     Optional[str]
    techs_match: list[str]
    link:        Optional[str]
    relevante:   bool

@dataclass
class EmailAnalise:
    # ── campos sempre presentes ──
    status:               str           # ver STATUS_PRIORIDADE abaixo
    relevante_para_perfil: bool
    resumo:               str           # 1 frase objetiva

    # ── campos de vaga direta ──
    cargo:       Optional[str]  = None
    empresa:     Optional[str]  = None
    senioridade: str            = "nao_informado"
    modalidade:  str            = "nao_informado"
    local:       Optional[str]  = None
    salario:     Optional[str]  = None
    techs_match: list[str]      = field(default_factory=list)
    link:        Optional[str]  = None

    # ── lista de vagas (somente para status == vaga_potencial) ──
    vagas_potenciais: list[VagaPotencial] = field(default_factory=list)

    # ── auditoria ──
    motivo_irrelevante: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
#  PERFIL DO CANDIDATO
# ─────────────────────────────────────────────────────────────────────────────

_CARGOS_ALVO = [
    "Analista de Dados", "Engenheiro de Dados", "Data Analyst", "Data Engineer",
    "Analista de BI", "BI Analyst", "Business Intelligence", "Analytics Engineer",
    "Data Scientist",
]
_SENIORIDADES_ALVO = ["Junior", "Pleno"]
_STACK = [
    # Engenharia
    "IBM DataStage", "Apache Spark", "PySpark", "Databricks", "ETL", "ELT", "Apache Airflow",
    # Bancos
    "IBM DB2", "MySQL", "SQL", "Modelagem Relacional", "Erwin Data Modeler",
    # Linguagens / libs
    "Python", "Pandas", "NumPy", "Scikit-learn", "JavaScript", "Node.js",
    # Cloud / infra
    "Docker", "AWS", "GCP", "Azure", "SAS",
    # DevOps / automação
    "Power Automate", "Git", "GitHub",
    # Visualização
    "Power BI", "Spotfire", "Matplotlib", "Seaborn", "Plotly",
]

# String compacta injetada no prompt (economiza tokens vs. JSON aninhado)
PERFIL_PROMPT = (
    f"Cargos alvo: {', '.join(_CARGOS_ALVO)}\n"
    f"Senioridades alvo: {', '.join(_SENIORIDADES_ALVO)}\n"
    f"Stack do candidato: {', '.join(_STACK)}"
)


# ─────────────────────────────────────────────────────────────────────────────
#  PRIORIDADES & CATEGORIAS
# ─────────────────────────────────────────────────────────────────────────────

# Menor número = exibir primeiro no Telegram
STATUS_PRIORIDADE: dict[str, int] = {
    "proposta":            0,
    "entrevista_agendada": 1,
    "avanco_etapa":        2,
    "nova_vaga":           3,
    "vaga_potencial":      4,
    "aguardando":          5,
    "reprovado":           6,
    "outro":               7,
}

CATEGORIES: dict[str, list[str]] = {
    "vagas": [
        "vaga", "emprego", "oportunidade", "contratação", "hiring", "job",
        "linkedin", "recrutador", "recruiter", "processo seletivo", "candidatura",
        "entrevista", "interview", "posição", "position", "oferta",
        "estamos buscando", "looking for", "we are hiring", "join our team", "faça parte",
    ],
    "treinamento": [
        "treinamento", "curso", "certificação", "capacitação", "training",
        "udemy", "coursera", "alura", "dio", "bootcamp", "mentoria",
    ],
    "workshops":   ["workshop", "webinar", "evento", "meetup", "hackathon", "palestra", "summit"],
    "newsletters": ["newsletter", "digest", "weekly", "semanal", "unsubscribe", "cancelar inscrição"],
    "financeiro":  ["fatura", "boleto", "pagamento", "nota fiscal", "invoice", "cobrança", "extrato"],
    "outros":      [],
}

# Compilados uma vez na inicialização do módulo
_CATEGORY_PATTERNS: dict[str, re.Pattern] = {
    cat: re.compile("|".join(re.escape(kw) for kw in kws), re.IGNORECASE)
    for cat, kws in CATEGORIES.items()
    if kws
}


# ─────────────────────────────────────────────────────────────────────────────
#  CLASSIFICAÇÃO DE CATEGORIA  (regex-first, LLM como fallback de 10 tokens)
# ─────────────────────────────────────────────────────────────────────────────

def classify_email(subject: str, snippet: str) -> str:
    """Retorna uma das chaves de CATEGORIES para o email recebido."""
    text = f"{subject} {snippet}"
    for cat, pattern in _CATEGORY_PATTERNS.items():
        if pattern.search(text):
            return cat

    # Fallback LLM — mínimo de tokens possível
    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{
            "role": "user",
            "content": (
                "Classifique em UMA palavra: vagas | treinamento | workshops | "
                "newsletters | financeiro | outros\n"
                f"Assunto: {subject}\nTrecho: {snippet[:200]}"
            ),
        }],
        max_tokens=5,
        temperature=0,
    )
    cat = (resp.choices[0].message.content or "outros").strip().lower()
    return cat if cat in CATEGORIES else "outros"


# ─────────────────────────────────────────────────────────────────────────────
#  PROMPT DE ANÁLISE DE VAGA  (system + user separados = melhor aderência ao JSON)
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_ANALISE = """\
Você é um parser de emails de recrutamento. Retorne SOMENTE JSON válido, sem markdown, \
sem texto extra, sem comentários. Siga o schema fornecido à risca.\
"""

_USER_ANALISE = """\
PERFIL DO CANDIDATO:
{perfil}

EMAIL:
Assunto: {subject}
Trecho : {snippet}
Corpo  : {body}

STATUS POSSÍVEIS:
proposta | entrevista_agendada | avanco_etapa | nova_vaga | vaga_potencial | aguardando | reprovado | outro

REGRAS:
- vaga_potencial → newsletter/digest com LISTA de vagas; preencha "vagas_potenciais"
- nova_vaga      → recrutador contatou sobre UMA vaga específica
- relevante_para_perfil = true SOMENTE se cargo e senioridade batem com o perfil
- resumo: 1 frase objetiva ("Recrutador da X oferece vaga de Y Pleno Remoto em Python/SQL")
- Extraia todos os links http/https, encurtados (bit.ly etc) e Markdown [texto](url)
- Campos não encontrados → null  |  listas não encontradas → []

JSON DE SAÍDA:
{{
  "status": "",
  "relevante_para_perfil": true,
  "resumo": "",
  "cargo": null,
  "empresa": null,
  "senioridade": "nao_informado",
  "modalidade": "nao_informado",
  "local": null,
  "salario": null,
  "techs_match": [],
  "link": null,
  "vagas_potenciais": [
    {{
      "cargo": "", "empresa": null, "senioridade": "nao_informado",
      "modalidade": "nao_informado", "local": null, "salario": null,
      "techs_match": [], "link": null, "relevante": true
    }}
  ],
  "motivo_irrelevante": null
}}\
"""

# Fallback quando a API falha ou retorna JSON inválido
_FALLBACK_ANALISE = EmailAnalise(
    status="outro",
    relevante_para_perfil=False,
    resumo="",
    motivo_irrelevante="Falha ao processar via API",
)


def _parse_analise(raw: dict) -> EmailAnalise:
    """Converte o dict bruto da API no dataclass EmailAnalise."""
    potenciais = [
        VagaPotencial(
            cargo       = v.get("cargo"),
            empresa     = v.get("empresa"),
            senioridade = v.get("senioridade", "nao_informado"),
            modalidade  = v.get("modalidade",  "nao_informado"),
            local       = v.get("local"),
            salario     = v.get("salario"),
            techs_match = v.get("techs_match") or [],
            link        = v.get("link"),
            relevante   = bool(v.get("relevante", False)),
        )
        for v in (raw.get("vagas_potenciais") or [])
    ]
    return EmailAnalise(
        status                = raw.get("status", "outro"),
        relevante_para_perfil = bool(raw.get("relevante_para_perfil", False)),
        resumo                = raw.get("resumo", ""),
        cargo                 = raw.get("cargo"),
        empresa               = raw.get("empresa"),
        senioridade           = raw.get("senioridade", "nao_informado"),
        modalidade            = raw.get("modalidade",  "nao_informado"),
        local                 = raw.get("local"),
        salario               = raw.get("salario"),
        techs_match           = raw.get("techs_match") or [],
        link                  = raw.get("link"),
        vagas_potenciais      = potenciais,
        motivo_irrelevante    = raw.get("motivo_irrelevante"),
    )


def analisar_vaga(email: dict) -> EmailAnalise:
    """Chama o LLM e devolve um EmailAnalise tipado."""
    user_prompt = _USER_ANALISE.format(
        perfil  = PERFIL_PROMPT,
        subject = email.get("subject", ""),
        snippet = email.get("snippet", ""),
        body    = email.get("body", "")[:2000],
    )
    try:
        resp = client.chat.completions.create(
            model    = GROQ_MODEL,
            messages = [
                {"role": "system", "content": _SYSTEM_ANALISE},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens  = 900,   # suficiente para vaga_potencial com 10 vagas
            temperature = 0,
        )
        raw = (resp.choices[0].message.content or "{}").strip()
        # Remove fences caso o modelo desobedeça o system prompt
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return _parse_analise(json.loads(raw))

    except json.JSONDecodeError:
        return EmailAnalise(
            **{**_FALLBACK_ANALISE.__dict__,
               "motivo_irrelevante": "JSON inválido retornado pela API"}
        )
    except Exception as exc:
        print(f"[classifier] Erro na análise: {exc}")
        return EmailAnalise(
            **{**_FALLBACK_ANALISE.__dict__,
               "motivo_irrelevante": f"Erro de API: {type(exc).__name__}"}
        )


# ─────────────────────────────────────────────────────────────────────────────
#  PIPELINE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def classify_all(emails: list[dict]) -> dict[str, list[dict]]:
    """
    Classifica e analisa todos os emails.

    Retorna:
        dict  categoria → lista de emails
              Cada email de 'vagas' ganha a chave 'analise': EmailAnalise
              As vagas são ordenadas por: relevância → prioridade de status
    """
    result: dict[str, list] = {cat: [] for cat in CATEGORIES}

    for email in emails:
        cat = classify_email(email.get("subject", ""), email.get("snippet", ""))
        if cat not in result:
            cat = "outros"

        if cat == "vagas":
            email["analise"] = analisar_vaga(email)

        result[cat].append(email)

    result["vagas"].sort(key=lambda e: (
        0 if e.get("analise") and e["analise"].relevante_para_perfil else 1,
        STATUS_PRIORIDADE.get(
            e["analise"].status if e.get("analise") else "outro", 7
        ),
    ))

    return result