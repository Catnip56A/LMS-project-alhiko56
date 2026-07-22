# Google Drive Import Feature

## Overview
This feature allows instructors to import existing files and folders from their Google Drive directly into course content without needing to re-upload files.

## Features

### Single File Import
- Import individual files from Google Drive using:
  - Full sharing URL: `https://drive.google.com/file/d/FILE_ID/view`
  - Short URL with ID parameter: `https://drive.google.com/open?id=FILE_ID`
  - Direct file ID: `FILE_ID`
- Optional custom title (defaults to original filename)
- Select target folder (optional)
- Choose publish status
- Set visibility for students

### Folder Import
- Import entire Google Drive folders with all contained files
- Creates matching folder structure in course
- Bulk imports all files at once
- Automatic ordering and numbering
- All files set to published and visible by default

## How to Use

### For Instructors

1. **Navigate to Course Page**
   - Go to your course page
   - Click the "Content" tab

2. **Click "Import from Drive" Button**
   - Located next to "Create Folder" and "Upload File" buttons
   - Blue button with cloud download icon

3. **Choose Import Type**
   - **Single File**: Import one file at a time
   - **Entire Folder**: Import a folder with all its contents

4. **Provide Google Drive URL**
   - Paste the sharing link from Google Drive
   - Or paste just the file/folder ID
   - Supports multiple URL formats

5. **Configure Options** (for single files)
   - Custom title (optional)
   - Target folder selection
   - Publish status
   - Student visibility

6. **Click Import**
   - File(s) will be imported to your course
   - Success message will confirm import

## Technical Implementation

### Backend Functions (`google_drive_service.py`)

#### `extract_file_id_from_url(drive_url)`
Extracts file or folder ID from various Google Drive URL formats:
- `/file/d/{id}/` pattern
- `/folders/{id}` pattern  
- `id={id}` parameter
- Direct ID string

#### `get_file_metadata(service, file_id)`
Fetches file metadata from Google Drive API:
- File name
- MIME type
- Size
- Icon URL
- Web view link

#### `list_folder_contents(service, folder_id)`
Lists all files in a Google Drive folder:
- Filters out trashed files
- Returns file metadata for each item
- Paginated results (100 per page)

#### `import_drive_file(service, file_id_or_url)`
Imports a single file:
1. Extracts file ID from URL
2. Fetches file metadata
3. Sets permissions for view link
4. Returns file data dictionary

#### `import_drive_folder(service, folder_id_or_url)`
Imports entire folder:
1. Extracts folder ID from URL
2. Gets folder metadata
3. Lists all files in folder
4. Imports each file's metadata
5. Returns folder data with files array

### Route Handlers (`routes/__init__.py`)

#### Action: `import_drive_file`
- Validates drive URL
- Authenticates with Google Drive
- Imports file metadata
- Creates `CourseContent` record
- Sets title, visibility, publish status
- Assigns to folder (if specified)

#### Action: `import_drive_folder`
- Validates drive URL
- Authenticates with Google Drive
- Imports folder metadata
- Creates `CourseContentFolder` record
- Bulk imports all contained files
- Sets all files as published and visible

### UI Components (`templates/course_page_enrolled.html`)

#### Import Button
Located in course content section alongside "Create Folder" and "Upload File"

#### Import Modal
- Radio buttons for import type (file/folder)
- URL input field with placeholder
- Optional title override (single file only)
- Folder selection (single file only)
- Publish checkbox
- Visibility checkbox (single file only)

#### JavaScript Handlers
- Dynamic form field visibility based on import type
- Folder context handling
- Action value switching (import_drive_file vs import_drive_folder)

## URL Format Support

The feature supports these Google Drive URL formats:

### File URLs
```
https://drive.google.com/file/d/1abc123DEF456/view
https://drive.google.com/open?id=1abc123DEF456
1abc123DEF456
```

### Folder URLs
```
https://drive.google.com/drive/folders/1abc123DEF456
https://drive.google.com/drive/u/0/folders/1abc123DEF456
https://drive.google.com/open?id=1abc123DEF456
1abc123DEF456
```

## Error Handling

The feature includes comprehensive error handling for:
- Missing or invalid URLs
- Authentication failures
- Permission denied errors
- Non-existent files/folders
- Network errors

All errors display user-friendly flash messages.

## Permissions

- Files are imported with view permissions
- Original Drive permissions are preserved
- Students see files through course interface
- Instructors can toggle visibility after import

## Limitations

- Requires Google Drive authentication
- Only imports files currently accessible to the authenticated user
- Does not copy files - creates references to original Drive files
- Folder imports are limited to direct children (no recursive subfolder import)
- Large folders may take time to process

## Future Enhancements

Potential improvements for future versions:
- Recursive subfolder import
- Batch file selection within folders
- Sync functionality to update metadata
- Import progress indicator for large folders
- Duplicate detection
- Import history and rollback
