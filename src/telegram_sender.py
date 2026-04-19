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
    'vaga_potencial':      '👀 Vaga potencial',
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

MODALIDADE_LABEL = {
    'remoto':     '🌐 Remoto',
    'hibrido':    '🔀 Híbrido',
    'presencial': '🏙️ Presencial',
}


def _info_linha(modalidade, local, salario):
    partes = []
    if modalidade and modalidade != 'nao_informado':
        partes.append(MODALIDADE_LABEL.get(modalidade, modalidade.capitalize()))
    if local:
        partes.append(f"📍 {local}")
    if salario:
        partes.append(f"💵 {salario}")
    return ' · '.join(partes)


def _formatar_vaga_processo(email: dict) -> str:
    """Formata vaga onde o candidato já está em contato/processo."""
    a       = email.get('analise', {})
    status  = a.get('status', 'outro')
    label   = STATUS_LABEL.get(status, '📩')
    cargo   = a.get('cargo') or email['subject'][:50]
    empresa = a.get('empresa')
    seniori = SENIORIDADE_LABEL.get(a.get('senioridade', ''), '')
    techs   = a.get('techs_match', [])
    resumo  = a.get('resumo', email.get('snippet', '')[:120])

    linhas = [label]
    linhas.append(f"*{cargo}*" + (f" — {seniori}" if seniori else ""))
    if empresa:
        linhas.append(f"🏢 {empresa}")
    info = _info_linha(a.get('modalidade'), a.get('local'), a.get('salario'))
    if info:
        linhas.append(info)
    if techs:
        linhas.append(f"🛠️ {', '.join(techs[:5])}")
    if resumo:
        linhas.append(f"_{resumo}_")
    return '\n'.join(linhas)


def _formatar_vaga_potencial(vaga: dict, idx: int) -> str:
    """Formata uma vaga potencial individual extraída de um digest/newsletter."""
    cargo   = vaga.get('cargo', 'Cargo não informado')
    empresa = vaga.get('empresa')
    seniori = SENIORIDADE_LABEL.get(vaga.get('senioridade', ''), '')
    techs   = vaga.get('techs_match', [])
    link    = vaga.get('link')

    linha1 = f"*{idx}. {cargo}*" + (f" — {seniori}" if seniori else "")
    linhas = [linha1]
    if empresa:
        linhas.append(f"   🏢 {empresa}")
    info = _info_linha(vaga.get('modalidade'), vaga.get('local'), vaga.get('salario'))
    if info:
        linhas.append(f"   {info}")
    if techs:
        linhas.append(f"   🛠️ {', '.join(techs[:4])}")
    if link:
        linhas.append(f"   🔗 [Candidatar-se]({link})")
    return '\n'.join(linhas)


def _formatar_outros(emails: list, categoria: str) -> str:
    icon = ICONS.get(categoria, '📌')
    msg  = f"{icon} *{categoria.capitalize()}* ({len(emails)})\n"
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

    vagas = classified.get('vagas', [])

    urgentes    = [v for v in vagas if v.get('analise', {}).get('status') in
                   ('entrevista_agendada', 'avanco_etapa', 'proposta')]
    em_processo = [v for v in vagas if v.get('analise', {}).get('relevante_para_perfil')
                   and v.get('analise', {}).get('status') == 'nova_vaga']
    potenciais_emails = [v for v in vagas if v.get('analise', {}).get('status') == 'vaga_potencial']
    outros_vagas = [v for v in vagas if v not in urgentes and v not in em_processo
                    and v not in potenciais_emails]
    outros_cats  = {k: v for k, v in classified.items() if k != 'vagas' and v}

    # Coleta todas as vagas potenciais relevantes de todos os emails
    todas_potenciais = []
    for email in potenciais_emails:
        for vaga in email.get('analise', {}).get('vagas_potenciais', []):
            if vaga.get('relevante'):
                todas_potenciais.append(vaga)

    total    = sum(len(v) for v in classified.values())
    date     = datetime.now().strftime('%d/%m/%Y')
    n_vagas  = len(vagas)
    n_pot    = len(todas_potenciais)

    # ── Mensagem 1: cabeçalho + urgentes + em processo ──
    msg = f"📬 *Digest de Emails — {date}*\n"
    msg += f"_{total} emails · {n_vagas} vagas · {n_pot} vagas para se inscrever_\n"

    if urgentes:
        msg += "\n━━ 🚨 *AÇÃO NECESSÁRIA* ━━\n\n"
        for email in urgentes:
            msg += _formatar_vaga_processo(email) + "\n\n"

    if em_processo:
        msg += "\n━━ 💼 *Vagas do seu perfil* ━━\n\n"
        for email in em_processo:
            msg += _formatar_vaga_processo(email) + "\n\n"

    if urgentes or em_processo:
        _send(token, chat_id, msg)
        msg = ""

    # ── Mensagem 2: vagas potenciais para se inscrever ──
    if todas_potenciais:
        msg += "\n━━ 👀 *Vagas para você se inscrever* ━━\n"
        msg += f"_Encontradas em {len(potenciais_emails)} email(s) de vagas_\n\n"
        for i, vaga in enumerate(todas_potenciais[:10], 1):
            msg += _formatar_vaga_potencial(vaga, i) + "\n\n"
        if len(todas_potenciais) > 10:
            msg += f"_...e mais {len(todas_potenciais) - 10} vagas potenciais_\n"

    # ── Outras vagas (fora do perfil) ──
    if outros_vagas:
        relevantes_outros = [v for v in outros_vagas
                             if v.get('analise', {}).get('relevante_para_perfil')]
        irrelevantes = [v for v in outros_vagas
                        if not v.get('analise', {}).get('relevante_para_perfil')]
        if irrelevantes:
            msg += f"\n📭 *Outras vagas* ({len(irrelevantes)}) — fora do seu perfil\n"
            for e in irrelevantes[:3]:
                a = e.get('analise', {})
                cargo   = a.get('cargo') or e['subject'][:45]
                empresa = a.get('empresa', '')
                msg += f"  • {cargo}" + (f" @ {empresa}" if empresa else "") + "\n"
            if len(irrelevantes) > 3:
                msg += f"  _...e mais {len(irrelevantes) - 3}_\n"

    if msg.strip():
        _send(token, chat_id, msg)

    # ── Mensagem 3: outros emails ──
    if outros_cats:
        msg3 = ""
        for cat, emails in outros_cats.items():
            msg3 += _formatar_outros(emails, cat) + "\n"
        _send(token, chat_id, msg3)


def _send(token: str, chat_id: str, text: str):
    if not text.strip():
        return
    if len(text) <= 4096:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        )
    else:
        chunks, current = [], ""
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