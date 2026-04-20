# Como o Email Organizer Funciona 🔄

Documentação técnica detalhada do fluxo e arquitetura do projeto.

## 📊 Fluxo Geral

```
┌─────────────────┐
│  Gmail (API)    │
└────────┬────────┘
         │ get_emails_since_yesterday()
         ↓
┌─────────────────────────────┐
│  gmail_reader.py            │
│  - Conecta via OAuth2       │
│  - Filtra últimas 24h       │
│  - Extrai headers e body    │
└────────┬────────────────────┘
         │ emails[] (lista)
         ↓
┌─────────────────────────────┐
│  main.py                    │
│  - Carrega cache (7 dias)   │
│  - Remove duplicatas        │
│  - Classifica novos emails  │
│  - Atualiza cache           │
└────────┬────────────────────┘
         │ emails_novos[] (dedupados)
         ↓
┌─────────────────────────────┐
│  classifier.py              │
│  - Chama Groq (IA)          │
│  - Extrai categoria         │
│  - Analisa relevância       │
│  - Estrutura dados          │
└────────┬────────────────────┘
         │ classified[] (estruturado)
         ↓
┌─────────────────────────────┐
│  telegram_sender.py         │
│  - Formata markdown         │
│  - Agrupa por categoria     │
│  - Envia ao Telegram        │
└────────┬────────────────────┘
         │
         ↓
    📱 Seu Telegram
```

---

## 🔑 Componentes Principais

### 1. **gmail_reader.py** - Lê emails do Gmail

#### Função principal
```python
def get_service() → googleapiclient.discovery.Resource
```

**O que faz:**
1. Lê a variável de ambiente `GMAIL_TOKEN` (JSON com credenciais)
2. Constrói objeto `Credentials` a partir do token
3. Retorna serviço autenticado do Gmail

#### Função principal
```python
def get_emails_since_yesterday() → list[dict]
```

**O que faz:**
1. Busca emails das últimas 24h: `after:YYYY/MM/DD`
2. Filtra apenas não-lidos: `is:unread`
3. Limita a 50 emails máximo
4. Para cada email, extrai:
   - `subject` - Assunto
   - `sender` - Remetente (From header)
   - `snippet` - Preview do Gmail
   - `body` - Corpo decodificado (primeiros 500 chars)

**Retorno exemplo:**
```python
[
  {
    'subject': 'Nova vaga: Analista de Dados',
    'sender': 'recrutador@empresa.com',
    'snippet': 'Estamos buscando um analista...',
    'body': 'Detalhes da vaga...'
  },
  ...
]
```

---

### 2. **main.py** - Orquestrador

#### Fluxo:

1. **Lê emails**
   ```python
   emails = get_emails_since_yesterday()  # Do Gmail
   ```

2. **Carrega cache** (últimos 7 dias)
   ```python
   cache = load_cache()  # Arquivo JSON local
   ```
   Cache: `{hash_md5: {'date': ISO8601}, ...}`

3. **Remove duplicatas**
   ```python
   for email in emails:
       email_hash = get_email_hash(email)
       if email_hash not in cache:
           emails_novos.append(email)
   ```
   Hash gerado por: `MD5(subject + sender + snippet)`

4. **Se há novos emails:**
   - Classifica com IA
   - Envia para Telegram
   - Atualiza cache

5. **Se nenhum novo:**
   - Imprime aviso
   - Aborta (não gasta API calls)

#### Variáveis importantes:
- `CACHE_FILE = 'processed_emails.json'` - Caminho do cache local

---

### 3. **classifier.py** - Análise com IA (Groq)

#### Etapa 1: Detectar Categoria

**Palavras-chave pré-definidas:**
```python
CATEGORIES = {
    "vagas": ["vaga", "emprego", "hiring", "linkedin", ...],
    "treinamento": ["curso", "certificação", "udemy", ...],
    "workshops": ["webinar", "evento", "hackathon", ...],
    "newsletters": ["newsletter", "digest", "unsubscribe", ...],
    "financeiro": ["fatura", "pagamento", "boleto", ...],
    "outros": []
}
```

