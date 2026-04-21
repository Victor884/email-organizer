"""
classifier.py
─────────────────────────────────────────────────────────────────────────────
Pipeline:
  1. classify_email()  → categoria (regex-first, LLM fallback 5 tokens)
  2. analisar_vaga()   → LLM devolve JSON → EmailAnalise com match_score
  3. classify_all()    → orquestra, ordena por match_score desc

Novidades vs versão anterior:
  • match_score 0–100: calculado pelo LLM (cargo 35 + senioridade 25 + stack 25 + local 15)
  • Threshold MATCH_THRESHOLD_PCT: vagas abaixo vão para "Radar", não "Direct Match"
  • Filtro de localização: Remoto✓ | Híbrido/Presencial só se Brasília/DF
  • link_candidatura: campo separado, LLM instruído a ignorar logo/unsubscribe/homepage
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from groq import Groq

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────────────────────

client     = Groq(api_key=os.environ["GROQ_API_KEY"])
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama3-70b-8192")

# Vagas com score abaixo disso vão para o bloco "Radar", não "Direct Match"
MATCH_THRESHOLD_PCT: int = 40


# ─────────────────────────────────────────────────────────────────────────────
#  PERFIL DO CANDIDATO  (fonte de verdade — usada no prompt E no scorer)
# ─────────────────────────────────────────────────────────────────────────────

CARGOS_ALVO = [
    "Analista de Dados", "Engenheiro de Dados", "Data Analyst", "Data Engineer",
    "Analista de BI", "BI Analyst", "Business Intelligence", "Analytics Engineer",
    "Data Scientist",
]
SENIORIDADES_ALVO = ["Junior", "Pleno"]

STACK: dict[str, list[str]] = {
    "engenharia":   ["IBM DataStage", "Apache Spark", "PySpark", "Databricks", "ETL", "ELT", "Apache Airflow"],
    "bancos":       ["IBM DB2", "MySQL", "SQL", "Modelagem Relacional", "Erwin Data Modeler"],
    "linguagens":   ["Python", "Pandas", "NumPy", "Scikit-learn", "JavaScript", "Node.js"],
    "cloud":        ["Docker", "AWS", "GCP", "Azure", "SAS"],
    "devops":       ["Power Automate", "Git", "GitHub"],
    "visualizacao": ["Power BI", "Spotfire", "Matplotlib", "Seaborn", "Plotly"],
}
STACK_FLAT: list[str] = [t for techs in STACK.values() for t in techs]

# Localização: remoto sempre ok; híbrido/presencial só em Brasília
_LOC_BRASILIA = ["brasilia", "brasília", "df", "distrito federal"]

_PERFIL_PROMPT = (
    f"Cargos: {', '.join(CARGOS_ALVO)}\n"
    f"Senioridades: {', '.join(SENIORIDADES_ALVO)}\n"
    f"Stack: {', '.join(STACK_FLAT)}\n"
    "Localização aceita: Remoto (qualquer lugar) | Híbrido ou Presencial somente em Brasília/DF"
)


# ─────────────────────────────────────────────────────────────────────────────
#  SCHEMA DE DADOS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VagaPotencial:
    cargo:            Optional[str]
    empresa:          Optional[str]
    senioridade:      str               # junior|pleno|senior|nao_informado
    modalidade:       str               # remoto|hibrido|presencial|nao_informado
    local:            Optional[str]
    salario:          Optional[str]
    techs_match:      list[str]
    link_candidatura: Optional[str]     # link direto de candidatura
    match_score:      int               # 0–100
    match_label:      str               # perfeito|bom|parcial|fraco

@dataclass
class EmailAnalise:
    status:               str           # ver STATUS_PRIORIDADE
    relevante_para_perfil: bool
    match_score:          int           # 0–100
    match_label:          str           # perfeito|bom|parcial|fraco
    resumo:               str

    cargo:            Optional[str]  = None
    empresa:          Optional[str]  = None
    senioridade:      str            = "nao_informado"
    modalidade:       str            = "nao_informado"
    local:            Optional[str]  = None
    salario:          Optional[str]  = None
    techs_match:      list[str]      = field(default_factory=list)
    link_candidatura: Optional[str]  = None

    vagas_potenciais:   list[VagaPotencial] = field(default_factory=list)
    motivo_irrelevante: Optional[str]       = None


# ─────────────────────────────────────────────────────────────────────────────
#  PRIORIDADES & CATEGORIAS
# ─────────────────────────────────────────────────────────────────────────────

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

_CATEGORY_PATTERNS: dict[str, re.Pattern] = {
    cat: re.compile("|".join(re.escape(kw) for kw in kws), re.IGNORECASE)
    for cat, kws in CATEGORIES.items()
    if kws
}


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _match_label(score: int) -> str:
    if score >= 80: return "perfeito"
    if score >= 60: return "bom"
    if score >= 40: return "parcial"
    return "fraco"


def _loc_aceita(modalidade: str, local: Optional[str]) -> bool:
    """True se modalidade+local é compatível com o perfil do candidato."""
    mod = (modalidade or "").lower()
    if mod == "remoto":
        return True
    if mod in ("hibrido", "presencial"):
        if not local:
            return False
        loc = local.lower()
        return any(bsb in loc for bsb in _LOC_BRASILIA)
    return True  # nao_informado → não penaliza


# ─────────────────────────────────────────────────────────────────────────────
#  CLASSIFICAÇÃO DE CATEGORIA  (regex-first, LLM como fallback de 5 tokens)
# ─────────────────────────────────────────────────────────────────────────────

def classify_email(subject: str, snippet: str) -> str:
    text = f"{subject} {snippet}"
    for cat, pattern in _CATEGORY_PATTERNS.items():
        if pattern.search(text):
            return cat

    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": (
            "Classifique em UMA palavra: vagas|treinamento|workshops|newsletters|financeiro|outros\n"
            f"Assunto: {subject}\nTrecho: {snippet[:200]}"
        )}],
        max_tokens=5, temperature=0,
    )
    cat = (resp.choices[0].message.content or "outros").strip().lower()
    return cat if cat in CATEGORIES else "outros"


# ─────────────────────────────────────────────────────────────────────────────
#  PROMPTS  (system + user separados = melhor aderência ao JSON no Llama)
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM = (
    "Você é um parser de e-mails de recrutamento. "
    "Retorne SOMENTE JSON válido. Sem markdown, sem texto extra, sem comentários."
)

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
- vaga_potencial → e-mail com LISTA de vagas (digest, Glassdoor, newsletter); preencha vagas_potenciais[]
- nova_vaga      → recrutador fala de UMA vaga específica
- relevante_para_perfil = true se cargo + senioridade + localização batem com o perfil
- match_score 0-100: some pontos — cargo correto +35, senioridade correta +25, ≥1 tech da stack +25, local aceito +15
- resumo: 1 frase objetiva ("Recrutador da X oferece Analista de Dados Pleno Remoto em Python/SQL")
- Campos ausentes → null | listas ausentes → []

REGRA CRÍTICA DE LINK:
- link_candidatura = link de CANDIDATURA DIRETA à vaga
- Busque por âncoras com textos: "Candidatar", "Apply", "Ver vaga", "Apply Now",
  "View Job", "Se inscrever", "Saiba mais", "Candidate-se"
- IGNORE links de: logo, header, rodapé, redes sociais, "unsubscribe",
  "cancelar inscrição", homepage da empresa (ex: https://empresa.com.br)
- Se não encontrar link de candidatura específico → null

JSON ÚNICO DE SAÍDA:
{{
  "status": "",
  "relevante_para_perfil": true,
  "match_score": 0,
  "resumo": "",
  "cargo": null,
  "empresa": null,
  "senioridade": "nao_informado",
  "modalidade": "nao_informado",
  "local": null,
  "salario": null,
  "techs_match": [],
  "link_candidatura": null,
  "vagas_potenciais": [
    {{
      "cargo": "",
      "empresa": null,
      "senioridade": "nao_informado",
      "modalidade": "nao_informado",
      "local": null,
      "salario": null,
      "techs_match": [],
      "link_candidatura": null,
      "match_score": 0
    }}
  ],
  "motivo_irrelevante": null
}}\
"""

