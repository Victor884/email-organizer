import os
import json
import re
from groq import Groq

# ─────────────────────────────────────────────
#  CONFIGURAÇÃO
# ─────────────────────────────────────────────

client = Groq(api_key=os.environ["GROQ_API_KEY"])
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama3-70b-8192")

# ─────────────────────────────────────────────
#  CATEGORIAS & KEYWORDS
# ─────────────────────────────────────────────

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

# Compilar regex uma única vez na inicialização
CATEGORY_PATTERNS: dict[str, re.Pattern] = {
    cat: re.compile("|".join(re.escape(kw) for kw in kws), re.IGNORECASE)
    for cat, kws in CATEGORIES.items()
    if kws  # ignora 'outros' que tem lista vazia
}

# ─────────────────────────────────────────────
#  PERFIL DO CANDIDATO
# ─────────────────────────────────────────────

CANDIDATO = {
    "cargos_alvo": [
        "Analista de Dados", "Engenheiro de Dados", "Data Analyst", "Data Engineer",
        "Analista de BI", "BI Analyst", "Business Intelligence", "Analytics Engineer",
        "Data Scientist",
    ],
    "senioridades_alvo": ["Junior", "Pleno"],
    "stack": {
        "engenharia":      ["IBM DataStage", "Apache Spark", "PySpark", "Databricks", "ETL/ELT", "Apache Airflow", "Pipelines de Dados"],
        "bancos":          ["IBM DB2", "MySQL", "SQL", "Modelagem Relacional", "Erwin Data Modeler"],
        "linguagens_libs": ["Python", "Pandas", "NumPy", "PyAutoGUI", "Scikit-learn", "JavaScript", "Node.js"],
        "cloud":           ["Databricks", "Docker", "SAS", "AWS", "GCP", "Azure"],
        "automacao_devops":["Power Automate", "Git", "GitHub", "Scrum", "Kanban"],
        "visualizacao":    ["Power BI", "Spotfire Analytics", "Matplotlib", "Seaborn", "Plotly"],
    },
}

# Texto compacto do perfil para injetar nos prompts
_STACK_FLAT = ", ".join(
    tech for techs in CANDIDATO["stack"].values() for tech in techs
)
PERFIL_RESUMIDO = (
    f"Cargos: {', '.join(CANDIDATO['cargos_alvo'])} | "
    f"Senioridade: {', '.join(CANDIDATO['senioridades_alvo'])} | "
    f"Stack: {_STACK_FLAT}"
)

# ─────────────────────────────────────────────
#  CONSTANTES DE NEGÓCIO
# ─────────────────────────────────────────────

# Prioridade de exibição: menor = mais urgente
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

EMOJI_STATUS: dict[str, str] = {
    "proposta":            "🏆",
    "entrevista_agendada": "📅",
    "avanco_etapa":        "🚀",
    "nova_vaga":           "💼",
    "vaga_potencial":      "📋",
    "aguardando":          "⏳",
    "reprovado":           "❌",
    "outro":               "📩",
}

EMOJI_CATEGORIA: dict[str, str] = {
    "vagas":       "💼",
    "treinamento": "🎓",
    "workshops":   "🛠️",
    "newsletters": "📰",
    "financeiro":  "💰",
    "outros":      "📁",
}

# ─────────────────────────────────────────────
#  CLASSIFICAÇÃO DE CATEGORIA
# ─────────────────────────────────────────────

def classify_email(subject: str, snippet: str) -> str:
    """
    Classifica o email por keyword matching (rápido).
    Usa LLM como fallback apenas quando keywords não resolvem.
    """
    text = f"{subject} {snippet}"

    for category, pattern in CATEGORY_PATTERNS.items():
        if pattern.search(text):
            return category

    # Fallback via LLM
    prompt = (
        "Classifique este email em UMA categoria: vagas, treinamento, workshops, newsletters, financeiro, outros.\n"
        f"Assunto: {subject}\n"
        f"Trecho: {snippet}\n"
        "Responda APENAS com o nome da categoria."
    )
    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=10,
        temperature=0,
    )
    result = (resp.choices[0].message.content or "outros").strip().lower()
    return result if result in CATEGORIES else "outros"


# ─────────────────────────────────────────────
#  ANÁLISE DE VAGAS
# ─────────────────────────────────────────────

