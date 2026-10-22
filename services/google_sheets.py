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


def open_profile_spreadsheet(profile, credentials_path):
    """Open an explicit profile without touching the running bot's caches."""
    return gspread.service_account(filename=str(credentials_path)).open_by_key(profile.spreadsheet_id)


def validate_profile_connection(profile, credentials_path):
    # Import lazily: startup validation itself uses the cached adapter above.
    from services.startup_validation import get_worksheet_rules, validate_worksheet_header
    from constants import MONEY_SOURCES_SHEET_NAME
    spreadsheet = open_profile_spreadsheet(profile, credentials_path)
    worksheets = {normalize_text(ws.title): ws for ws in spreadsheet.worksheets()}
    from services.budget_settings import BudgetSettings, read_settings, SETTINGS_SHEET
    settings = read_settings(spreadsheet) if normalize_text(SETTINGS_SHEET) in worksheets else BudgetSettings(profile.currency)
    for rule in get_worksheet_rules(profile, limits_enabled=settings.monthly_limits_enabled):
        worksheet = worksheets.get(normalize_text(rule.name))
        if worksheet is None:
            raise ValueError(f"Не найден лист «{rule.name}». Создайте его по шаблону.")
        if rule.required_headers:
            try:
                validate_worksheet_header(rule, worksheet.row_values(1), legacy=profile.legacy, track_money_source=profile.track_money_source)
            except ValueError:
                raise ValueError(f"Лист «{rule.name}»: проверьте обязательные заголовки и порядок столбцов по шаблону.") from None
        if rule.name == MONEY_SOURCES_SHEET_NAME:
            from services.money_sources import parse_money_sources
            if not parse_money_sources(worksheet.get_all_values()):
                raise ValueError("Лист «Источники»: добавьте хотя бы один активный источник.")
    return True
