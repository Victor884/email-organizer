"""
telegram_sender.py
─────────────────────────────────────────────────────────────────────────────
Responsabilidade única: formatar o dict classificado e enviar ao Telegram.
Não faz chamadas ao Groq. Não conhece a lógica de classificação.

Hierarquia de mensagens enviadas:
  Msg 1 → Cabeçalho + Ação Urgente (proposta / entrevista / avanço de etapa)
  Msg 2 → Vagas diretas relevantes ao perfil
  Msg 3 → Vagas potenciais para se inscrever (newsletters de emprego)
  Msg 4 → Demais emails (treinamento, financeiro, etc.)
─────────────────────────────────────────────────────────────────────────────
"""

import os
from datetime import datetime

import requests

from classifier import EmailAnalise, VagaPotencial, STATUS_PRIORIDADE

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTES DE EXIBIÇÃO
# ─────────────────────────────────────────────────────────────────────────────

_STATUS_HEADER: dict[str, str] = {
    "proposta":            "🏆 PROPOSTA RECEBIDA",
    "entrevista_agendada": "📅 ENTREVISTA AGENDADA",
    "avanco_etapa":        "🚀 AVANÇOU DE ETAPA",
    "nova_vaga":           "💼 Nova vaga",
    "vaga_potencial":      "📋 Digest de vagas",
    "aguardando":          "⏳ Aguardando retorno",
    "reprovado":           "❌ Reprovado",
    "outro":               "📩 Email de recrutamento",
}

_MODALIDADE: dict[str, str] = {
    "remoto":     "🌐 Remoto",
    "hibrido":    "🔀 Híbrido",
    "presencial": "🏙️ Presencial",
}

_SENIORIDADE: dict[str, str] = {
    "junior": "Júnior",
    "pleno":  "Pleno",
    "senior": "Sênior",
}

_CAT_ICON: dict[str, str] = {
    "treinamento": "🎓",
    "workshops":   "🛠️",
    "newsletters": "📰",
    "financeiro":  "💰",
    "outros":      "📁",
}

# Status que exigem ação imediata do candidato
_STATUS_URGENTES = {"proposta", "entrevista_agendada", "avanco_etapa"}


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS DE FORMATAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

def _linha_info(analise_or_vaga: object) -> str:
    """Monta linha compacta: modalidade · local · salário."""
    modal   = getattr(analise_or_vaga, "modalidade", "nao_informado")
    local   = getattr(analise_or_vaga, "local", None)
    salario = getattr(analise_or_vaga, "salario", None)

    partes = []
    if modal and modal != "nao_informado":
        partes.append(_MODALIDADE.get(modal, modal.capitalize()))
    if local:
        partes.append(f"📍 {local}")
    if salario:
        partes.append(f"💵 {salario}")
    return " · ".join(partes)


def _fmt_vaga_direta(email: dict) -> str:
    """
    Bloco completo para uma vaga onde o candidato está em contato ou
    acaba de ser abordado.

    Exemplo de saída:
        📅 ENTREVISTA AGENDADA
        *Data Engineer* — Pleno
        🏢 Empresa XYZ
        🌐 Remoto · 📍 SP · 💵 R$8k-12k
        🛠️ Python, Airflow, Spark
        _Recrutadora da XYZ convida para entrevista técnica na sexta._
        🔗 Candidatar-se
    """
    a: EmailAnalise = email["analise"]

    cargo    = a.cargo or email.get("subject", "")[:50] or "Cargo não informado"
    senior   = _SENIORIDADE.get(a.senioridade, "")
    empresa  = a.empresa
    techs    = a.techs_match[:5]
    info     = _linha_info(a)
    header   = _STATUS_HEADER.get(a.status, "📩 Email de recrutamento")

    linhas = [header]
    linhas.append(f"*{cargo}*" + (f" — {senior}" if senior else ""))
    if empresa:
        linhas.append(f"🏢 {empresa}")
    if info:
        linhas.append(info)
    if techs:
        linhas.append(f"🛠️ {', '.join(techs)}")
    if a.resumo:
        linhas.append(f"_{a.resumo}_")
    if a.link:
        linhas.append(f"🔗 [Candidatar-se]({a.link})")

    return "\n".join(linhas)


def _fmt_vaga_potencial(vaga: VagaPotencial, idx: int) -> str:
    """
    Item numerado de uma lista de vagas potenciais extraídas de newsletters.

    Exemplo de saída:
        *1. Analista de BI* — Pleno
           🏢 Empresa ABC  |  🌐 Remoto  |  🛠️ Power BI, SQL
           🔗 Candidatar-se
    """
    cargo   = vaga.cargo or "Cargo não informado"
    senior  = _SENIORIDADE.get(vaga.senioridade, "")
    techs   = vaga.techs_match[:4]
    info    = _linha_info(vaga)

    linhas = [f"*{idx}. {cargo}*" + (f" — {senior}" if senior else "")]
    partes_linha2 = []
    if vaga.empresa:
        partes_linha2.append(f"🏢 {vaga.empresa}")
    if info:
        partes_linha2.append(info)
    if partes_linha2:
        linhas.append("   " + "  |  ".join(partes_linha2))
    if techs:
        linhas.append(f"   🛠️ {', '.join(techs)}")
    if vaga.link:
        linhas.append(f"   🔗 [Candidatar-se]({vaga.link})")

    return "\n".join(linhas)