_FALLBACK = EmailAnalise(
    status="outro", relevante_para_perfil=False,
    match_score=0, match_label="fraco", resumo="",
    motivo_irrelevante="Falha ao processar",
)


# ─────────────────────────────────────────────────────────────────────────────
#  PARSER  dict → dataclass
# ─────────────────────────────────────────────────────────────────────────────

def _parse_vaga_potencial(v: dict) -> VagaPotencial:
    score = max(0, min(100, int(v.get("match_score") or 0)))
    return VagaPotencial(
        cargo            = v.get("cargo"),
        empresa          = v.get("empresa"),
        senioridade      = v.get("senioridade", "nao_informado"),
        modalidade       = v.get("modalidade",  "nao_informado"),
        local            = v.get("local"),
        salario          = v.get("salario"),
        techs_match      = v.get("techs_match") or [],
        link_candidatura = v.get("link_candidatura"),
        match_score      = score,
        match_label      = _match_label(score),
    )


def _parse_analise(raw: dict) -> EmailAnalise:
    score = max(0, min(100, int(raw.get("match_score") or 0)))
    modal = raw.get("modalidade", "nao_informado")
    local = raw.get("local")

    # Penaliza score se a localização é incompatível (ex: presencial em SP)
    if not _loc_aceita(modal, local):
        score = max(0, score - 30)

    potenciais = [_parse_vaga_potencial(v) for v in (raw.get("vagas_potenciais") or [])]

    # Remove vagas potenciais com localização incompatível
    potenciais = [
        p for p in potenciais
        if p.modalidade == "nao_informado" or _loc_aceita(p.modalidade, p.local)
    ]

    return EmailAnalise(
        status                = raw.get("status", "outro"),
        relevante_para_perfil = bool(raw.get("relevante_para_perfil", False)),
        match_score           = score,
        match_label           = _match_label(score),
        resumo                = raw.get("resumo", ""),
        cargo                 = raw.get("cargo"),
        empresa               = raw.get("empresa"),
        senioridade           = raw.get("senioridade", "nao_informado"),
        modalidade            = modal,
        local                 = local,
        salario               = raw.get("salario"),
        techs_match           = raw.get("techs_match") or [],
        link_candidatura      = raw.get("link_candidatura"),
        vagas_potenciais      = potenciais,
        motivo_irrelevante    = raw.get("motivo_irrelevante"),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  ANÁLISE DE VAGA
# ─────────────────────────────────────────────────────────────────────────────

def analisar_vaga(email: dict) -> EmailAnalise:
    """Chama o LLM e devolve um EmailAnalise tipado com match_score."""
    prompt = _USER_ANALISE.format(
        perfil  = _PERFIL_PROMPT,
        subject = email.get("subject", ""),
        snippet = email.get("snippet", ""),
        body    = email.get("body", "")[:2500],
    )
    try:
        resp = client.chat.completions.create(
            model    = GROQ_MODEL,
            messages = [
                {"role": "system", "content": _SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=1000, temperature=0,
        )
        raw = (resp.choices[0].message.content or "{}").strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return _parse_analise(json.loads(raw))

    except json.JSONDecodeError:
        fb = _FALLBACK.__dict__.copy()
        fb["motivo_irrelevante"] = "JSON inválido da API"
        return EmailAnalise(**fb)
    except Exception as exc:
        print(f"[classifier] Erro: {exc}")
        fb = _FALLBACK.__dict__.copy()
        fb["motivo_irrelevante"] = f"Erro de API: {type(exc).__name__}"
        return EmailAnalise(**fb)


# ─────────────────────────────────────────────────────────────────────────────
#  PIPELINE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def classify_all(emails: list[dict]) -> dict[str, list[dict]]:
    """
    Classifica, analisa e ordena todos os emails.
    Vagas ordenadas por: match_score desc → status_prioridade asc
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
        -(e["analise"].match_score if e.get("analise") else 0),
        STATUS_PRIORIDADE.get(e["analise"].status if e.get("analise") else "outro", 7),
    ))

    return result