_PROMPT_ANALISE_VAGA = """Você é um assistente que analisa emails de recrutamento.

PERFIL DO CANDIDATO:
{perfil}

EMAIL:
Assunto : {subject}
Trecho  : {snippet}
Corpo   : {body}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEFINIÇÕES DE STATUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• vaga_potencial       → newsletter/digest com lista de vagas abertas (candidato ainda não se inscreveu)
• nova_vaga            → recrutador contatou diretamente sobre UMA vaga específica
• entrevista_agendada  → confirmação ou convite de entrevista
• avanco_etapa         → aprovado para próxima fase
• proposta             → oferta formal de emprego
• aguardando           → processo em andamento, sem novidades
• reprovado            → candidato reprovado
• outro                → email de recrutamento que não se encaixa nos anteriores

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INSTRUÇÕES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Extraia links diretos (http/https), URLs encurtadas (bit.ly, etc) e links Markdown [texto](url).
2. Para "vaga_potencial", liste CADA vaga encontrada em "vagas_potenciais".
3. Marque "relevante_para_perfil" = true somente para cargos de Dados/BI em nível Junior ou Pleno.
4. O campo "resumo" deve ser uma frase objetiva no estilo: "Recrutador da [Empresa] oferece vaga de [Cargo] [Senioridade] [Modalidade] com foco em [techs principais]."
5. Se não encontrar um campo, use null.

Responda EXATAMENTE neste JSON (sem markdown, sem texto extra):
{{
  "cargo"                : "cargo principal ou null",
  "empresa"              : "empresa ou null",
  "senioridade"          : "junior | pleno | senior | nao_informado",
  "modalidade"           : "remoto | hibrido | presencial | nao_informado",
  "local"                : "cidade/estado ou null",
  "salario"              : "faixa salarial ou null",
  "techs_match"          : ["tecnologias do perfil mencionadas no email"],
  "link"                 : "URL direta para a vaga ou null",
  "status"               : "nova_vaga | vaga_potencial | entrevista_agendada | avanco_etapa | reprovado | proposta | aguardando | outro",
  "vagas_potenciais"     : [
    {{
      "cargo"      : "nome do cargo",
      "empresa"    : "empresa ou null",
      "senioridade": "junior | pleno | nao_informado",
      "modalidade" : "remoto | hibrido | presencial | nao_informado",
      "local"      : "cidade ou null",
      "salario"    : "faixa ou null",
      "techs_match": ["techs que batem com o perfil"],
      "link"       : "URL direta ou null",
      "relevante"  : true
    }}
  ],
  "resumo"               : "frase objetiva descrevendo o email",
  "relevante_para_perfil": true,
  "motivo_irrelevante"   : "motivo se não relevante, senão null"
}}

Preencha "vagas_potenciais" SOMENTE quando status for "vaga_potencial".
Se não houver vagas potenciais relevantes, use [].
"""

_ANALISE_FALLBACK: dict = {
    "cargo": None, "empresa": None, "senioridade": "nao_informado",
    "modalidade": "nao_informado", "local": None, "salario": None,
    "techs_match": [], "link": None, "status": "outro",
    "vagas_potenciais": [], "resumo": "",
    "relevante_para_perfil": False, "motivo_irrelevante": None,
}


def analisar_vaga(email: dict) -> dict:
    """Envia o email para o LLM e retorna análise estruturada."""
    prompt = _PROMPT_ANALISE_VAGA.format(
        perfil  = PERFIL_RESUMIDO,
        subject = email.get("subject", ""),
        snippet = email.get("snippet", ""),
        body    = email.get("body", "")[:2000],
    )
    try:
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0,
        )
        content = (resp.choices[0].message.content or "{}").strip()
        content = content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        analise = json.loads(content)
        analise.setdefault("vagas_potenciais", [])
        return analise

    except json.JSONDecodeError:
        return {**_ANALISE_FALLBACK, "motivo_irrelevante": "JSON inválido retornado pela API"}
    except Exception as e:
        print(f"[classifier] Erro na análise: {e}")
        return {**_ANALISE_FALLBACK, "motivo_irrelevante": f"Erro de API: {type(e).__name__}"}


# ─────────────────────────────────────────────
#  FORMATAÇÃO PARA TELEGRAM
# ─────────────────────────────────────────────

