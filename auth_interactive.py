import argparse
from pathlib import Path
import traceback
from urllib.parse import parse_qs, urlparse

from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def extract_code(value: str) -> str:
	if value.startswith("http://") or value.startswith("https://"):
		query = urlparse(value).query
		code = parse_qs(query).get("code", [""])[0]
		return code.strip()
	return value.strip()


def resolve_redirect_uri(flow: InstalledAppFlow, oauth_response: str | None = None) -> str | None:
	if oauth_response and (oauth_response.startswith("http://") or oauth_response.startswith("https://")):
		parsed = urlparse(oauth_response)
		if parsed.scheme and parsed.netloc:
			return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

	redirect_uris = flow.client_config.get("installed", {}).get("redirect_uris", [])
	if redirect_uris:
		return redirect_uris[0]
	return None


def authorize_by_pasted_url(flow: InstalledAppFlow):
	redirect_uri = resolve_redirect_uri(flow)
	if redirect_uri:
		flow.redirect_uri = redirect_uri

	auth_url, _ = flow.authorization_url(
		access_type="offline",
		prompt="consent",
		include_granted_scopes="true",
	)
	print("\nAbra esta URL no navegador e conclua a autorizacao:")
	print(auth_url)
	print("\nDepois, cole a URL final de redirecionamento (http://localhost:...)")
	response_or_code = input("URL final (ou somente code=...): ").strip()
	redirect_uri = resolve_redirect_uri(flow, response_or_code)
	if redirect_uri:
		flow.redirect_uri = redirect_uri
	flow.fetch_token(code=extract_code(response_or_code))
	return flow.credentials


def generate_token_json(
	oauth_response: str | None = None,
	use_local_server: bool = True,
) -> str | None:
	credentials_path = Path("credentials.json")
	if not credentials_path.exists():
		print("Erro: credentials.json nao encontrado na raiz do projeto.")
		print("Baixe o arquivo no Google Cloud Console e tente novamente.")
		return None

	try:
		flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
	except ValueError as exc:
		print("Erro ao carregar credentials.json:")
		print(exc)
		print("\nConfirme que o OAuth Client foi criado como 'Desktop app'.")
		return None

	try:
		if oauth_response:
			code = extract_code(oauth_response)
			if not code:
				print("Erro: nao foi possivel extrair o parametro 'code' da entrada informada.")
				return None
			redirect_uri = resolve_redirect_uri(flow, oauth_response)
			if redirect_uri:
				flow.redirect_uri = redirect_uri
			flow.fetch_token(code=code)
			creds = flow.credentials
		elif use_local_server:
			# Fluxo recomendado pelo Google para apps locais.
			# Com open_browser=False, a URL aparece no terminal para copia manual.
			creds = flow.run_local_server(host="localhost", port=8080, open_browser=False)
		else:
			creds = authorize_by_pasted_url(flow)
	except KeyboardInterrupt:
		print("\nAutorizacao interrompida. Mudando para modo de URL colada...")
		creds = authorize_by_pasted_url(flow)
	except Exception as exc:
		print("Erro durante a autorizacao OAuth:")
		print(exc)
		if oauth_response:
			return None
		if "redirect_uri" in str(exc).lower() or "invalid_request" in str(exc).lower():
			print("\nPossivel causa: credencial OAuth incorreta ou sem redirect URI valido.")
			print("No Google Cloud Console, crie um OAuth Client do tipo 'Desktop app'.")
			print("Depois, baixe novamente o credentials.json e tente de novo.")
			return None
		print("\nTentando modo alternativo por URL colada...")
		try:
			creds = authorize_by_pasted_url(flow)
		except Exception:
			print("\nDetalhes tecnicos:")
			traceback.print_exc()
			return None

	return creds.to_json()


def main() -> None:
	parser = argparse.ArgumentParser(description="Gera token OAuth do Gmail")
	parser.add_argument(
		"oauth_response",
		nargs="?",
		help="URL final de redirecionamento OU apenas o valor do parametro code",
	)
	parser.add_argument(
		"--manual",
		action="store_true",
		help="Nao inicia servidor local; usa somente URL colada no terminal",
	)
	args = parser.parse_args()

	token_json = generate_token_json(
		oauth_response=args.oauth_response,
		use_local_server=not args.manual,
	)
	if not token_json:
		return

	# Salva localmente para facilitar debug e uso futuro.
	Path("token.json").write_text(token_json, encoding="utf-8")

	print("\nToken gerado com sucesso.")
	print("Copie o JSON abaixo e salve no secret GMAIL_TOKEN:")
	print(token_json)


if __name__ == "__main__":
	main()
