http://localhost:8080/?state=2Y1X9c34w2LFNfGDvIGplXGJxPhSbV&iss=https://accounts.google.com&code=4/0Aci98E90s66sgzhkRzTSNC1bacN5-jxFY0jShxdkcEUw_Jh5xrnNXwZrAiiIXuKc-xydPw&scope=https://www.googleapis.com/auth/gmail.readonly#!/usr/bin/env python3
"""
Wrapper manual para gerar token OAuth usando o fluxo compartilhado.
"""
import json

from auth_interactive import generate_token_json


def main() -> None:
    print("Cole a URL final completa (http://localhost:...) ou somente o code:")
    user_input = input("> ").strip()

    try:
        token_json = generate_token_json(oauth_response=user_input, use_local_server=False)
        if not token_json:
            raise SystemExit(1)
        token_data = json.loads(token_json)
    except Exception as exc:
        print(f"❌ Erro ao converter código: {exc}")
        raise SystemExit(1)

    print("\n✅ Token gerado com sucesso!")
    print("\n" + "="*80)
    print("📋 COPIE TODO O JSON ABAIXO E COLE NO GITHUB SECRET 'GMAIL_TOKEN':")
    print("="*80)
    print("\n" + json.dumps(token_data, indent=2) + "\n")
    print("="*80)
    print("\n✨ Como usar:")
    print("1. Copie o JSON acima (Ctrl+C)")
    print("2. Vá para: https://github.com/Victor884/email-organizer/settings/secrets/actions")
    print("3. Clique em 'GMAIL_TOKEN'")
    print("4. Cole o JSON no campo 'Secret'")
    print("5. Clique em 'Update secret'")


if __name__ == "__main__":
    main()
