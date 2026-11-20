"""In-memory Sheets adapter with atomic-batch behavior, no credentials/network."""
from copy import deepcopy
import re


class Sheet:
    def __init__(self, title, rows=None, sheet_id=1):
        self.title, self.rows, self.id = title, deepcopy(rows or []), sheet_id
        self.writes = []
        self.fail_append_after = False

    def get_all_values(self):
        return deepcopy(self.rows)

    def row_values(self, n):
        return list(self.rows[n-1]) if len(self.rows) >= n else []

    def update(self, range_name, values, **kwargs):
        self.writes.append((range_name, deepcopy(values), kwargs))
        match = re.match(r'([A-Z]+)([0-9]+)', range_name)
        column = 0
        for character in match[1]:
            column = column * 26 + ord(character) - ord('A') + 1
        column -= 1
        n = int(match[2]) - 1
        while len(self.rows) < n + len(values):
            self.rows.append([])
        for i, row in enumerate(values):
            target = self.rows[n+i]
            target.extend([''] * max(0, column + len(row) - len(target)))
            target[column:column + len(row)] = row

    def update_cell(self, row, column, value):
        while len(self.rows) < row:
            self.rows.append([])
        while len(self.rows[row-1]) < column:
            self.rows[row-1].append('')
        self.rows[row-1][column-1] = value


    def append_row(self, values, **kwargs):
        self.writes.append(('append', list(values), kwargs))
        self.rows.append(list(values))
        if self.fail_append_after:
            self.fail_append_after = False
            raise TimeoutError('lost append response')
        return {'updates': {'updatedRange': f"'{self.title}'!A{len(self.rows)}:I{len(self.rows)}"}}

    def col_values(self, n):
        return [row[n-1] if len(row) >= n else '' for row in self.rows]


class Spreadsheet:
    def __init__(self, *sheets):
        self.sheets = list(sheets)
        self.batches = []
        self.metadata = {}
        self.batch_error_before = None
        self.batch_error_after = False
        self.deferred_batch = None

    def worksheets(self):
        return list(self.sheets)

    def add_worksheet(self, title, **kwargs):
        sheet = Sheet(title, sheet_id=len(self.sheets)+10)
        self.sheets.append(sheet)
        return sheet

    def batch_update(self, body):
        if self.batch_error_before:
            raise self.batch_error_before
        self.batches.append(deepcopy(body))
        if self.deferred_batch is False:
            self.deferred_batch = body
            raise TimeoutError('still in flight')
        self.apply_batch(body)
        if self.batch_error_after:
            self.batch_error_after = False
            raise TimeoutError('lost batch response')
        return {}

    def apply_batch(self, body):
        # Real spreadsheets.batchUpdate validates all requests before applying.
        snapshots = {s.id: deepcopy(s.rows) for s in self.sheets}
        metadata = self.metadata.copy()
        for request in body['requests']:
            if 'createDeveloperMetadata' in request:
                entry = request['createDeveloperMetadata']['developerMetadata']
                if entry['metadataId'] in metadata:
                    raise ValueError('duplicate developer metadata id')
                metadata[entry['metadataId']] = entry['metadataValue']
            elif 'appendCells' in request:
                data = request['appendCells']
                target = snapshots[data['sheetId']]
                target.extend([self._values(row) for row in data['rows']])
            else:
                data = request['updateCells']
                target = snapshots[data['start']['sheetId']]
                index = data['start']['rowIndex']
                values = self._values(data['rows'][0])
                target[index] = values + target[index][len(values):]
        self.metadata = metadata
        for sheet in self.sheets:
            sheet.rows = snapshots[sheet.id]

    @staticmethod
    def _values(row):
        return [str(next(iter(cell.get('userEnteredValue', {}).values()), '')) for cell in row['values']]
