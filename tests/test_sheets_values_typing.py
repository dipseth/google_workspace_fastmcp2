"""Unit tests for Sheets value typing and validation fixes.

Guards the fixes for:
- read_sheet_values crashing on numeric/boolean cells returned by
  value_render_option="UNFORMATTED_VALUE" (SheetValuesResponse.values was
  typed List[List[str]]).
- modify_sheet_values rejecting non-string cells, making it impossible to
  write real numbers/booleans with valueInputOption="RAW".
"""

from sheets.sheets_tools import _validate_2d_values
from sheets.sheets_types import SheetValuesResponse


class TestSheetValuesResponseTyping:
    def test_accepts_unformatted_value_cells(self):
        """UNFORMATTED_VALUE reads return floats/ints/bools — must not raise."""
        response = SheetValuesResponse(
            spreadsheetId="abc",
            range="Sheet1!A1:D2",
            values=[[1.5, 2, True, "text"], ["", None, -3, 0.0]],
            rowCount=2,
            columnCount=4,
        )
        assert response.values[0][0] == 1.5
        assert response.values[0][2] is True

    def test_accepts_formatted_string_cells(self):
        response = SheetValuesResponse(
            spreadsheetId="abc",
            range="A1",
            values=[["$1,234.00"]],
            rowCount=1,
            columnCount=1,
        )
        assert response.values == [["$1,234.00"]]


class TestValidate2DValues:
    def test_accepts_scalar_cells(self):
        assert _validate_2d_values([["a", 1, 2.5, True, None]]) is None

    def test_accepts_empty_rows(self):
        assert _validate_2d_values([[], ["x"]]) is None

    def test_rejects_nested_lists(self):
        assert _validate_2d_values([[["nested"]]]) is not None

    def test_rejects_dict_cells(self):
        assert _validate_2d_values([[{"not": "a scalar"}]]) is not None

    def test_rejects_non_list_rows(self):
        assert _validate_2d_values(["not-a-row"]) is not None
