# Email Organizer

Automacao em Python que le emails do Gmail, classifica mensagens com IA e envia um resumo estruturado via Telegram. O projeto foi criado para reduzir triagem manual de caixa de entrada e monitorar mensagens relevantes, especialmente vagas, treinamentos, eventos, newsletters e alertas financeiros.

## Visao Geral

O fluxo combina Gmail API, regras de classificacao, Groq/Llama, cache de deduplicacao e GitHub Actions. A cada execucao, os emails recentes sao coletados, analisados, categorizados e enviados em formato de digest.

## Resultado

- Leitura automatizada de emails recentes e nao lidos.
- Classificacao por categoria e status.
- Extracao de informacoes relevantes de vagas, como empresa, cargo, senioridade, modalidade, salario e tecnologias.
- Deduplicacao com cache temporario para evitar mensagens repetidas.
- Envio de resumo formatado para Telegram.
- Execucao recorrente via GitHub Actions.

## Arquitetura

```text
Gmail API -> gmail_reader.py -> main.py -> classifier.py -> Groq/Llama
                                             \-> telegram_sender.py -> Telegram
                                             \-> processed_emails.json
```

## Stack

- Python 3.11+
- Gmail API
- OAuth2
- Groq API / Llama
- Telegram Bot API
- GitHub Actions
- JSON
- Automacao

## Estrutura

```text
email-organizer/
├── .github/workflows/daily_digest.yml
├── src/
│   ├── main.py
│   ├── gmail_reader.py
│   ├── classifier.py
│   └── telegram_sender.py
├── auth_interactive.py
├── HOW_IT_WORKS.md
├── requirements.txt
└── README.md
```

## Como Executar Localmente

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python auth_interactive.py
python src/main.py
```

No Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python auth_interactive.py
python src/main.py
```

## Variaveis e Secrets

Configure localmente ou no GitHub Actions:

```env
GMAIL_TOKEN=...
GMAIL_CLIENT_ID=...
GMAIL_CLIENT_SECRET=...
GMAIL_REFRESH_TOKEN=...
GROQ_API_KEY=...
GROQ_MODEL=llama-3.1-8b-instant
TELEGRAM_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## GitHub Actions

O workflow `.github/workflows/daily_digest.yml` executa o digest periodicamente. Para rodar manualmente:

1. Acesse a aba `Actions`.
2. Selecione o workflow de digest.
3. Clique em `Run workflow`.

## Detalhes Tecnicos

A explicacao completa do fluxo, camadas e dependencias entre modulos esta em [HOW_IT_WORKS.md](HOW_IT_WORKS.md).

## Cuidados de Seguranca

- Nunca commitar `token.json`, `credentials.json`, `.env` ou chaves de API.
- Revogar tokens caso algum segredo tenha sido exposto.
- Manter `processed_emails.json` fora do Git, pois pode conter metadados de mensagens.

## Proximos Passos

- Adicionar testes unitarios para classificacao.
- Criar logs estruturados.
- Separar prompts da IA em arquivos de configuracao.
- Adicionar exemplos anonimizados de entrada e saida.