**Como funciona:**
1. Cria regex para cada categoria (case-insensitive)
2. Testa subject + body contra cada padrão
3. Encontra categoria com mais matches
4. Se nenhum match → "outros"

#### Etapa 2: Chamar Groq (IA)

Para emails potencialmente relevantes (categoria != "outros"), chama Groq com prompt:

```
Você é um especialista em recrutamento tech.
Analise este email e retorne JSON com:
{
  "categoria": "vagas|treinamento|workshops|newsletters|financeiro|outros",
  "status": "nova_vaga|entrevista_agendada|proposta|...",
  "relevancia": 0-100,
  "cargo": "cargo extraído ou null",
  "empresa": "empresa extraída ou null",
  "senioridade": "junior|pleno|senior|nao_informado",
  "techs_match": ["tech1", "tech2"],
  "resumo": "2-3 linhas com info relevante",
  "link": "URL para candidatura ou null"
}
```

**Perfil injetado no prompt:**
```
Cargos alvo: Analista de Dados, Engenheiro de Dados, Data Analyst, etc
Stack: Python, PySpark, SQL, Power BI, Databricks, etc
Senioridade: Junior, Pleno
```

#### Função `classify_all(emails)`

**Retorna:**
```python
{
  "vagas": [
    {
      'subject': '...',
      'sender': '...',
      'analise': {
        'status': 'nova_vaga',
        'cargo': 'Analista de Dados',
        'empresa': 'Tech Corp',
        'techs_match': ['Python', 'SQL'],
        'resumo': 'Vaga remota...',
        ...
      }
    },
    ...
  ],
  "treinamento": [...],
  "newsletters": [...],
  "outros": [...]
}
```

---

### 4. **telegram_sender.py** - Envia para Telegram

#### Função `send_digest(classified)`

**O que faz:**
1. Agrupa emails por categoria
2. Formata cada um com markdown e emojis
3. Monta mensagem única com todos os grupos
4. Envia via API Telegram

#### Exemplo de formatação:

**Para vagas:**
```
🏆 PROPOSTA RECEBIDA
*Analista de Dados* — Pleno
🏢 Tech Corp
🌐 Remoto · 📍 São Paulo · 💵 R$ 8-10k
🛠️ Python, SQL, Power BI
_Empresa busca analista sênior com 5+ anos..._
🔗 [Candidatar-se](https://careers.com/job/123)
```

**Para newsletters/outros:**
```
📰 Newsletter
De: news@techmail.com
_Confira as últimas tendências em IA..._
```

#### Estrutura da mensagem final:

```
📧 DIGEST DIÁRIO - 20 de Abril

💼 VAGAS (3 novas)
─────────────────
[Email 1 formatado]

[Email 2 formatado]

📚 TREINAMENTO (1 novo)
─────────────────
[Email formatado]

[... outros grupos]

─────────────────
Processados em: 2026-04-20 14:35:22
```

---

## 🔐 Fluxo de Autenticação

### Google OAuth2 (Gmail)

1. **Setup inicial** (uma única vez):
   ```bash
   python auth_interactive.py
   ```
   Retorna JSON:
   ```json
   {
     "token": "ya29.a0AfH6...",
     "refresh_token": "1//0gXX...",
     "token_uri": "https://oauth2.googleapis.com/token",
     "client_id": "123456789-abc.apps.googleusercontent.com",
     "client_secret": "GOCSPX-abc123...",
     "scopes": ["https://www.googleapis.com/auth/gmail.readonly"]
   }
   ```

2. **Runtime**:
   - Lê `GMAIL_TOKEN` (env ou arquivo)
   - Usa `refresh_token` para renovar `token` automaticamente
   - Faz requisições ao Gmail com token válido

### Groq API

- Variável: `GROQ_API_KEY`
- Modelo: `GROQ_MODEL` (padrão: `llama-3.1-8b-instant`)
- Sem autenticação complexa (apenas chave na header)

### Telegram

