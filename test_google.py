from config import SPREADSHEET_ID, get_credentials_path

import gspread


def main() -> None:
    # Авторизация через сервисный аккаунт
    gc = gspread.service_account(filename=str(get_credentials_path()))

    # Открытие таблицы по ID
    sh = gc.open_by_key(SPREADSHEET_ID)
    worksheet = sh.sheet1

    # Чтение данных
    all_records = worksheet.get_all_records()
    print("Данные из таблицы:", all_records)

    # Тестовая запись
    worksheet.append_row(["2026-03-06", "123", "100", "food", "Обед"])
    print("Данные добавлены!")


if __name__ == "__main__":
    main()
