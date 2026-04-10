# Moodle LMS Scraper

A CLI tool to scrape and download files from a Moodle LMS. It handles authentication, course discovery, and downloading course contents.

## Features

- **Automated Login**: Uses Moodle `logintoken` for authentication.
- **Course Discovery**: Detects enrolled courses natively with a fallback API extractor for dynamically loaded dashboards.
- **CLI Interface**: Uses `rich` for the interactive menu and download progress bars.
- **Scraping Support**:
  - Files (`/mod/resource`)
  - Folders (`/mod/folder`)
  - Assignment Attachments (`/mod/assign`)
  - **Quizzes** (`/mod/quiz`): Scrapes your highest graded attempt review, extracting the full question text, multiple choice options, your answer, correct answer, and grade. The output is cleanly formatted into a `.json` file, making it perfect for feeding into a Graph Database, an Anki Deck, or experimenting with RAG/LLM embeddings!
- **External Link Archiving**: Extracts third-party links (like YouTube or Google Drive) found in lessons or assignment prompts and aggregates them into a clean `links.csv` file inside your class folder.
- **Flexible Selection**: Download all classes, specific lists (e.g., `0, 2, 4`), or exclusionary filters (e.g., `all except 1`).

## Setup

### 1. Environment

Python 3.7+ is required. Google Chrome must be installed if you want to use the Google Drive download feature. Using a virtual environment is recommended:

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

*(Note: `playwright install chromium` is needed for the Playwright engine, even though local Chrome is used for profile authentication).*

### 3. Configuration

Copy `.env.example` to create your `.env` file:

```bash
cp .env.example .env
```

Open `.env` and configure your Moodle URL, username, and password.

## Usage

Run the main script:

```bash
python src/cli.py
```

1. **Google Drive Integration**: You will be asked if you want to enable Google Drive downloading. If yes, select the Chrome Profile associated with your Google account. Your Chrome browser must be fully closed for this step to work.
2. **Select Courses**: Enter your selection based on the list of enrolled courses (`all`, `0, 2`, `all except 1`).
3. **Output**: Files are saved to a `downloads/` directory, organized by course.
