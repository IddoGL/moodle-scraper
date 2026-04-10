import os
import platform
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
import img2pdf
from rich.console import Console

console = Console()

def get_chrome_user_data_dir():
    """Detects OS and returns the default Chrome User Data directory."""
    sys_os = platform.system()
    if sys_os == "Windows":
        return os.path.expanduser('~\\AppData\\Local\\Google\\Chrome\\User Data')
    elif sys_os == "Darwin":
        return os.path.expanduser('~/Library/Application Support/Google/Chrome')
    else:
        return os.path.expanduser('~/.config/google-chrome')

def get_chrome_profiles():
    """Returns a dict of {friendly_name: profile_dir_name} by parsing 'Local State'"""
    user_data_dir = get_chrome_user_data_dir()
    local_state_path = os.path.join(user_data_dir, "Local State")
    profiles = {}
    
    if not os.path.exists(local_state_path):
        return {"Default": "Default"}
        
    try:
        with open(local_state_path, 'r', encoding='utf-8') as f:
            local_state = json.load(f)
            
        info_cache = local_state.get('profile', {}).get('info_cache', {})
        for profile_dir, info in info_cache.items():
            name = info.get('name', profile_dir)
            user_name = info.get('user_name', '')
            if user_name:
                display = f"{name} ({user_name})"
            else:
                display = name
            profiles[display] = profile_dir
            
    except Exception as e:
        console.print(f"[yellow]Warning: Could not parse Local State: {e}[/yellow]")
        profiles["Default"] = "Default"
        
    return profiles

