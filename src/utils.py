import os
import re
import csv
import json
import urllib.parse
from pathlib import Path

def sanitize_filename(filename: str) -> str:
    """Sanitizes a string to be a safe filename format."""
    # Remove invalid characters for Windows and Unix
    filename = urllib.parse.unquote(filename)
    filename = re.sub(r'[\\/*?:"<>|]', "-", filename)
    filename = filename.replace('\n', ' ').replace('\r', '')
    return filename.strip()

def save_link_to_csv(course_dir: str, title: str, url: str):
    """Saves an external link to a links.csv file in the respective course directory."""
    os.makedirs(course_dir, exist_ok=True)
    csv_path = os.path.join(course_dir, "links.csv")
    
    file_exists = os.path.isfile(csv_path)
    with open(csv_path, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['Title', 'URL'])
        writer.writerow([title, url])

def save_quiz_to_json(course_dir: str, title: str, quiz_data: list):
    """Saves quiz data to a JSON file."""
    os.makedirs(course_dir, exist_ok=True)
    json_path = os.path.join(course_dir, f"{title}.json")
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(quiz_data, f, indent=4, ensure_ascii=False)

def get_filename_from_response(response) -> str:
    """
    Attempts to extract the filename from the Content-Disposition header.
    If it fails, it falls back to the URL.
    """
    if "Content-Disposition" in response.headers:
        content_disposition = response.headers["Content-Disposition"]
        # Example format: attachment; filename="document.pdf"
        # Or: inline; filename*=UTF-8''document.pdf
        match_utf8 = re.search(r"filename\*\s*=\s*UTF-8''(.+)", content_disposition, re.IGNORECASE)
        match_standard = re.search(r'filename="?([^"]+)"?', content_disposition)
        
        if match_utf8:
            filename = urllib.parse.unquote(match_utf8.group(1))
            return sanitize_filename(filename)
        elif match_standard:
            filename = urllib.parse.unquote(match_standard.group(1))
            return sanitize_filename(filename)
            
    # Fallback to last segment of the url path
    url_path = urllib.parse.urlsplit(response.url).path
    filename = os.path.basename(url_path)
    
    # Very generic fallback if Moodle hides filename
    if not filename or "view.php" in filename:
        filename = "downloaded_file"
        
    return sanitize_filename(filename)