def _fmt_categoria_compacta(emails: list[dict], categoria: str) -> str:
    """
    Bloco resumido para categorias não-vagas (treinamento, financeiro, etc.).
    Exibe até 5 emails; trunca o restante.
    """
    icon  = _CAT_ICON.get(categoria, "📌")
    label = categoria.capitalize()
    linhas = [f"{icon} *{label}* ({len(emails)})"]

    for e in emails[:5]:
        remetente = e.get("sender", "").split("<")[0].strip()[:28]
        assunto   = e.get("subject", "(sem assunto)")[:55]
        linhas.append(f"  • {assunto}")
        if remetente:
            linhas.append(f"    _{remetente}_")

    if len(emails) > 5:
        linhas.append(f"  _... e mais {len(emails) - 5}_")

    return "\n".join(linhas)


# ─────────────────────────────────────────────────────────────────────────────
#  MONTAGEM DAS MENSAGENS
# ─────────────────────────────────────────────────────────────────────────────

def _build_messages(classified: dict) -> list[str]:
    """
    Retorna lista de strings prontas para envio.
    Cada string respeita o limite de 4096 chars do Telegram.
    A ordem reflete a prioridade de ação do candidato.
    """
    vagas: list[dict] = classified.get("vagas", [])

    # Segmenta as vagas por urgência
    urgentes      = [v for v in vagas if v["analise"].status in _STATUS_URGENTES]
    novas_vagas   = [v for v in vagas
                     if v["analise"].relevante_para_perfil
                     and v["analise"].status == "nova_vaga"]
    pot_emails    = [v for v in vagas if v["analise"].status == "vaga_potencial"]
    outros_vagas  = [v for v in vagas
                     if v not in urgentes
                     and v not in novas_vagas
                     and v not in pot_emails]

    # Coleta vagas potenciais relevantes de todos os digests
    vagas_potenciais_relevantes: list[VagaPotencial] = [
        vp
        for email in pot_emails
        for vp in email["analise"].vagas_potenciais
        if vp.relevante
    ]

    total    = sum(len(v) for v in classified.values())
    n_vagas  = len(vagas)
    n_pot    = len(vagas_potenciais_relevantes)
    data     = datetime.now().strftime("%d/%m/%Y %H:%M")

    messages: list[str] = []

    # ── MSG 1: cabeçalho + ação urgente ──────────────────────────────────────
    bloco1 = (
        f"📬 *Digest — {data}*\n"
        f"_{total} emails · {n_vagas} vagas · {n_pot} para se inscrever_"
    )

    if urgentes:
        bloco1 += "\n\n━━ 🚨 *AÇÃO NECESSÁRIA* ━━\n"
        for email in urgentes:
            bloco1 += "\n" + _fmt_vaga_direta(email) + "\n"

    if bloco1.strip():
        messages.append(bloco1.strip())

    # ── MSG 2: vagas diretas relevantes ao perfil ─────────────────────────────
    if novas_vagas:
        bloco2 = "━━ 💼 *Vagas do seu perfil* ━━\n"
        for email in novas_vagas:
            bloco2 += "\n" + _fmt_vaga_direta(email) + "\n"
        messages.append(bloco2.strip())

    # ── MSG 3: vagas potenciais para se inscrever ─────────────────────────────
    if vagas_potenciais_relevantes:
        bloco3 = (
            f"━━ 👀 *Vagas para se inscrever* ━━\n"
            f"_Encontradas em {len(pot_emails)} email(s)_\n"
        )
        for i, vp in enumerate(vagas_potenciais_relevantes[:12], 1):
            bloco3 += "\n" + _fmt_vaga_potencial(vp, i) + "\n"
        if len(vagas_potenciais_relevantes) > 12:
            bloco3 += f"\n_... e mais {len(vagas_potenciais_relevantes) - 12} vagas_"
        messages.append(bloco3.strip())

    # ── MSG 4: outras vagas (fora do perfil) + demais categorias ─────────────
    bloco4_partes: list[str] = []

    if outros_vagas:
        linhas = [f"📭 *Outras vagas* ({len(outros_vagas)}) — fora do perfil"]
        for e in outros_vagas[:4]:
            a       = e["analise"]
            cargo   = a.cargo or e.get("subject", "")[:45]
            empresa = f" @ {a.empresa}" if a.empresa else ""
            linhas.append(f"  • {cargo}{empresa}")
        if len(outros_vagas) > 4:
            linhas.append(f"  _... e mais {len(outros_vagas) - 4}_")
        bloco4_partes.append("\n".join(linhas))

    ordem_cats = ["treinamento", "workshops", "financeiro", "newsletters", "outros"]
    for cat in ordem_cats:
        emails_cat = classified.get(cat, [])
        if emails_cat:
            bloco4_partes.append(_fmt_categoria_compacta(emails_cat, cat))

    if bloco4_partes:
        messages.append("\n\n".join(bloco4_partes))

    return messages


# ─────────────────────────────────────────────────────────────────────────────
#  ENVIO
# ─────────────────────────────────────────────────────────────────────────────

def _send(token: str, chat_id: str, text: str) -> None:
    """Envia uma mensagem, quebrando em chunks se ultrapassar 4096 chars."""
    if not text.strip():
        return

    chunks: list[str] = []
    if len(text) <= 4096:
        chunks = [text]
    else:
        current = ""
        for line in text.split("\n"):
            if len(current) + len(line) + 1 > 4000:
                chunks.append(current)
                current = line
            else:
                current += ("\n" if current else "") + line
        if current:
            chunks.append(current)

    for chunk in chunks:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id":    chat_id,
                "text":       chunk,
                "parse_mode": "Markdown",
            },
            timeout=10,
        )
        if not resp.ok:
            print(f"[telegram] Erro ao enviar: {resp.status_code} {resp.text[:200]}")


def send_digest(classified: dict) -> None:
    """Ponto de entrada: monta e envia todas as mensagens do digest."""
    token   = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    for msg in _build_messages(classified):
        _send(token, chat_id, msg)