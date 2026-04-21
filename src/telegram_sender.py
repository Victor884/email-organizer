"""
telegram_sender.py
─────────────────────────────────────────────────────────────────────────────
Responsabilidade única: formatar e enviar o digest ao Telegram.

Hierarquia das mensagens (ordem de envio):
  Msg 1 → 🚨 Ação Urgente  (proposta / entrevista / avanço) — se houver
  Msg 2 → ✅ Direct Match  (score ≥ threshold, vagas do perfil)
  Msg 3 → 📡 Radar         (score < threshold, mas relacionadas)
  Msg 4 → 📖 Conteúdo & Networking (treinamento, workshops, newsletters, outros)

Indicadores visuais de match:
  🟢 perfeito (≥80)  🔵 bom (≥60)  🟡 parcial (≥40)  🔴 fraco (<40)
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import os
from datetime import datetime

import requests

from classifier import (
    EmailAnalise, VagaPotencial,
    MATCH_THRESHOLD_PCT, STATUS_PRIORIDADE,
)

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTES DE EXIBIÇÃO
# ─────────────────────────────────────────────────────────────────────────────

_MATCH_EMOJI: dict[str, str] = {
    "perfeito": "🟢",
    "bom":      "🔵",
    "parcial":  "🟡",
    "fraco":    "🔴",
}

_STATUS_HEADER: dict[str, str] = {
    "proposta":            "🏆 PROPOSTA RECEBIDA",
    "entrevista_agendada": "📅 ENTREVISTA AGENDADA",
    "avanco_etapa":        "🚀 AVANÇOU DE ETAPA",
    "nova_vaga":           "💼 Nova vaga direta",
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
    "junior": "Jr",
    "pleno":  "Pl",
    "senior": "Sr",
}

_STATUS_URGENTES = {"proposta", "entrevista_agendada", "avanco_etapa"}

_CAT_ICON: dict[str, str] = {
    "treinamento": "🎓",
    "workshops":   "🛠️",
    "newsletters": "📰",
    "financeiro":  "💰",
    "outros":      "📁",
}


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _chip_techs(techs: list[str], max_n: int = 5) -> str:
    """Renderiza techs como chips inline: `Python` `SQL` `Power BI`"""
    return " ".join(f"`{t}`" for t in techs[:max_n])


def _linha_meta(modalidade: str, local: str | None, salario: str | None) -> str:
    """Linha compacta de metadados: 🌐 Remoto · 📍 BSB · 💵 R$8k"""
    partes = []
    if modalidade and modalidade != "nao_informado":
        partes.append(_MODALIDADE.get(modalidade, modalidade.capitalize()))
    if local:
        partes.append(f"📍 {local}")
    if salario:
        partes.append(f"💵 {salario}")
    return " · ".join(partes)


# ─────────────────────────────────────────────────────────────────────────────
#  FORMATADORES DE BLOCO
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_urgente(email: dict) -> str:
    """
    Bloco detalhado para ação imediata (proposta/entrevista/avanço).

    ┌─────────────────────────────────────────┐
    │ 📅 ENTREVISTA AGENDADA                  │
    │ *Data Engineer* — Pl  🔵 85%            │
    │ 🏢 Empresa XYZ                          │
    │ 🌐 Remoto · 📍 SP · 💵 R$8k-12k        │
    │ `Python` `Spark` `Airflow`              │
    │ _Recrutadora convida para entrevista..._ │
    │ 🔗 Candidatar-se                        │
    └─────────────────────────────────────────┘
    """
    a: EmailAnalise = email["analise"]
    senior  = _SENIORIDADE.get(a.senioridade, "")
    badge   = _MATCH_EMOJI.get(a.match_label, "")
    cargo   = a.cargo or email.get("subject", "")[:50] or "Cargo não informado"
    meta    = _linha_meta(a.modalidade, a.local, a.salario)

    linhas = [
        _STATUS_HEADER.get(a.status, "📩"),
        f"*{cargo}*" + (f" — {senior}" if senior else "") + f"  {badge} {a.match_score}%",
    ]
    if a.empresa:     linhas.append(f"🏢 {a.empresa}")
    if meta:          linhas.append(meta)
    if a.techs_match: linhas.append(_chip_techs(a.techs_match))
    if a.resumo:      linhas.append(f"_{a.resumo}_")
    if a.link_candidatura:
        linhas.append(f"🔗 [Candidatar-se]({a.link_candidatura})")

    return "\n".join(linhas)


def _fmt_direct_match(email: dict) -> str:
    """
    Item compacto de "Direct Match" — uma linha principal + techs + link.

    ✅ *Analista de Dados* — Pl  🟢 90%
       🏢 Empresa · 🌐 Remoto · 💵 R$6k
       `SQL` `Power BI` `Python`
       🔗 Candidatar-se
    """
    a: EmailAnalise = email["analise"]
    senior = _SENIORIDADE.get(a.senioridade, "")
    badge  = _MATCH_EMOJI.get(a.match_label, "")
    cargo  = a.cargo or email.get("subject", "")[:45] or "Cargo não informado"
    meta   = _linha_meta(a.modalidade, a.local, a.salario)

    # Linha 1 — cargo + score
    linha1 = f"✅ *{cargo}*" + (f" — {senior}" if senior else "") + f"  {badge} {a.match_score}%"

    # Linha 2 — empresa + meta
    partes_meta = []
    if a.empresa: partes_meta.append(f"🏢 {a.empresa}")
    if meta:      partes_meta.append(meta)
    linha2 = "   " + "  ·  ".join(partes_meta) if partes_meta else ""

    # Linha 3 — techs
    linha3 = "   " + _chip_techs(a.techs_match) if a.techs_match else ""

    # Linha 4 — link
    linha4 = f"   🔗 [Candidatar-se]({a.link_candidatura})" if a.link_candidatura else ""

    return "\n".join(l for l in [linha1, linha2, linha3, linha4] if l)


def _fmt_radar_item(email: dict) -> str:
    """
    Item de uma linha para o bloco Radar (vagas relacionadas, fora do perfil principal).

    ⚠️ Analista de Dados @ Randstad | SP | `SQL`
    """
    a: EmailAnalise = email["analise"]
    badge   = _MATCH_EMOJI.get(a.match_label, "🔴")
    cargo   = a.cargo or email.get("subject", "")[:40] or "Cargo não informado"
    empresa = f" @ {a.empresa}" if a.empresa else ""
    local   = f" | {a.local}" if a.local else ""
    techs   = (" | " + _chip_techs(a.techs_match, 3)) if a.techs_match else ""

    return f"{badge} {cargo}{empresa}{local}{techs}"


def _fmt_vaga_potencial_item(vaga: VagaPotencial, idx: int) -> str:
    """
    Item de vaga potencial extraída de digest/newsletter.

    🟢 *1. Analista de BI* — Pl
       🏢 Empresa · 🌐 Remoto · `Power BI` `SQL`
       🔗 Candidatar-se
    """
    badge  = _MATCH_EMOJI.get(vaga.match_label, "")
    senior = _SENIORIDADE.get(vaga.senioridade, "")
    cargo  = vaga.cargo or "Cargo não informado"
    meta   = _linha_meta(vaga.modalidade, vaga.local, vaga.salario)

    linha1 = f"{badge} *{idx}. {cargo}*" + (f" — {senior}" if senior else "") + f"  {vaga.match_score}%"

    partes_meta = []
    if vaga.empresa: partes_meta.append(f"🏢 {vaga.empresa}")
    if meta:         partes_meta.append(meta)
    linha2 = "   " + "  ·  ".join(partes_meta) if partes_meta else ""

    linha3 = "   " + _chip_techs(vaga.techs_match) if vaga.techs_match else ""
    linha4 = f"   🔗 [Candidatar-se]({vaga.link_candidatura})" if vaga.link_candidatura else ""

    return "\n".join(l for l in [linha1, linha2, linha3, linha4] if l)


def _fmt_conteudo(classified: dict) -> str:
    """
    Bloco compacto para e-mails que não são vagas:
    treinamento, workshops, newsletters, financeiro, outros.
    """
    ordem = ["treinamento", "workshops", "newsletters", "financeiro", "outros"]
    partes: list[str] = []

    for cat in ordem:
        emails = classified.get(cat, [])
        if not emails:
            continue
        icon  = _CAT_ICON.get(cat, "📌")
        label = cat.capitalize()
        linhas = [f"{icon} *{label}* ({len(emails)})"]
        for e in emails[:4]:
            remetente = e.get("sender", "").split("<")[0].strip()[:25]
            assunto   = e.get("subject", "(sem assunto)")[:50]
            linhas.append(f"  • {assunto}" + (f"  _({remetente})_" if remetente else ""))
        if len(emails) > 4:
            linhas.append(f"  _... e mais {len(emails) - 4}_")
        partes.append("\n".join(linhas))

    return "\n\n".join(partes)


# ─────────────────────────────────────────────────────────────────────────────
#  MONTAGEM DAS MENSAGENS
# ─────────────────────────────────────────────────────────────────────────────

def _build_messages(classified: dict) -> list[str]:
    """
    Retorna lista de strings prontas para envio no Telegram.
    Cada string respeita os 4096 chars do Telegram.
    """
    vagas: list[dict] = classified.get("vagas", [])
    msgs: list[str] = []

    # Segmenta vagas
    urgentes       = [v for v in vagas if v["analise"].status in _STATUS_URGENTES]
    direct_match   = [v for v in vagas
                      if v["analise"].match_score >= MATCH_THRESHOLD_PCT
                      and v["analise"].status not in _STATUS_URGENTES
                      and v["analise"].status != "vaga_potencial"]
    pot_emails     = [v for v in vagas if v["analise"].status == "vaga_potencial"]
    radar          = [v for v in vagas
                      if v["analise"].match_score < MATCH_THRESHOLD_PCT
                      and v["analise"].status not in _STATUS_URGENTES
                      and v["analise"].status != "vaga_potencial"]

    # Vagas potenciais relevantes extraídas de todos os digests
    pot_relevantes: list[VagaPotencial] = sorted(
        [vp for e in pot_emails
             for vp in e["analise"].vagas_potenciais
             if vp.match_score >= MATCH_THRESHOLD_PCT],
        key=lambda v: -v.match_score,
    )

    total   = sum(len(lst) for lst in classified.values())
    n_vagas = len(vagas)
    n_pot   = len(pot_relevantes)
    data    = datetime.now().strftime("%d/%m %H:%M")

    # ── MSG 1: cabeçalho + urgente ────────────────────────────────────────────
    cab = (
        f"📬 *Digest de E-mails — {data}*\n"
        f"_{total} emails · {n_vagas} vagas · {n_pot} para se inscrever_\n\n"
        f"🟢 ≥80%  🔵 ≥60%  🟡 ≥40%  🔴 <40%"
    )
    if urgentes:
        cab += "\n\n━━━━━━━━━━━━━━━━━━━━\n🚨 *AÇÃO NECESSÁRIA*\n━━━━━━━━━━━━━━━━━━━━\n"
        for e in urgentes:
            cab += "\n" + _fmt_urgente(e) + "\n"
    msgs.append(cab.strip())

    # ── MSG 2: Direct Match ───────────────────────────────────────────────────
    if direct_match or pot_relevantes:
        bloco = "━━━━━━━━━━━━━━━━━━━━\n✅ *DIRECT MATCH*\n━━━━━━━━━━━━━━━━━━━━\n"

        if direct_match:
            for e in direct_match:
                bloco += "\n" + _fmt_direct_match(e) + "\n"

        if pot_relevantes:
            bloco += f"\n📌 *Vagas para se inscrever* — extraídas de {len(pot_emails)} digest(s)\n"
            for i, vp in enumerate(pot_relevantes[:10], 1):
                bloco += "\n" + _fmt_vaga_potencial_item(vp, i) + "\n"
            if len(pot_relevantes) > 10:
                bloco += f"\n_... e mais {len(pot_relevantes) - 10} vagas_"

        msgs.append(bloco.strip())

    # ── MSG 3: Radar ──────────────────────────────────────────────────────────
    if radar:
        bloco = f"━━━━━━━━━━━━━━━━━━━━\n📡 *RADAR* — relacionadas, fora do perfil principal ({len(radar)})\n━━━━━━━━━━━━━━━━━━━━\n"
        for e in radar[:12]:
            bloco += _fmt_radar_item(e) + "\n"
        if len(radar) > 12:
            bloco += f"_... e mais {len(radar) - 12}_"
        msgs.append(bloco.strip())

    # ── MSG 4: Conteúdo & Networking ──────────────────────────────────────────
    conteudo = _fmt_conteudo(classified)
    if conteudo:
        msgs.append(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📖 *CONTEÚDO & NETWORKING*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            + conteudo
        )

    return msgs


# ─────────────────────────────────────────────────────────────────────────────
#  ENVIO
# ─────────────────────────────────────────────────────────────────────────────

def _send(token: str, chat_id: str, text: str) -> None:
    """Envia texto, quebrando em chunks ≤4096 chars se necessário."""
    if not text.strip():
        return

    if len(text) <= 4096:
        chunks = [text]
    else:
        chunks, current = [], ""
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
            json={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"},
            timeout=10,
        )
        if not resp.ok:
            print(f"[telegram] Erro {resp.status_code}: {resp.text[:200]}")


def send_digest(classified: dict) -> None:
    """Ponto de entrada: monta e envia todas as mensagens do digest."""
    token   = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    for msg in _build_messages(classified):
        _send(token, chat_id, msg)