- Variáveis: `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID`
- Envia mensagens via `telegram-bot` library
- Chat ID é seu ID privado (não público)

---

## 📝 Cache e Duplicatas

### Como funciona:

**Arquivo:** `processed_emails.json`

**Formato:**
```json
{
  "a3c5e7f9b1d2e4f6g8h0i2j4k6l8m0n2": {
    "date": "2026-04-20T14:35:22.123456"
  },
  "b4d6e8g0a2c4e6f8h0j2l4m6n8o0p2q4": {
    "date": "2026-04-19T10:15:30.654321"
  }
}
```

### Geração do Hash:

```python
email_hash = MD5(subject + sender + snippet)
```

**Por que funciona:**
- Mesmo email reprocessado terá subject, sender e snippet idênticos
- Hash consistente = detecção de duplicata
- Email genuinamente novo terá hash diferente

### Limpeza automática:

A cada execução, remove entradas com mais de 7 dias:
```python
cutoff = (datetime.now() - timedelta(days=7)).isoformat()
cache = {k: v for k, v in cache.items() if v.get('date', '') > cutoff}
```

**Por quê 7 dias?**
- Emails processados há >7 dias provavelmente já foram respondidos
- GitHub Actions roda a cada 6h = ~40 execuções/semana
- 7 dias = segurança contra re-processamento acidental

---

## 🤖 Exemplo Real de Processamento

### Email recebido:
```
Subject: Analista de Dados - Empresa XYZ [Remoto]
From: recrutador@xyztech.com
Body: Estamos buscando um Analista de Dados Junior com experiência 
em Python e SQL para nossa equipe em São Paulo...
```

### Passo 1 - gmail_reader.py:
```python
{
  'subject': 'Analista de Dados - Empresa XYZ [Remoto]',
  'sender': 'recrutador@xyztech.com',
  'snippet': 'Estamos buscando um Analista de Dados Junior...',
  'body': 'Estamos buscando um Analista de Dados Junior com experiência...'
}
```

### Passo 2 - main.py (cache check):
```python
hash = MD5('Analista de Dados - Empresa XYZ [Remoto]' + 
           'recrutador@xyztech.com' + 
           'Estamos buscando um Analista de Dados Junior...')
# hash = a3c5e7f9b1d2e4f6g8h0i2j4k6l8m0n2

if hash not in cache:  # ✅ Não estava processado
    emails_novos.append(email)
```

### Passo 3 - classifier.py (categoria):
```python
# Testa against keywords
matches = {
  "vagas": 6,      # vaga, Analista, Dados, Junior, remoto, candidata
  "treinamento": 0,
  "newsletters": 0,
  ...
}
categoria = "vagas"  # Maior score
```

### Passo 4 - classifier.py (IA/Groq):
```
Prompt enviado ao Groq:
"Você é um especialista em recrutamento tech...
Analise este email de: recrutador@xyztech.com
Subject: Analista de Dados...
Body: Estamos buscando...
Perfil alvo: Cargos=[Analista de Dados, Data Engineer], Stack=[Python, SQL...]"

Resposta do Groq (JSON):
{
  "categoria": "vagas",
  "status": "nova_vaga",
  "relevancia": 95,
  "cargo": "Analista de Dados Junior",
  "empresa": "Empresa XYZ",
  "senioridade": "junior",
  "techs_match": ["Python", "SQL"],
  "resumo": "Vaga remota para Analista de Dados Junior em São Paulo...",
  "link": null
}
```

### Passo 5 - telegram_sender.py:
```
Formata e envia ao Telegram:

💼 VAGAS (1 nova)
─────────────────
🆕 Nova vaga
*Analista de Dados Junior*
🏢 Empresa XYZ
🌐 Remoto · 📍 São Paulo
🛠️ Python, SQL
_Vaga remota para Analista de Dados Junior em São Paulo..._
```

### Passo 6 - main.py (update cache):
```python
cache['a3c5e7f9b1d2e4f6g8h0i2j4k6l8m0n2'] = {
  'date': '2026-04-20T14:35:22.123456'
}
# Salva em processed_emails.json
```

