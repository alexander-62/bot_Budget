"""Exercise real profile bootstraps in separate processes with fake Sheets."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from services.bot_profiles import BotProfile


ROOT = Path(__file__).resolve().parents[1]
CHILD = r'''
import sys, json
sys.path.insert(0, sys.argv[1])
from unittest.mock import patch
with patch('services.profile_secrets.load_token', return_value='123:fake'):
    import config
from datetime import date
from decimal import Decimal
from services import google_sheets, access, expenses, daily_digest
from state.expense_session import create_session, get_active_session

category = 'Офис' if config.PROFILE_ID == 'business' else 'Дом'
allowed_id = 101 if config.PROFILE_ID == 'business' else 202
opened = []

class Worksheet:
    def __init__(self, title, rows):
        self.title, self.rows = title, rows
    def col_values(self, col):
        return [row[col-1] if len(row) >= col else '' for row in self.rows]
    def append_row(self, row, **kwargs):
        self.rows.append(row)
        return {'updates': {'updatedRange': f'{self.title}!A{len(self.rows)}:H{len(self.rows)}'}}
    def get_all_values(self):
        return self.rows

users = Worksheet('Users', [['username','user_id','digest_enabled','last_digest_date'], ['',str(allowed_id),'TRUE','']])
records = Worksheet('Траты_по_месяцам', [['дата','месяц','пользователь','категория','подкатегория','сумма','комментарий','expense_id']])
class Sheet:
    def worksheets(self): return [users, records]
class Client:
    def open_by_key(self, key):
        opened.append(key)
        return Sheet()

with patch.object(google_sheets.gspread, 'service_account', return_value=Client()):
    assert get_active_session(42) is None
    session = create_session(42, 'amount')
    session.category = category
    saved = expenses.write_expense(str(allowed_id), category, 'Подкатегория', '10.25')
    summary = daily_digest.build_daily_digest_summary(date.fromisoformat(saved.date))
    print(json.dumps({
        'profile': config.PROFILE_ID, 'table': opened, 'rows': len(records.rows),
        'category': get_active_session(42).category,
        'allowed': access.is_allowed_user(allowed_id, None)[0],
        'denied': access.is_allowed_user(303, 'known')[0],
        'digest': daily_digest.format_daily_digest_message(summary),
        'amount': records.rows[-1][5],
        'runtime': str(config.PROFILE_RUNTIME_DIR),
    }, ensure_ascii=False))
'''


class ProfileIsolationTests(unittest.TestCase):
    def test_two_workers_keep_sheets_access_sessions_and_digests_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            # Copy only the non-secret loader. All configuration is generated.
            (base / 'config.py').write_text((ROOT / 'config.py').read_text(encoding='utf-8'), encoding='utf-8')
            (base / '.env').write_text('GOOGLE_CREDENTIALS_FILE=fake-key.json\n', encoding='utf-8')
            profiles = [BotProfile('business', 'Бизнес', 'business-table', 'RUB'),
                        BotProfile('family', 'Семья', 'family-table', 'EUR')]
            (base / 'profiles.json').write_text(json.dumps({'version': 1, 'profiles': [asdict(p) for p in profiles]}), encoding='utf-8')
            workers = []
            for profile in profiles:
                env = {key: value for key, value in os.environ.items()
                       if not key.startswith('BOT_BUDGET_') and key not in {'BOT_TOKEN', 'SPREADSHEET_ID', 'GOOGLE_CREDENTIALS_FILE'}}
                env['BOT_BUDGET_PROFILE'] = profile.id
                env['PYTHONUTF8'] = '1'  # Parent decoding does not configure child stdout on Windows.
                workers.append(subprocess.Popen([sys.executable, '-c', CHILD, str(base)], cwd=ROOT,
                                                env=env, text=True, encoding='utf-8', stdout=subprocess.PIPE, stderr=subprocess.PIPE))
            results = []
            for worker in workers:
                try:
                    stdout, stderr = worker.communicate(timeout=30)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.communicate()
                    self.fail('Fake worker timed out')
                self.assertEqual(worker.returncode, 0, stderr)
                results.append(json.loads(stdout))
            business, family = results
            self.assertEqual(business['table'], ['business-table'])
            self.assertEqual(family['table'], ['family-table'])
            self.assertEqual([r['rows'] for r in results], [2, 2])
            self.assertEqual([r['category'] for r in results], ['Офис', 'Дом'])
            self.assertTrue(all(r['allowed'] and not r['denied'] for r in results))
            self.assertEqual([r['amount'] for r in results], [10.25, 10.25])
            self.assertIn('₽', business['digest'])
            self.assertNotIn('€', business['digest'])
            self.assertIn('€', family['digest'])
            self.assertNotIn('₽', family['digest'])
            self.assertNotEqual(business['runtime'], family['runtime'])


if __name__ == '__main__':
    unittest.main()
