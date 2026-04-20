# Email Organizer 📧

Um sistema inteligente de classificação e organização de emails que automatiza a análise de mensagens recebidas e envia um resumo personalizado via Telegram.

## 🎯 O que faz

- **Lê emails** do Gmail com filtro automático (últimas 24h, não lidos)
- **Classifica** emails em categorias usando IA (Groq/Llama)
- **Remove duplicatas** com cache inteligente (7 dias)
- **Envia resumo** formatado via Telegram com emojis e informações estruturadas
- **Executa periodicamente** via GitHub Actions (a cada 6 horas)

Ideal para categorizar e monitorar:
- 💼 **Vagas** de emprego (com status: entrevista agendada, proposta, etc)
- 📚 **Treinamentos** e cursos
- 🎯 **Workshops** e eventos
- 📰 **Newsletters**
- 💰 **Notificações financeiras**

## ⚡ Funcionalidades

### Classificação Inteligente
- Detecta categoria automaticamente (vagas, treinamento, workshops, newsletters, financeiro, outros)
- Extrai informações relevantes de vagas (empresa, cargo, senioridade, modalidade, salário, tecnologias)
- Identifica status de processos seletivos (nova vaga, entrevista agendada, proposta, reprovado, etc)
- Filtra por perfil do candidato (tecnologias, cargo, senioridade)

### Deduplicação
- Cache com hash MD5 do email (subject + sender + snippet)
- Retém histórico de 7 dias
- Evita reprocessar emails duplicados

### Envio via Telegram
- Formatação elegante com Markdown e emojis
- Agrupamento por categoria
- Links diretos para candidaturas

## 📋 Pré-requisitos

- Python 3.11+
- Conta Google com Gmail ativado
- Token da API Groq (IA)
- Token do Telegram Bot
- Acesso a GitHub Actions (para automation)

## 🚀 Instalação Local

### 1. Clone o repositório

```bash
git clone https://github.com/seu-usuario/email-organizer.git
cd email-organizer
```

### 2. Crie um ambiente virtual

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

## ⚙️ Configuração

### 1. Google Gmail (OAuth2)

O projeto usa autenticação OAuth2 interativa. Execute:

```bash
python auth_interactive.py
```

Isto vai:
1. Abrir uma URL no navegador
2. Você faz login na sua conta Google
3. Autoriza o acesso ao Gmail
4. Retorna um JSON com o token

**Salve o JSON resultante** - você vai usar em:
- `token.json` (localmente)
- `GMAIL_TOKEN` secret (GitHub)

Para uso estável em GitHub Actions, extraia também:
- `client_id`
- `client_secret`
- `refresh_token`

E configure como secrets separados (veja seção de Deploy).

### 2. API Groq (IA)

1. Acesse [console.groq.com](https://console.groq.com)
2. Gere uma API Key
3. Configure a variável de ambiente:
   ```bash
   set GROQ_API_KEY=sua_chave_aqui
   ```

### 3. Telegram Bot

1. Converse com [@BotFather](https://t.me/botfather) no Telegram
2. Crie um novo bot: `/newbot`
3. Anote o **token**
4. Descubra seu **chat ID**:
   - Envie qualquer mensagem para o bot
   - Acesse: `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - Procure por `"id"` no JSON

## 🏃 Como usar

### Execução local

```bash
cd src
python main.py
```

Saída esperada:
```
Lendo emails...
X emails encontrados.
Processando Y emails novos...
Classificando...
Enviando para o Telegram...
Digest enviado com sucesso!
```

### Variáveis de ambiente necessárias

```bash
# Gmail
set GMAIL_TOKEN={"token": "...", "client_id": "...", ...}

# IA
set GROQ_API_KEY=gsk_...
set GROQ_MODEL=llama-3.1-8b-instant  # opcional

# Telegram
set TELEGRAM_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
set TELEGRAM_CHAT_ID=987654321
```

## 🔄 Automação com GitHub Actions

O workflow `.github/workflows/daily_digest.yml` executa automaticamente a cada 6 horas.

### Configurar Secrets

No repositório, acesse **Settings → Secrets and variables → Actions** e adicione:

| Secret | Valor |
|--------|-------|
| `GMAIL_TOKEN` | JSON completo do token Google |
| `GMAIL_CLIENT_ID` | client_id do credentials.json |
| `GMAIL_CLIENT_SECRET` | client_secret do credentials.json |
| `GMAIL_REFRESH_TOKEN` | refresh_token do credentials.json |
| `GROQ_API_KEY` | Chave da API Groq |
| `TELEGRAM_TOKEN` | Token do bot Telegram |
| `TELEGRAM_CHAT_ID` | ID do seu chat no Telegram |

### Executar manualmente

No GitHub, vá para **Actions → Email Digest Diário → Run workflow**

## 📁 Estrutura do Projeto

```
email-organizer/
├── .github/
│   └── workflows/
│       └── daily_digest.yml          # GitHub Actions automation
├── src/
│   ├── main.py                        # Orquestrador principal
│   ├── gmail_reader.py                # Lê emails do Gmail
│   ├── classifier.py                  # Classifica e analisa com IA
│   └── telegram_sender.py             # Envia digest ao Telegram
├── auth_interactive.py                # Gera token OAuth2
├── requirements.txt                   # Dependências Python
├── .gitignore                         # Arquivos ignorados (token, venv)
└── README.md                          # Este arquivo
```

### Arquivos de configuração

- `credentials.json` - Credenciais do Google Cloud (não commitado)
- `token.json` - Token OAuth2 gerado (não commitado)
- `processed_emails.json` - Cache de emails processados (gerado em runtime)

## 🔧 Stack Tecnológico

- **Python 3.11+** - Linguagem principal
- **Gmail API** - Acesso aos emails
- **Groq API** - Classificação com IA (Llama 3.1)
- **python-telegram-bot** - Integração Telegram
- **GitHub Actions** - Automação e CI/CD

## 🛠️ Desenvolvimento

### Adicionar nova categoria

Edite `src/classifier.py` e atualize:

1. `CATEGORIES` - Adicione palavras-chave
2. `CANDIDATO` (se relevante) - Adicione skills/cargos alvo
3. Lógica de análise conforme necessário

### Customizar análise

A classificação acontece em `classifier.py`. Modifique:
- Prompts enviados à IA
- Parsing de respostas
- Status e emojis

### Filtrar emails por tipo

Em `src/main.py`, ajuste o filtro Gmail:
```python
result = service.users().messages().list(
    userId='me', q=f'after:{since} is:unread'
).execute()
```

## 📝 Logs e Debugging

Os logs são impressos no console/Actions. Para mais detalhes:

```bash
# Local
python -u src/main.py

# GitHub Actions
Veja a aba "Run workflow" para cada execução
```

## 📄 Licença

MIT License - sinta-se livre para usar, modificar e distribuir

## 🤝 Contribuições

Contribuições são bem-vindas! Abra uma issue ou pull request com suas melhorias.

## 📞 Suporte

- Dúvidas? Abra uma [issue](https://github.com/seu-usuario/email-organizer/issues)
- Documentação de APIs:
  - [Gmail API](https://developers.google.com/gmail/api)
  - [Groq API](https://groq.com)
  - [Telegram Bot API](https://core.telegram.org/bots/api)