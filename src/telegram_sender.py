import os
import requests
from datetime import datetime

ICONS = {
    'vagas':       '💼',
    'treinamento': '📚',
    'workshops':   '🎯',
    'newsletters': '📰',
    'financeiro':  '💰',
    'outros':      '📌'
}

STATUS_LABEL = {
    'entrevista_agendada': '🔥 ENTREVISTA AGENDADA',
    'avanco_etapa':        '⬆️ AVANÇOU DE ETAPA',
    'proposta':            '🎉 PROPOSTA RECEBIDA',
    'nova_vaga':           '🆕 Nova vaga',
    'aguardando':          '⏳ Aguardando retorno',
    'reprovado':           '❌ Reprovado',
    'outro':               '📩 Email de recrutamento',
}

SENIORIDADE_LABEL = {
    'pleno':         'Pleno',
    'senior':        'Sênior',
    'junior':        'Júnior',
    'nao_informado': '',
}


def _formatar_vaga(email: dict, idx: int) -> str:
    a = email.get('analise', {})
    status  = a.get('status', 'outro')
    label   = STATUS_LABEL.get(status, '📩 Email de recrutamento')
    cargo   = a.get('cargo') or email['subject'][:50]
    empresa = a.get('empresa')
    seniori = SENIORIDADE_LABEL.get(a.get('senioridade', ''), '')
    modal   = a.get('modalidade', 'nao_informado')
    local   = a.get('local')
    salario = a.get('salario')
    techs   = a.get('techs_match', [])
    resumo  = a.get('resumo', email.get('snippet', '')[:120])
    relevante = a.get('relevante_para_perfil', False)

    linhas = [f"{label}"]
    linhas.append(f"*{cargo}*" + (f" — {seniori}" if seniori else ""))

    if empresa:
        linhas.append(f"🏢 {empresa}")

    info_linha = []
    if modal not in ('nao_informado', None):
        info_linha.append({'remoto': '🌐 Remoto', 'hibrido': '🔀 Híbrido', 'presencial': '🏙️ Presencial'}.get(modal, modal.capitalize()))
    if local:
        info_linha.append(f"📍 {local}")
    if salario:
        info_linha.append(f"💵 {salario}")
    if info_linha:
        linhas.append(' · '.join(info_linha))

    if techs:
        linhas.append(f"🛠️ {', '.join(techs[:6])}")

    if resumo:
        linhas.append(f"_{resumo}_")

    if not relevante:
        motivo = a.get('motivo_irrelevante', '')
        if motivo:
            linhas.append(f"⚠️ _{motivo}_")

    return '\n'.join(linhas)


def _formatar_outros(emails: list, categoria: str) -> str:
    icon = ICONS.get(categoria, '📌')
    nome = categoria.capitalize()
    msg  = f"{icon} *{nome}* ({len(emails)})\n"
    for e in emails[:5]:
        sender  = e['sender'].split('<')[0].strip()[:30]
        subject = e['subject'][:55]
        msg += f"  • {subject}\n    _{sender}_\n"
    if len(emails) > 5:
        msg += f"  _...e mais {len(emails) - 5}_\n"
    return msg


def send_digest(classified: dict):
    token   = os.environ['TELEGRAM_TOKEN']
    chat_id = os.environ['TELEGRAM_CHAT_ID']

    vagas      = classified.get('vagas', [])
    relevantes = [v for v in vagas if v.get('analise', {}).get('relevante_para_perfil')]
    urgentes   = [v for v in vagas if v.get('analise', {}).get('status') in
                  ('entrevista_agendada', 'avanco_etapa', 'proposta')]
    outros_cats = {k: v for k, v in classified.items() if k != 'vagas' and v}

    total = sum(len(v) for v in classified.values())
    date  = datetime.now().strftime('%d/%m/%Y')

    # ── Mensagem 1: cabeçalho + vagas urgentes/relevantes ──
    msg = f"📬 *Digest de Emails — {date}*\n"
    msg += f"_{total} emails · {len(vagas)} vagas ({len(relevantes)} para seu perfil)_\n"

    if urgentes:
        msg += "\n━━ 🚨 *AÇÃO NECESSÁRIA* ━━\n\n"
        for email in urgentes:
            msg += _formatar_vaga(email, 0) + "\n\n"

    if relevantes:
        msg += "\n━━ 💼 *Vagas para seu perfil* ━━\n\n"
        for email in relevantes:
            if email not in urgentes:
                msg += _formatar_vaga(email, 0) + "\n\n"

    irrelevantes = [v for v in vagas if not v.get('analise', {}).get('relevante_para_perfil')]
    if irrelevantes:
        msg += f"\n📭 *Outras vagas* ({len(irrelevantes)}) — fora do seu perfil\n"
        for e in irrelevantes[:3]:
            a = e.get('analise', {})
            cargo   = a.get('cargo') or e['subject'][:45]
            empresa = a.get('empresa', '')
            msg += f"  • {cargo}" + (f" @ {empresa}" if empresa else "") + "\n"
        if len(irrelevantes) > 3:
            msg += f"  _...e mais {len(irrelevantes) - 3}_\n"

    _send(token, chat_id, msg)

    # ── Mensagem 2: outros emails (apenas se houver) ──
    if outros_cats:
        msg2 = ""
        for cat, emails in outros_cats.items():
            msg2 += _formatar_outros(emails, cat) + "\n"
        _send(token, chat_id, msg2)


def _send(token: str, chat_id: str, text: str):
    """Envia mensagem com fallback se ultrapassar limite do Telegram (4096 chars)."""
    if len(text) <= 4096:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        )
    else:
        # Divide em blocos de 4000 chars sem quebrar no meio de uma linha
        chunks = []
        current = ""
        for line in text.split('\n'):
            if len(current) + len(line) + 1 > 4000:
                chunks.append(current)
                current = line
            else:
                current += ('\n' if current else '') + line
        if current:
            chunks.append(current)
        for chunk in chunks:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"}
            )