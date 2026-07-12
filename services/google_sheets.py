from config import SPREADSHEET_ID, get_credentials_path

import gspread

_client: gspread.Client | None = None
_spreadsheet: gspread.Spreadsheet | None = None
_worksheet_cache: dict[str, gspread.Worksheet] = {}


def normalize_text(value: str) -> str:
    return " ".join(value.strip().split()).lower()


def normalize_username(username: str) -> str:
    return username.strip().lstrip("@").lower()


def reset_google_sheets_cache() -> None:
    global _client, _spreadsheet, _worksheet_cache

    _client = None
    _spreadsheet = None
    _worksheet_cache = {}


def get_gspread_client() -> gspread.Client:
    global _client

    if _client is None:
        _client = gspread.service_account(filename=str(get_credentials_path()))
    return _client


def get_spreadsheet() -> gspread.Spreadsheet:
    global _spreadsheet

    if _spreadsheet is None:
        _spreadsheet = get_gspread_client().open_by_key(SPREADSHEET_ID)
    return _spreadsheet


def get_spreadsheet_url() -> str:
    return f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"


def find_worksheet_case_insensitive(
    spreadsheet: gspread.Spreadsheet, worksheet_name: str
) -> gspread.Worksheet:
    target = normalize_text(worksheet_name)
    cached = _worksheet_cache.get(target)
    if cached is not None:
        return cached

    for ws in spreadsheet.worksheets():
        if normalize_text(ws.title) == target:
            _worksheet_cache[target] = ws
            return ws
    raise ValueError(f"Лист '{worksheet_name}' не найден в таблице")