---

## ⚙️ Variáveis de Ambiente

| Variável | Tipo | Obrigatória | Exemplo |
|----------|------|-------------|---------|
| `GMAIL_TOKEN` | JSON string | ✅ | `{"token": "...", "client_id": "..."}` |
| `GMAIL_CLIENT_ID` | string | ❌ (se não em GMAIL_TOKEN) | `123456789-abc.apps.googleusercontent.com` |
| `GMAIL_CLIENT_SECRET` | string | ❌ (se não em GMAIL_TOKEN) | `GOCSPX-abc123...` |
| `GMAIL_REFRESH_TOKEN` | string | ❌ (se não em GMAIL_TOKEN) | `1//0gXX...` |
| `GROQ_API_KEY` | string | ✅ | `gsk_...` |
| `GROQ_MODEL` | string | ❌ | `llama-3.1-8b-instant` |
| `TELEGRAM_TOKEN` | string | ✅ | `123456:ABC-DEF...` |
| `TELEGRAM_CHAT_ID` | integer | ✅ | `987654321` |

---

## 🚀 Execução (Fluxo Completo)

### Local:
```bash
# 1. Ativa venv
.venv\Scripts\activate

# 2. Define variáveis (Windows)
$env:GMAIL_TOKEN = '{"token": "...", ...}'
$env:GROQ_API_KEY = 'gsk_...'
$env:TELEGRAM_TOKEN = '123456:ABC...'
$env:TELEGRAM_CHAT_ID = '987654321'

# 3. Executa
python src/main.py

# Output:
# Lendo emails...
# 5 emails encontrados.
# Processando 2 emails novos (ignorando 3 duplicatas)...
# Classificando...
# Enviando para o Telegram...
# Digest enviado com sucesso!
```

### GitHub Actions:
```yaml
# .github/workflows/daily_digest.yml
on:
  schedule:
    - cron: '0 */6 * * *'  # A cada 6 horas

jobs:
  digest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python src/main.py
        env:
          GMAIL_TOKEN: ${{ secrets.GMAIL_TOKEN }}
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
```

---

## 🐛 Troubleshooting

### Email não aparece no Telegram
1. Check: Email foi enviado nas últimas 24h?
2. Check: Email não-lido? (gmail_reader filtra `is:unread`)
3. Check: Não é duplicata? (verifica processed_emails.json)
4. Check: Passou na classificação? (categoria != "outros" ou relevância alta)

### Erro: "GMAIL_TOKEN inválido"
1. Regenere: `python auth_interactive.py`
2. Copie o JSON completo (com `refresh_token`)
3. Configure em GitHub Secrets

### Erro: "GROQ_API_KEY not found"
1. Acesse [console.groq.com](https://console.groq.com)
2. Gere nova API Key
3. Configure variável de ambiente

### Email processado 2x
1. Verificar `processed_emails.json`
2. Deletar arquivo para "resetar" (cuidado!)
3. Próxima execução vai reprocessar

---

## 📊 Performance

| Operação | Tempo | Notas |
|----------|-------|-------|
| Gmail API (50 emails) | ~2-3s | HTTP calls inclusos |
| Deduplicação (cache) | ~10ms | Hash MD5 local |
| Classificação (Groq) | ~3-5s/email | Dependente do tamanho do email |
| Formatação (Telegram) | ~100ms | Markdown local |
| Envio Telegram | ~500ms | HTTP call |

**Total esperado:** ~20-30s para 5 emails novos

---

## 🔄 Próximas Melhorias Possíveis

1. **Multi-conta Gmail** - Suportar múltiplas contas no mesmo digest
2. **Filtros customizáveis** - Adicionar regex patterns por usuário
3. **Dashboard web** - Interface para visualizar emails processados
4. **Notificações Push** - Mobile notifications em vez de Telegram
5. **Histórico de emails** - Database para rastrear processamento
6. **ML training** - Melhorar classificação com feedback do usuário
