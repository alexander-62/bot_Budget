import gspread

from config import GOOGLE_CREDENTIALS_FILE, SPREADSHEET_ID


def normalize_text(value: str) -> str:
    return " ".join(value.strip().split()).lower()


def normalize_username(username: str) -> str:
    return username.strip().lstrip("@").lower()


def get_spreadsheet() -> gspread.Spreadsheet:
    gc = gspread.service_account(filename=GOOGLE_CREDENTIALS_FILE)
    return gc.open_by_key(SPREADSHEET_ID)


def get_spreadsheet_url() -> str:
    return f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"


def find_worksheet_case_insensitive(
    spreadsheet: gspread.Spreadsheet, worksheet_name: str
) -> gspread.Worksheet:
    target = normalize_text(worksheet_name)
    for ws in spreadsheet.worksheets():
        if normalize_text(ws.title) == target:
            return ws
    raise ValueError(f"Лист '{worksheet_name}' не найден в таблице")
