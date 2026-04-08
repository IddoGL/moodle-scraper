# Moodle LMS Scraper

CLI tool designed to scrape and download files from your university's Moodle LMS. It automates logging in, discovering your enrolled classes, and bulk-downloading course contents directly to your computer.

## Features

- **Automated Login**: Handles Moodle `logintoken` extraction to establish an authenticated session.
- **Course Discovery**: Detects enrolled courses natively, and includes a fallback API extractor for modern Moodle instances that load dashboards dynamically.
- **CLI UI**: Powered by `rich` to provide a menu and live download progress bars.
- **Flexible Scraping**: Supports downloading:
  - Files (`/mod/resource`)
  - Nested Directories (`/mod/folder`)
  - Assignment Attachments (`/mod/assign`)
  - **Quizzes** (`/mod/quiz`): Scrapes your highest graded attempt review, extracting the full question text, multiple choice options, your answer, correct answer, and grade. The output is formatted into a `.json` file
- **External Link Archiving**: Extracts third-party links (like YouTube or Google Drive) found in lessons or assignment prompts and aggregates them into a clean `links.csv` file inside your class folder.
- **Flexible Selection**: Download all classes, specific lists (e.g., `0, 2, 4`), or exclusionary filters (e.g., `all except 1`).

## 🛠 Setup

### 1. Environment

Ensure you have Python 3.7+ installed. Using a virtual environment is highly recommended:

```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configuration

For security, this script utilizes environment variables so you never accidentally upload your password to GitHub.

Copy the `.env.example` file to create your local `.env`:

```bash
cp .env.example .env
```

Open `.env` in any text editor and provide your school's Moodle URL, username, and password.

## Usage

Execute the main CLI script:

```bash
python src/cli.py
```

1. **Select Courses**: The interface will list your enrolled courses. Follow the prompt to enter `all`, `0, 2`, or `all except 1`.
2. **Review Output**: Once completed, a new `downloads/` directory will be created in your root folder. Your downloaded files will be organized neatly by class.