def _fmt_vaga(analise: dict, subject: str) -> str:
    """Formata uma vaga individual para mensagem Telegram."""
    status  = analise.get("status", "outro")
    emoji   = EMOJI_STATUS.get(status, "📩")
    cargo   = analise.get("cargo") or subject or "Cargo não informado"
    empresa = analise.get("empresa") or "Empresa não informada"
    senior  = analise.get("senioridade", "nao_informado").replace("nao_informado", "—")
    modal   = analise.get("modalidade",  "nao_informado").replace("nao_informado", "—")
    local   = analise.get("local")   or "—"
    salario = analise.get("salario") or "—"
    techs   = ", ".join(analise.get("techs_match") or []) or "—"
    link    = analise.get("link")
    resumo  = analise.get("resumo", "")

    lines = [
        f"{emoji} *{cargo}* — {empresa}",
        f"📊 `{senior}` | 🏠 `{modal}` | 📍 {local}",
        f"💵 {salario}",
        f"🛠 {techs}",
    ]
    if resumo:
        lines.append(f"_{resumo}_")
    if link:
        lines.append(f"🔗 [Acessar vaga]({link})")

    return "\n".join(lines)


def _fmt_vaga_potencial(vaga: dict) -> str:
    """Formata um item de lista de vagas potenciais."""
    cargo   = vaga.get("cargo") or "Cargo não informado"
    empresa = vaga.get("empresa") or "—"
    senior  = vaga.get("senioridade", "nao_informado").replace("nao_informado", "—")
    modal   = vaga.get("modalidade",  "nao_informado").replace("nao_informado", "—")
    techs   = ", ".join(vaga.get("techs_match") or []) or "—"
    link    = vaga.get("link")

    line = f"  • *{cargo}* @ {empresa} | `{senior}` | `{modal}` | 🛠 {techs}"
    if link:
        line += f" | [→ vaga]({link})"
    return line


def format_telegram_summary(classified: dict) -> str:
    """
    Gera o resumo completo formatado para envio via bot Telegram.
    Ordenado por relevância e prioridade de status.
    """
    sections: list[str] = ["🗂 *Resumo de Emails*\n"]

    # ── VAGAS (seção mais importante, detalhada) ──────────────────────────────
    vagas = classified.get("vagas", [])
    if vagas:
        sections.append("━━━━━━━━━━━━━━━━━━━")
        sections.append("💼 *VAGAS*")
        sections.append("━━━━━━━━━━━━━━━━━━━")

        for email in vagas:
            analise = email.get("analise", {})
            block   = _fmt_vaga(analise, email.get("subject", ""))

            # Sub-lista de vagas potenciais (newsletters de emprego)
            potenciais = [v for v in analise.get("vagas_potenciais", []) if v.get("relevante")]
            if potenciais:
                sub = "\n".join(_fmt_vaga_potencial(v) for v in potenciais)
                block += f"\n\n📌 *Vagas relevantes no digest:*\n{sub}"

            sections.append(block)
            sections.append("")  # linha em branco entre vagas

    # ── DEMAIS CATEGORIAS (compactas) ─────────────────────────────────────────
    ordem_categorias = ["treinamento", "workshops", "financeiro", "newsletters", "outros"]

    for cat in ordem_categorias:
        emails = classified.get(cat, [])
        if not emails:
            continue

        emoji = EMOJI_CATEGORIA.get(cat, "📁")
        label = cat.upper()
        sections.append(f"{emoji} *{label}* ({len(emails)})")

        for email in emails:
            subj = email.get("subject", "(sem assunto)")
            snip = email.get("snippet", "")[:80]
            sections.append(f"  • {subj}" + (f"\n    _{snip}_" if snip else ""))

        sections.append("")

    return "\n".join(sections).strip()


# ─────────────────────────────────────────────
#  PIPELINE PRINCIPAL
# ─────────────────────────────────────────────

def classify_all(emails: list[dict]) -> dict[str, list]:
    """
    Classifica todos os emails, analisa vagas e retorna dict por categoria.
    As vagas são ordenadas por: relevância → prioridade de status.
    """
    result: dict[str, list] = {cat: [] for cat in CATEGORIES}

    for email in emails:
        cat = classify_email(email["subject"], email["snippet"])
        if cat not in result:
            cat = "outros"

        if cat == "vagas":
            email["analise"] = analisar_vaga(email)

        result[cat].append(email)

    # Ordenar vagas: relevantes primeiro, depois por status
    result["vagas"].sort(key=lambda e: (
        0 if e.get("analise", {}).get("relevante_para_perfil") else 1,
        STATUS_PRIORIDADE.get(e.get("analise", {}).get("status", "outro"), 7),
    ))

    return result