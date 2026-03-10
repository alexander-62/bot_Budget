# Настройка Google Таблицы для бота

## Шаг 1: Создание Google Таблицы

1. Откройте [Google Таблицы](https://sheets.google.com/)
2. Создайте новую таблицу
3. Назовите её (например, `Budget Bot`)
4. Создайте лист с именем `transactions` (или любым другим)
5. В первой строке создайте заголовки столбцов, например:
   - `A1`: `date`
   - `B1`: `user_id`
   - `C1`: `amount`
   - `D1`: `category`
   - `E1`: `description`

## Шаг 2: Получение ID таблицы

1. Откройте вашу таблицу
2. В адресной строке URL будет выглядеть так:
   ```
   https://docs.google.com/spreadsheets/d/1A2B3C4D5E6F7G8H9I0J/edit#gid=0
   ```
3. Скопируйте часть между `/d/` и `/edit` — это и есть **SPREADSHEET_ID**:
   ```
   1A2B3C4D5E6F7G8H9I0J
   ```

## Шаг 3: Создание сервисного аккаунта Google

1. Откройте [Google Cloud Console](https://console.cloud.google.com/)
2. Создайте новый проект (или выберите существующий)
3. В меню слева выберите **APIs & Services** → **Library**
4. Найдите и включите **Google Sheets API**
5. Также включите **Google Drive API** (для доступа к файлам)

## Шаг 4: Создание учетных данных

1. Перейдите в **APIs & Services** → **Credentials**
2. Нажмите **Create Credentials** → **Service Account**
3. Заполните информацию:
   - **Service account name**: `budget-bot`
   - **Service account ID**: заполнится автоматически
   - **Description**: опционально
4. Нажмите **Create and Continue**
5. Пропустите шаг с ролями (или выберите **Viewer**)
6. Нажмите **Done**

## Шаг 5: Создание ключа сервисного аккаунта

1. В списке сервисных аккаунтов нажмите на созданный аккаунт
2. Перейдите на вкладку **Keys**
3. Нажмите **Add Key** → **Create new key**
4. Выберите тип ключа **JSON**
5. Нажмите **Create**
6. Файл автоматически скачается на компьютер
7. Переименуйте его в `credentials.json` и поместите в папку с ботом

## Шаг 6: Предоставление доступа таблице

1. Откройте вашу Google Таблицу
2. Нажмите кнопку **Share** (Поделиться) в правом верхнем углу
3. В поле "Добавить людей" вставьте email сервисного аккаунта
   - Email выглядит так: `budget-bot@project-id.iam.gserviceaccount.com`
   - Его можно найти в файле `credentials.json` в поле `client_email`
4. Выберите роль **Editor** (Редактор)
5. Нажмите **Send** (или **Done**)

## Шаг 7: Установка зависимостей

Выполните команду в терминале:

```bash
pip install gspread
```

Или обновите `requirements.txt`:

```bash
echo gspread >> requirements.txt
pip install -r requirements.txt
```

## Шаг 8: Настройка secrets.py

Добавьте в файл `secrets.py` следующие переменные:

```python
# Токен Telegram бота
BOT_TOKEN = "ваш_токен_бота"

# ID Google таблицы (из шага 2)
SPREADSHEET_ID = "ваш_id_таблицы"

# Путь к файлу с учетными данными
GOOGLE_CREDENTIALS_FILE = "credentials.json"
```

## Шаг 9: Проверка подключения

Создайте тестовый файл `test_google.py`:

```python
import gspread
from secrets import SPREADSHEET_ID, GOOGLE_CREDENTIALS_FILE

# Авторизация
gc = gspread.service_account(filename=GOOGLE_CREDENTIALS_FILE)

# Открытие таблицы
sh = gc.open_by_key(SPREADSHEET_ID)

# Получение первого листа
worksheet = sh.sheet1

# Чтение данных
all_records = worksheet.get_all_records()
print("Данные из таблицы:", all_records)

# Запись данных
worksheet.append_row(["2024-01-01", "123", "100", "food", "Обед"])
print("Данные добавлены!")
```

Запустите:

```bash
python test_google.py
```

Если всё работает — вы увидите данные из таблицы и сообщение об успешной записи.

## Если появилась ошибка 403 (API не включен)

Пример ошибки:

`Google Sheets API has not been used in project ... before or it is disabled`

Это значит, что Google видит ключ, но API для проекта сервисного аккаунта еще не активирован (или изменения еще не применились).

Сделайте по шагам:

1. Откройте [Google Cloud Console](https://console.cloud.google.com/).
2. Вверху выберите именно тот проект, к которому относится ваш `credentials.json`.
   - Номер проекта можно увидеть в тексте ошибки (например: `project 356880314515`).
   - Также можно проверить в `credentials.json` поле `project_id`.
3. Перейдите в **APIs & Services** → **Library**.
4. Найдите и включите:
   - **Google Sheets API**
   - **Google Drive API**
5. Откройте **APIs & Services** → **Enabled APIs & services** и убедитесь, что оба API в списке включенных.
6. Подождите 2-10 минут.
   - Иногда активация API применяется не мгновенно.
7. Запустите снова:

```bash
python test_google.py
```

Если после ожидания ошибка осталась:

1. Проверьте, что таблица расшарена на `client_email` из `credentials.json` с ролью **Editor**.
2. Убедитесь, что в `secrets.py` указан правильный `SPREADSHEET_ID` (часть URL между `/d/` и `/edit`).
3. Убедитесь, что `GOOGLE_CREDENTIALS_FILE = "credentials.json"` и файл лежит в папке проекта.
4. Перепроверьте, что вы включили API именно в том проекте, чей ключ используете.
5. Подождите еще 10-15 минут и повторите запуск.

---

## Готово!

Теперь можно создавать модуль для работы с Google Таблицей в боте.
