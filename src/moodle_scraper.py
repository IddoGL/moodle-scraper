import os
from urllib.parse import urljoin, parse_qs, urlparse
import requests
from bs4 import BeautifulSoup

from utils import sanitize_filename, save_link_to_csv, get_filename_from_response

class MoodleScraper:
    def __init__(self, base_url, username, password):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        # Pretend to be a regular browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        })

    def login(self) -> bool:
        login_url = f"{self.base_url}/login/index.php"
        
        try:
            # 1. Fetch login page to get the logintoken
            response = self.session.get(login_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find the logintoken hidden input
            token_input = soup.find('input', {'name': 'logintoken'})
            logintoken = token_input['value'] if token_input else ''
            
            # 2. Perform POST request with credentials
            payload = {
                'username': self.username,
                'password': self.password,
                'logintoken': logintoken
            }
            
            post_response = self.session.post(login_url, data=payload)
            post_response.raise_for_status()
            
            # 3. Verify login (usually redirects to /my/ or contains logout link)
            if 'login/index.php' not in post_response.url and ('logout' in post_response.text or 'loginerrormessage' not in post_response.text):
                return True
            return False
            
        except Exception as e:
            print(f"Login failed: {e}")
            return False

    def get_enrolled_courses(self):
        """Returns a list of dicts: [{'id': '123', 'name': 'Course A'}, ...]"""
        dashboard_url = f"{self.base_url}/my/"
        response = self.session.get(dashboard_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        courses = []
        seen_ids = set()
        
        # 1. Try finding links visually available on `/my/` or `/my/courses.php`
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if 'course/view.php?id=' in href:
                course_id = parse_qs(urlparse(href).query).get('id', [None])[0]
                
                name_element = a_tag.find(class_=['multiline', 'coursename']) or a_tag.find('span') or a_tag
                name = name_element.get_text(strip=True)
                
                # Filter out generic UI links
                if course_id and name and len(name) > 3 and "view.php" not in name and course_id not in seen_ids:
                    seen_ids.add(course_id)
                    courses.append({'id': course_id, 'name': sanitize_filename(name)})
                    
        # 2. Most modern Moodle instances load course blocks dynamically via AJAX.
        # Let's extract the `sesskey` and call the core_course AJAX endpoint if the above failed.
        if not courses:
            import re
            sesskey_match = re.search(r'"sesskey":"([a-zA-Z0-9]+)"', response.text)
            if not sesskey_match:
               sesskey_match = re.search(r'name="sesskey" value="([a-zA-Z0-9]+)"', response.text)
               
            if sesskey_match:
                sesskey = sesskey_match.group(1)
                ajax_url = f"{self.base_url}/lib/ajax/service.php?sesskey={sesskey}&info=core_course_get_enrolled_courses_by_timeline_classification"
                payload = [{
                    "index": 0,
                    "methodname": "core_course_get_enrolled_courses_by_timeline_classification",
                    "args": {
                        "offset": 0,
                        "limit": 99,
                        "classification": "all",
                        "sort": "fullname"
                    }
                }]
                
                ajax_response = self.session.post(ajax_url, json=payload)
                if ajax_response.status_code == 200:
                    try:
                        data = ajax_response.json()
                        if not data[0].get('error'):
                            for course_data in data[0]['data']['courses']:
                                c_id = str(course_data['id'])
                                c_name = course_data['fullname']
                                if c_id not in seen_ids:
                                    seen_ids.add(c_id)
                                    courses.append({'id': c_id, 'name': sanitize_filename(c_name)})
                    except Exception as e:
                        pass
        return courses

    def download_file_direct(self, url, dest_dir, progress_callback=None):
        """Downloads a file directly, supporting progress updates."""
        try:
            # Stream the request to get file size and download iteratively
            with self.session.get(url, stream=True) as response:
                response.raise_for_status()
                
                # Check if we were redirected to a Moodle login page (session expired, etc)
                if 'login/index.php' in response.url:
                    return None
                    
                # We might have landed on a preview page instead of a direct download
                # But typically /mod/resource/view.php?id=X redirects to the actual /pluginfile.php/...
                
                # If we're an HTML page, it might be a resource page with a download link inside
                content_type = response.headers.get('Content-Type', '')
                if 'text/html' in content_type and 'pluginfile.php' not in response.url:
                    # Let's inspect the page for the real file link
                    soup = BeautifulSoup(response.content, 'html.parser')
                    # Look for the main resource link
                    div = soup.find('div', class_='resourceworkaround')
                    if div and div.find('a'):
                        real_url = div.find('a')['href']
                        # Recursive call with the real URL
                        return self.download_file_direct(real_url, dest_dir, progress_callback)
                    
                filename = get_filename_from_response(response)
                file_path = os.path.join(dest_dir, filename)
                
                # Don't download if it already exists and size matches? For simplicity, we just overwrite or skip.
                # Let's skip if exists.
                if os.path.exists(file_path):
                    if progress_callback:
                        progress_callback(filename, 0, completed=True)
                    return file_path
                
                total_size = int(response.headers.get('content-length', 0))
                
                if progress_callback:
                    task_id = progress_callback(filename, total_size, init=True)
                
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            if progress_callback:
                                progress_callback(filename, len(chunk), update=True, task_id=task_id)
                                
                if progress_callback:
                    progress_callback(filename, 0, completed=True, task_id=task_id)
                    
                return file_path

        except Exception as e:
            # Failed to download
            return None

    def scrape_folder(self, url, dest_dir, progress_callback=None):
        """Pages with /mod/folder/... contain multiple files"""
        response = self.session.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Moodle folders usually list files inside a span class="fp-filename" with a parent anchor tag
        for a_tag in soup.find_all('a', href=True):
            if 'pluginfile.php' in a_tag['href']:
                file_url = a_tag['href']
                os.makedirs(dest_dir, exist_ok=True)
                # Download it directly
                # Adding ?forcedownload=1 helps bypass HTML previews for some file types
                download_url = file_url + ("&forcedownload=1" if "?" in file_url else "?forcedownload=1")
                self.download_file_direct(download_url, dest_dir, progress_callback)

    def scrape_assignment(self, url, assign_dir, progress_callback=None):
        """Assignments can have attached files and descriptions with links."""
        response = self.session.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. Search for attachment files (avoiding our own submissions)
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if 'pluginfile.php' in href and 'assign' in href:
                 # Skip student submissions and grading feedback files
                 if 'assignsubmission' in href or 'assignfeedback' in href:
                     continue
                 os.makedirs(assign_dir, exist_ok=True)
                 self.download_file_direct(href, assign_dir, progress_callback)
                 
        # 2. Search for external links inside the prompt/description
        intro_div = soup.find('div', id='intro')
        if intro_div:
            for a_tag in intro_div.find_all('a', href=True):
                href = a_tag['href']
                text = a_tag.get_text(strip=True) or href
                
                # Check if it's an external link (not our moodle base)
                if href.startswith('http') and not href.startswith(self.base_url):
                    save_link_to_csv(assign_dir, text, href)

    def scrape_url_module(self, url, course_dir):
        """Pages with /mod/url/view.php redirect or contain the external link."""
        response = self.session.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the URL workaround link (click here to open...)
        workaround = soup.find('div', class_='urlworkaround')
        if workaround and workaround.find('a'):
            actual_url = workaround.find('a')['href']
            title = soup.find('h2').get_text(strip=True) if soup.find('h2') else "External Link"
            save_link_to_csv(course_dir, title, actual_url)

    def scrape_quiz(self, url, course_dir, module_name):
        """Scrapes a Moodle quiz, finding the highest graded review attempt and exporting to JSON."""
        response = self.session.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        review_links = soup.find_all('a', href=True)
        best_review_url = None
        highest_grade = -1.0
        
        attempts = [a['href'] for a in review_links if '/mod/quiz/review.php?attempt=' in a['href']]
        
        if not attempts:
            return  # No reviewable attempts found
            
        # Try to parse the table to find the attempt with the highest grade
        for tr in soup.find_all('tr'):
            review_link = next((a['href'] for a in tr.find_all('a', href=True) if '/mod/quiz/review.php?attempt=' in a['href']), None)
            
            if review_link:
                # Look for numbers in the table columns (grades)
                for col in tr.find_all(['td', 'th']):
                    text = col.get_text(strip=True).replace(',', '.')
                    try:
                        # Attempt to extract float values
                        from re import findall
                        numbers = findall(r"[-+]?\d*\.\d+|\d+", text)
                        for num in numbers:
                            val = float(num)
                            if val > highest_grade:
                                highest_grade = val
                                best_review_url = review_link
                    except Exception:
                        pass
                        
        if not best_review_url:
            best_review_url = attempts[-1] # fallback to last attempt
            
        # Append showall=1 to avoid pagination
        review_url = best_review_url + "&showall=1"
        res = self.session.get(review_url)
        review_soup = BeautifulSoup(res.text, 'html.parser')
        
        questions_data = []
        
        for que in review_soup.find_all('div', class_='que'):
            q_data = {
                "question_text": "",
                "options": [],
                "student_answer": "",
                "correct_answer": "",
                "grade_info": "",
                "question_html": ""
            }
            
            qtext_div = que.find('div', class_='qtext')
            if qtext_div:
                q_data["question_html"] = str(qtext_div)
                q_data["question_text"] = qtext_div.get_text(separator='\n', strip=True)
                
            answer_div = que.find('div', class_='answer')
            if answer_div:
                for label in answer_div.find_all('label'):
                    text = label.get_text(separator=' ', strip=True)
                    # Filter out purely structural things if needed, mostly the text is fine.
                    q_data["options"].append(text)
                    
                input_field = answer_div.find('input', type='text')
                if input_field and input_field.get('value'):
                    q_data["student_answer"] = input_field.get('value')
                    
            right_answer_div = que.find('div', class_='rightanswer')
            if right_answer_div:
                q_data["correct_answer"] = right_answer_div.get_text(separator=' ', strip=True).replace('The correct answer is: ', '').replace('The correct answers are: ', '')
                
            grade_div = que.find('div', class_='grade')
            if grade_div:
                q_data["grade_info"] = grade_div.get_text(strip=True)
                
            questions_data.append(q_data)
            
        if questions_data:
            from utils import save_quiz_to_json
            save_quiz_to_json(course_dir, module_name, questions_data)

    def scrape_course(self, course_id, course_name, base_download_dir, progress_callback=None):
        course_url = f"{self.base_url}/course/view.php?id={course_id}"
        response = self.session.get(course_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        course_dir = os.path.join(base_download_dir, course_name)
        os.makedirs(course_dir, exist_ok=True)
        
        # Moodle sections contain activities
        # We look for all module links: /mod/.../view.php?id=...
        for module in soup.find_all('a', href=True):
            href = module['href']
            
            # Module name usually inside an instancename span
            name_span = module.find('span', class_='instancename')
            module_name = sanitize_filename(name_span.get_text(strip=True).split('File')[0].split('URL')[0].strip()) if name_span else "Unnamed_Module"
            
            if '/mod/resource/view.php' in href:
                # Direct file
                self.download_file_direct(href, course_dir, progress_callback)
                
            elif '/mod/folder/view.php' in href:
                # Nested Folder
                folder_dir = os.path.join(course_dir, module_name)
                self.scrape_folder(href, folder_dir, progress_callback)
                
            elif '/mod/assign/view.php' in href:
                # Assignment
                assign_dir = os.path.join(course_dir, module_name)
                self.scrape_assignment(href, assign_dir, progress_callback)
                
            elif '/mod/url/view.php' in href:
                # External URL Link
                self.scrape_url_module(href, course_dir)
                
            elif '/mod/quiz/view.php' in href:
                # Quiz JSON Export
                self.scrape_quiz(href, course_dir, module_name)
                
        return course_dir
