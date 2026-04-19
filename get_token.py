from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import json, os

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
creds = flow.run_local_server(port=0, access_type='offline', prompt='consent')

# Garante que o refresh_token está presente
data = json.loads(creds.to_json())
print(json.dumps(data, indent=2))