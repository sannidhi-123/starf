# CAN CSV dataset format

## Columns

Required columns, in any header order: `timestamp`, `can_id`, `dlc`, and `data_0` through `data_7`.

Optional columns: `is_remote`, `source`, `capture`, `attack_type`, `label`, and `label_quality`. The metadata columns `source`, `capture`, `attack_type`, and `label_quality` are retained as provided and are not value-validated. `is_remote` and `label` are validated when their columns are present.

## Types and ranges

| Column | Type | Accepted values |
| --- | --- | --- |
| `timestamp` | Number | Finite and greater than or equal to 0; timestamps need not be ordered. |
| `can_id` | Integer | Decimal or `0x`-prefixed hexadecimal, from 0 through `0x1FFFFFFF`. |
| `dlc` | Integer | 0 through 8. |
| `data_i`, for `i < dlc` | Integer byte | Required, from 0 through 255. |
| `data_i`, for `i >= dlc` | Empty value or integer zero | Empty or `0`. |
| `is_remote` | Boolean-like value | `True`, `False`, `1`, or `0`, case-insensitive. |
| `label` | Integer | `0` or `1`. |
| `source`, `capture`, `attack_type`, `label_quality` | Text metadata | Accepted as provided. |

## Validation errors

The API returns these `detail` messages. `{row}` is replaced with the one-based CSV line number, including the header line as line 1.

- Missing upload file: `A CSV file is required in the 'file' field.`
- Unsupported filename extension: `The uploaded file must have a .csv extension.`
- Empty file: `The CSV file is empty.`
- Missing header: `The CSV header is missing.`
- Missing required headers: `Missing required CSV columns: {comma-separated columns}.`
- Duplicate header: `The CSV header contains duplicate columns.`
- Wrong row field count: `Row {row}: expected {header field count} fields, found {actual field count}.`
- No nonblank data rows: `The CSV file has no data rows.`
- Invalid UTF-8: `The CSV file must use UTF-8 encoding.`
- CSV parser error: `Invalid CSV structure: {parser error}.`
- Invalid `can_id` syntax: `Row {row}: can_id must be an integer in decimal or 0x-prefixed hexadecimal form.`
- `can_id` outside range: `Row {row}: can_id must be between 0 and 0x1FFFFFFF.`
- Invalid or out-of-range `dlc`: `Row {row}: dlc must be an integer from 0 to 8.`
- Invalid required payload byte: `Row {row}: data_i must be a non-empty integer from 0 to 255 when index is less than dlc.`
- Invalid trailing payload value: `Row {row}: data_i must be empty or 0 when index is greater than or equal to dlc.`
- Invalid `timestamp`: `Row {row}: timestamp must be a finite, non-negative number.`
- Invalid `is_remote`: `Row {row}: is_remote must be True, False, 1, or 0 (case-insensitive).`
- Invalid `label`: `Row {row}: label must be 0 or 1.`
- File larger than 25 MiB: `The uploaded file exceeds the 26214400-byte limit.`
- Unknown dataset ID: `Dataset '{dataset_id}' was not found.`

## Examples

Valid fixture row (line 2):

```csv
0.0,1072,8,102,121,210,214,74,202,87,116,False,synthetic,fixture,normal,0,frame
```

Invalid fixture row (line 11):

```csv
0.010448,304,2,87,128,-1,-1,-1,-1,-1,-1,False,synthetic,fixture,normal,0,frame
```

This row violates the trailing-payload rule; because `dlc` is 2, `data_2` through `data_7` must each be empty or `0`. The API returned: `Row 11: data_2 must be empty or 0 when index is greater than or equal to dlc.`

Step 6 invalid value examples were also checked through the API:

- `can_id=0x20000000`: `Row 2: can_id must be between 0 and 0x1FFFFFFF.`
- `dlc=9`: `Row 2: dlc must be an integer from 0 to 8.`
- `dlc=3` with empty `data_0`: `Row 2: data_0 must be a non-empty integer from 0 to 255 when index is less than dlc.`
- `timestamp=-1`: `Row 2: timestamp must be a finite, non-negative number.`
- `is_remote=maybe`: `Row 2: is_remote must be True, False, 1, or 0 (case-insensitive).`

## HTTP status codes

| Status | Behavior |
| --- | --- |
| `201` | CSV validated and dataset metadata returned. |
| `400` | Uploaded filename does not end in `.csv`. |
| `413` | File exceeds 25 MiB (26,214,400 bytes). |
| `422` | Missing file, empty or malformed CSV, or row validation failure. |
| `404` | Requested dataset ID is not in the current dataset catalog. |