class GoogleDriveDownloader:
    def __init__(self, profile_dir_name):
        self.user_data_dir = get_chrome_user_data_dir()
        self.profile_dir_name = profile_dir_name
        self.browser = None
        self.playwright_context = None

    def start_browser(self):
        import os
        from rich.console import Console
        from rich.panel import Panel
        console = Console()
        
        # Clean up any leftover state
        self.close_browser()

        self.playwright_context = sync_playwright().start()
        
        session_dir = os.path.abspath(os.path.join("downloads", ".gdrive_session"))
        os.makedirs(session_dir, exist_ok=True)
        
        console.print("[dim]Checking Google Drive authentication in isolated Playwright sandbox...[/dim]")
        
        # Launch interactive browser to check authentication natively
        self.browser = self.playwright_context.chromium.launch_persistent_context(
            user_data_dir=session_dir,
            channel="chrome",
            headless=False,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )
        
        page = self.browser.new_page()
        page.goto("https://drive.google.com/drive/my-drive", timeout=60000)
        
        if "accounts.google.com" in page.url or "ServiceLogin" in page.url:
            console.print(Panel(
                "[bold yellow]Google Drive Authentication Required![/]\n\n"
                "A clean, tracking-free Google Chrome window has just opened.\n"
                "Please securely log in to your [bold green]University Google Account[/bold green] in that window.\n"
                "Once you log in successfully, the window will automatically close and save your session forever.",
                title="Authentication Profile Setup"
            ))
            
            try:
                page.wait_for_url("**/drive/my-drive*", timeout=300000) # 5 minutes timeout
                console.print("[green]Authentication successful! Saving secure session...[/green]")
                page.wait_for_timeout(3000) # Give cookies a moment to flush to SQLite
            except Exception:
                raise Exception("Authentication timeout! Please try running the script again.")
                
        # Close the visible browser
        page.close()
        self.browser.close()
        
        console.print("  [dim]Authentication valid! Launching stealth headless downloading engine...[/dim]")
        
        self.browser = self.playwright_context.chromium.launch_persistent_context(
            user_data_dir=session_dir,
            channel="chrome",
            headless=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 1600},
            device_scale_factor=2
        )

    def close_browser(self):
        try:
            if getattr(self, 'browser', None):
                self.browser.close()
            if getattr(self, 'playwright_context', None):
                self.playwright_context.stop()
        except:
            pass
        finally:
            self.browser = None
            self.playwright_context = None

    def _get_total_pages(self, page):
        """Parse total page count from the Google Drive viewer UI."""
        import re
        try:
            full_text = page.inner_text('body')
            m = re.search(r'/\s*(\d+)', full_text)
            if m:
                return int(m.group(1))
        except Exception:
            pass
        return 0

    def _find_page_input(self, page):
        """Find the page number input field in the Drive viewer."""
        for selector in ['input[type="number"]', 'input[aria-label*="Page"]',
                         'input[aria-label*="page"]', 'input[class*="jfk-textinput"]']:
            el = page.query_selector(selector)
            if el:
                return el
        inputs = page.query_selector_all('input')
        for inp in inputs:
            try:
                bbox = inp.bounding_box()
                if bbox and bbox['width'] < 80 and bbox['height'] < 40:
                    return inp
            except:
                continue
        return None

    def _screenshot_current_page(self, page):
        """Find and screenshot the currently visible page image element.
        
        Uses JavaScript to locate the largest <img> element near the viewport 
        center — this is the rendered PDF page. Screenshots just that element,
        producing a clean capture with exact page dimensions.
        """
        handle = page.evaluate_handle('''() => {
            const imgs = Array.from(document.querySelectorAll('img'));
            const viewH = window.innerHeight;
            const viewCenterY = viewH / 2;
            let best = null;
            let bestScore = -1;
            
            for (const img of imgs) {
                const r = img.getBoundingClientRect();
                if (r.width < 200 || r.height < 200) continue;
                
                const visibleTop = Math.max(r.top, 0);
                const visibleBottom = Math.min(r.bottom, viewH);
                if (visibleBottom <= visibleTop) continue;
                
                const visibleArea = (visibleBottom - visibleTop) * r.width;
                const imgCenterY = (r.top + r.bottom) / 2;
                const centerDist = Math.abs(imgCenterY - viewCenterY);
                const score = visibleArea / (1 + centerDist);
                
                if (score > bestScore) {
                    bestScore = score;
                    best = img;
                }
            }
            return best;
        }''')
        
        element = handle.as_element()
        if element:
            try:
                return element.screenshot(type="png")
            except Exception:
                pass
        return None

    def download_pdf(self, url, dest_dir, title):
        page = None
        try:
            if not getattr(self, 'browser', None):
                self.start_browser()
            
            from utils import sanitize_filename
            safe_title = sanitize_filename(title)
            
            page = self.browser.new_page()
            
            pdf_data = None
            
            def handle_response(response):
                nonlocal pdf_data
                if response.status != 200:
                    return
                try:
                    content_type = response.headers.get("content-type", "")
                    if "application/pdf" in content_type:
                        body = response.body()
                        if len(body) > 1024:
                            pdf_data = body
                except Exception:
                    pass

            page.on("response", handle_response)
            
            console.print(f"  [dim]Opening Google Drive link for: {title}...[/dim]")
            
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
            except Exception:
                pass
            
            page.wait_for_timeout(5000)
            
            # ── Strategy 1: Direct download button ──
            try:
                download_btn = page.query_selector('[aria-label="Download"], [data-tooltip="Download"]')
                if download_btn:
                    console.print(f"  [cyan]Download button found — downloading directly...[/cyan]")
                    with page.expect_download(timeout=30000) as download_info:
                        download_btn.click()
                    download = download_info.value
                    save_path = os.path.join(dest_dir, f"{safe_title}.pdf")
                    download.save_as(save_path)
                    console.print(f"  [green]Successfully downloaded: {save_path}[/green]")
                    return True
            except Exception:
                pass
            
            # ── Strategy 2: Raw PDF interception ──
            if pdf_data:
                pdf_path = os.path.join(dest_dir, f"{safe_title}.pdf")
                with open(pdf_path, 'wb') as f:
                    f.write(pdf_data)
                console.print(f"  [green]Intercepted PDF: {pdf_path}[/green]")
                return True
            
            # ── Strategy 3: Page-by-page element screenshot ──
            total_pages = self._get_total_pages(page)
            page_input = self._find_page_input(page)
            
            if total_pages > 0 and page_input:
                console.print(f"  [cyan]Capturing {total_pages} pages...[/cyan]")
                page_screenshots = []
                
                for pg_num in range(1, total_pages + 1):
                    try:
                        page_input.click(click_count=3)
                        page.wait_for_timeout(200)
                        page_input.fill(str(pg_num))
                        page.wait_for_timeout(200)
                        page_input.press("Enter")
                    except Exception:
                        page.keyboard.press("PageDown")
                    
                    page.wait_for_timeout(2500)
                    
                    if pdf_data:
                        pdf_path = os.path.join(dest_dir, f"{safe_title}.pdf")
                        with open(pdf_path, 'wb') as f:
                            f.write(pdf_data)
                        console.print(f"  [green]Intercepted PDF: {pdf_path}[/green]")
                        return True
                    
                    screenshot = self._screenshot_current_page(page)
                    if screenshot:
                        page_screenshots.append(screenshot)
                
                if page_screenshots:
                    pdf_path = os.path.join(dest_dir, f"{safe_title}.pdf")
                    with open(pdf_path, 'wb') as f:
                        f.write(img2pdf.convert(page_screenshots))
                    console.print(f"  [green]Saved ({len(page_screenshots)} pages): {pdf_path}[/green]")
                    return True
            
            # ── Strategy 4: Single-page fallback ──
            screenshot = self._screenshot_current_page(page)
            if screenshot:
                pdf_path = os.path.join(dest_dir, f"{safe_title}.pdf")
                with open(pdf_path, 'wb') as f:
                    f.write(img2pdf.convert([screenshot]))
                console.print(f"  [green]Saved (1 page): {pdf_path}[/green]")
                return True
            
            # Nothing worked
            import random
            uid = random.randint(1000, 9999)
            debug_path = os.path.join(dest_dir, f"DEBUG_{safe_title}_{uid}.png")
            page.screenshot(path=debug_path)
            console.print(f"  [yellow]No pages captured for {title}. Debug: {debug_path}[/yellow]")
            return False
                    
        except Exception as e:
            console.print(f"  [red]Error downloading via Playwright: {e}[/red]")
            self.close_browser()
            return False
            
        finally:
            if page:
                try:
                    page.close()
                except:
                    pass

