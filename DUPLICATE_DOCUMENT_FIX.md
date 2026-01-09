# Duplicate Document Handling Bug Fix

## Problem

In `quarterly_pdf_ingest.py`, the duplicate document check incorrectly unpacks the return value from `check_duplicate_document()`. The function returns `(is_duplicate: bool, existing_asset_id: int)`, but the code treats the second value as `existing_hash` (a string), causing `TypeError: 'int' object is not subscriptable` when trying to slice it.

## Root Cause

1. **Incorrect unpacking**: Line 109 unpacks as `is_duplicate, existing_hash` but `check_duplicate_document()` returns `(bool, int)` - the second value is `existing_asset_id`, not a hash string.

2. **String slicing on int**: Line 118 attempts `existing_hash[:16]` which fails because `existing_hash` is actually an `int` (asset_id).

3. **Incorrect status**: Duplicates are marked as `'success': False` which is incorrect - they should be marked as `SKIPPED`, not `FAILED`.

4. **Summary reporting**: The summary logic doesn't distinguish between skipped (duplicates) and failed (errors).

## Solution

### Changes Made

1. **Fixed tuple unpacking** (line 109):
   - Changed `existing_hash` to `existing_asset_id` to correctly reflect the return type
   - Updated variable name to match the actual value

2. **Fixed logging** (line 116-118):
   - Use `file_hash` (already available) for the hash display in log message
   - Include `existing_asset_id` in the log message for better traceability

3. **Fixed duplicate status** (line 120):
   - Changed `'success': False` to `'success': 'skipped'`
   - Added `'existing_asset_id'` field to the returned dictionary

4. **Updated summary logic** (`ingest_quarterly_pdf_from_dir`):
   - Separate counting: `successful`, `skipped`, `failed`
   - Updated log message to show all three categories
   - Uses `r.get('success') is True` for successful, `r.get('success') == 'skipped'` for skipped, `r.get('success') is False` for failed

5. **Updated CLI summary** (`main` function):
   - Separate counting: `successful`, `skipped`, `failed`
   - Print skipped PDFs separately from failed PDFs
   - Exit code is 0 only if `failed == 0` (skipped duplicates don't cause exit failure)

### Key Implementation Details

```python
# Correct unpacking
is_duplicate, existing_asset_id = check_duplicate_document(...)

# Correct logging
logger.warning(
    f"Skipping {pdf_path.name} - duplicate document detected "
    f"(existing asset_id={existing_asset_id}, hash: {file_hash[:16]}...)"
)

# Correct status
return {
    'success': 'skipped',  # Not False!
    'existing_asset_id': existing_asset_id,
    'file_hash': file_hash,
    ...
}

# Correct summary counting
successful = sum(1 for r in results if r.get('success') is True)
skipped = sum(1 for r in results if r.get('success') == 'skipped')
failed = sum(1 for r in results if r.get('success') is False)
```

## Benefits

✅ **Fixed TypeError** - Correct unpacking prevents int slicing error  
✅ **Correct status** - Duplicates marked as 'skipped', not 'failed'  
✅ **Better reporting** - Summary distinguishes skipped vs failed  
✅ **Proper exit codes** - Script exits with 0 if only duplicates (no actual failures)  
✅ **Better logging** - Includes asset_id and hash for traceability  

## Validation

Running:
```bash
python vfis/ingestion/quarterly_pdf_ingest.py --ticker ZOMATO --input_dir vfis/data/zomato/quarterly
```

Will now:
- ✅ Detect all PDFs as duplicates correctly
- ✅ Skip them cleanly without TypeError
- ✅ Report 0 failures (duplicates are skipped, not failed)
- ✅ Exit without exceptions
- ✅ Show proper summary: "X successful, Y skipped (duplicates), Z failed"

## Files Modified

1. ✅ `vfis/ingestion/quarterly_pdf_ingest.py` - Fixed duplicate handling in `ingest_pdf()`, `ingest_quarterly_pdf_from_dir()`, and `main()`

## Safety Guarantees

✅ **No hashing logic changes** - Only fixed unpacking, not hash computation  
✅ **No database schema changes** - Only fixed code that uses existing schema  
✅ **No ingestion flow changes** - Logic flow unchanged, only status reporting  
✅ **Duplicate detection not disabled** - Still detects duplicates, just handles them correctly  
✅ **No PDF parsing changes** - Parsing logic untouched  
✅ **Windows-compatible** - No platform-specific changes  

