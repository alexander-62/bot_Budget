import secrets as app_secrets

BOT_TOKEN = app_secrets.BOT_TOKEN
GOOGLE_CREDENTIALS_FILE = app_secrets.GOOGLE_CREDENTIALS_FILE
SPREADSHEET_ID = app_secrets.SPREADSHEET_ID
WEBAPP_URL = getattr(app_secrets, "WEBAPP_URL", "https://example.com/webapp")
WEBAPP_HOST = getattr(app_secrets, "WEBAPP_HOST", "127.0.0.1")
WEBAPP_PORT = getattr(app_secrets, "WEBAPP_PORT", 8080)
