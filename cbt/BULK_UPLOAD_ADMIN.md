# Django Admin Bulk Question Upload

## Overview
The Django Admin panel now supports bulk uploading of exam questions directly from the admin interface. This feature allows administrators to upload multiple questions with their answers and explanations at once, instead of creating them one by one.

## Features
- **Admin Interface**: Access bulk upload from `/admin/cbt/bulk-upload/`
- **Exam & Subject Selection**: Choose which exam and subject to upload questions to
- **JSON Format Support**: Paste JSON array of questions
- **Validation**: Real-time validation of JSON format and required fields
- **Error Reporting**: Detailed error messages for failed questions
- **Automatic Creation**: Questions and multiple choice options created in a single action

## How to Use

### Access the Feature
1. Log in to Django Admin: `http://localhost:8000/admin/`
2. Click on the "CBT" app section
3. Look for "📤 Bulk Upload Questions" link (or navigate directly to `/admin/cbt/bulk-upload/`)

### Upload Questions

1. **Select Exam**: Choose the exam (JAMB, NECO, WAEC, etc.)
2. **Select Subject**: Choose the subject (automatically filtered by selected exam)
3. **Paste JSON Data**: Paste your questions in the JSON format below
4. **Submit**: Click "Upload Questions"

### JSON Format

```json
[
  {
    "question_text": "Which element has atomic number 6?",
    "options": {
      "A": "Carbon",
      "B": "Nitrogen",
      "C": "Oxygen",
      "D": "Boron"
    },
    "correct_answer": "A",
    "explanation": "Carbon is the element with atomic number 6",
    "subject": "Chemistry"
  },
  {
    "question_text": "What is 2 + 2?",
    "options": {
      "A": "3",
      "B": "4",
      "C": "5",
      "D": "6"
    },
    "correct_answer": "B",
    "explanation": "2 plus 2 equals 4",
    "subject": "Mathematics"
  }
]
```

### Required Fields
- `question_text` (string): The question being asked
- `options` (object): Multiple choice options with keys A, B, C, D
- `correct_answer` (string): The letter of the correct option (A, B, C, or D)
- `explanation` (string): Explanation for the correct answer
- `subject` (string): The subject name

## Response Handling

### Successful Upload
- Shows a success message with count of created questions
- Redirects to the subject's change page in admin
- You can then review and edit the uploaded questions

### Partial Success (Some Questions Failed)
- Shows success count and warning message
- Lists the first 10 errors (if more than 10, shows count of remaining)
- Common errors:
  - Missing required fields
  - Invalid JSON format
  - Correct answer doesn't match any option
  - Options must be at least 2 items

### All Failed
- Shows error count and details
- Redirects back to the form so you can fix issues

## Validation Rules
✓ Question text cannot be empty
✓ At least 2 options required (preferably 4)
✓ Options must be object format (not array)
✓ Correct answer must be one of the option keys
✓ All fields are required

## Error Examples

**Invalid JSON Format:**
```
⚠ Invalid JSON: Expecting value: line 1 column 1 (char 0)
```

**Missing Required Field:**
```
⚠ Question 1: Missing question_text
```

**Incorrect Answer Format:**
```
⚠ Question 2: correct_answer "E" not in options
```

## Integration Points

### Admin URLs
- Main view: `/admin/cbt/bulk-upload/`
- Added to: `backend/lep_backend/urls.py`

### Files Modified/Created
1. **backend/cbt/admin_views.py** (NEW)
   - `bulk_upload_questions_admin()` view function

2. **backend/cbt/forms.py** (UPDATED)
   - `BulkQuestionUploadForm` class with JSON validation

3. **backend/cbt/templates/cbt/bulk_upload_admin.html** (NEW)
   - Professional admin interface template

4. **backend/templates/admin/index.html** (NEW)
   - Admin home page with bulk upload link

5. **backend/lep_backend/urls.py** (UPDATED)
   - Added URL pattern for bulk upload view

6. **backend/lep_backend/settings.py** (UPDATED)
   - Added templates directory to TEMPLATES config

7. **backend/cbt/admin.py** (UPDATED)
   - Imports for admin view and template customization

## Tips & Best Practices

### Before Uploading
- Validate your JSON format (use JSONLint online)
- Double-check correct answers match option keys
- Ensure all required fields are present

### Excel to JSON Conversion
If you have questions in Excel:
1. Export to CSV
2. Use an online CSV to JSON converter
3. Add missing fields (correct_answer, explanation)
4. Format options as object

### Batch Uploads
For large datasets:
- Split into smaller batches (100-500 questions)
- Test first with a small batch
- Monitor error messages for patterns

### After Upload
- Review questions in the admin Questions list
- Edit any questions that need correction
- Check that correct answers are properly marked

## Troubleshooting

### Template Not Found Error
Make sure templates are in the correct locations:
- `/backend/templates/admin/index.html`
- `/backend/cbt/templates/cbt/bulk_upload_admin.html`

### "Staff Member Only" Message
Ensure your user account has:
- Staff status enabled
- Appropriate admin permissions

### JSON Validation Fails
Common issues:
- Missing quotes around keys
- Trailing commas in arrays
- Mixed quote types (' and ")
- Non-ASCII characters not properly escaped

### Questions Created But With Wrong Information
- Check the JSON data for typos
- Verify correct_answer matches the intended option
- Review the explanation text

## Alternative Methods

This feature complements the existing bulk upload methods:

1. **Django Admin Bulk Upload** (NEW)
   - Direct admin interface
   - URL: `/admin/cbt/bulk-upload/`

2. **Dedicated BulkUploadPage** (Existing)
   - Frontend React component
   - URL: `/bulk-upload`
   - File upload or JSON textarea

3. **API Endpoint** (Existing)
   - For programmatic access
   - Endpoint: `POST /api/cbt/bulk-upload/`

4. **Master Admin Dashboard** (Existing)
   - Quick JSON upload for master admins
   - Available in admin dashboard

All methods accept the same JSON format and create questions in the same way.
