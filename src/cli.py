import os
import sys
from dotenv import load_dotenv
from rich.console import Console
from rich.prompt import Prompt
from rich.progress import Progress, TextColumn, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn

from moodle_scraper import MoodleScraper
from gdrive_scraper import get_chrome_profiles, GoogleDriveDownloader
from utils import save_link_to_csv

console = Console()

def main():
    console.print("[bold blue]Moodle Web Scraper[/bold blue]", justify="center")
    
    # Load .env variables
    load_dotenv()
    moodle_url = os.getenv("MOODLE_URL")
    username = os.getenv("MOODLE_USERNAME")
    password = os.getenv("MOODLE_PASSWORD")
    
    if not all([moodle_url, username, password]):
        console.print("[bold red]Error:[/bold red] Missing configuration. Make sure you copied .env.example to .env and filled it out.")
        sys.exit(1)
        
    console.print("\n[bold]Google Drive Automation (Optional)[/bold]")
    console.print("Do you want to automatically download View-Only Google Drive links using Playwright?")
    console.print("[dim]Note: This requires your actual Google Chrome browser to be closed while it processes at the end![/dim]")
    use_gdrive = Prompt.ask("Enable this feature?", choices=["y", "n"], default="n").lower() == "y"
    
    selected_gdrive_profile = "Default"
    if use_gdrive:
        profiles = get_chrome_profiles()
        if not profiles:
            console.print("[yellow]Could not detect any Chrome profiles. Proceeding with Default.[/yellow]")
        else:
            console.print("\n[bold]Available Chrome Profiles:[/bold]")
            profile_keys = list(profiles.keys())
            for i, p_name in enumerate(profile_keys, 1):
                console.print(f"  [cyan]{i}[/cyan]: {p_name}")
            
            while True:
                p_choice = Prompt.ask("Select the profile containing your University Account (number)", default="1")
                try:
                    idx = int(p_choice) - 1
                    if 0 <= idx < len(profile_keys):
                        selected_gdrive_profile = profiles[profile_keys[idx]]
                        console.print(f"[green]Selected profile directory: {selected_gdrive_profile}[/green]")
                        break
                    else:
                        console.print("[red]Invalid selection.[/red]")
                except ValueError:
                    console.print("[red]Please enter a valid number.[/red]")
                    
    print("\n")
    scraper = MoodleScraper(moodle_url, username, password)
    
    with console.status(f"[bold cyan]Logging into {moodle_url}[/bold cyan]..."):
        if not scraper.login():
            console.print("[bold red]Login failed. Please check your credentials or Moodle URL.[/bold red]")
            sys.exit(1)
            
    console.print("[bold green]Successfully logged in![/bold green]")
    
    with console.status("[bold cyan]Fetching enrolled courses[/bold cyan]..."):
        courses = scraper.get_enrolled_courses()
        
    if not courses:
        console.print("[bold yellow]No enrolled courses found.[/bold yellow]")
        sys.exit(0)
        
    console.print("\n[bold]Your Enrolled Courses:[/bold]")
    for i, course in enumerate(courses):
        console.print(f"[cyan]{i}[/cyan]: {course['name']}")
        
    console.print("\n[bold]Selection Options:[/bold]")
    console.print("  [green]all[/green]            : Download ALL courses")
    console.print("  [green]0, 2, 3[/green]        : Download specific courses")
    console.print("  [green]all except 1,4[/green] : Download all EXCEPT specific courses")
    
    while True:
        choice = Prompt.ask("\nEnter your selection").strip().lower()
        selected_courses = []
        
        if not choice:
            continue
            
        try:
            if choice == "all":
                selected_courses = courses
            elif choice.startswith("all except"):
                excludes_str = choice.replace("all except", "").replace(" ", "")
                if excludes_str:
                    exclude_indices = [int(x) for x in excludes_str.split(",") if x.isdigit()]
                    selected_courses = [c for i, c in enumerate(courses) if i not in exclude_indices]
                else:
                    selected_courses = courses
            else:
                includes_str = choice.replace(" ", "")
                include_indices = [int(x) for x in includes_str.split(",") if x.isdigit()]
                selected_courses = [courses[i] for i in include_indices if 0 <= i < len(courses)]
                
            if not selected_courses:
                console.print("[yellow]No valid courses selected. Please try again.[/yellow]")
                continue
                
            break
        except Exception:
            console.print("[bold red]Invalid format. Please use numbers, commas, or 'all'.[/bold red]")
    
    base_dir = "downloads"
    os.makedirs(base_dir, exist_ok=True)
    
    # Setup the Rich progress bar
    progress = Progress(
        TextColumn("[bold blue]{task.fields[filename]}", justify="right"),
        BarColumn(bar_width=None),
        "[progress.percentage]{task.percentage:>3.1f}%",
        "•",
        DownloadColumn(),
        "•",
        TransferSpeedColumn(),
        "•",
        TimeRemainingColumn(),
        console=console,
        expand=True
    )
    
    def progress_callback(filename, chunk_size, init=False, update=False, completed=False, task_id=None):
        if init:
            return progress.add_task("download", filename=filename[:40], total=chunk_size if chunk_size > 0 else None)
        elif update:
            progress.update(task_id, advance=chunk_size)
        elif completed:
            if task_id is not None:
                progress.update(task_id, completed=True)
                progress.remove_task(task_id)

    # Execute scraping
    for course in selected_courses:
        console.print(f"\n[bold magenta]Scraping '{course['name']}'...[/bold magenta]")
        with progress:
            scraper.scrape_course(course['id'], course['name'], base_dir, progress_callback)
            
    # Process Google Drive Links
    if use_gdrive and scraper.gdrive_links:
        console.print(f"\n[bold magenta]Starting batch download for {len(scraper.gdrive_links)} Google Drive PDFs...[/bold magenta]")
        console.print("[bold yellow]Please make sure all Google Chrome windows are closed now![/bold yellow]")
        console.print("[dim]Note: Chrome usually runs silently in the background (system tray). Playwright will FREEZE if Chrome is still running![/dim]")
        
        kill_chrome = Prompt.ask("Do you want me to automatically force-kill background Chrome processes to prevent freezing?", choices=["y", "n"], default="y").lower() == "y"
        if kill_chrome:
            import platform
            sys_os = platform.system()
            if sys_os == "Windows":
                os.system("taskkill /im chrome.exe /f >nul 2>&1")
            else:
                os.system("pkill -f 'Google Chrome' > /dev/null 2>&1")
            console.print("[green]Chrome processes terminated.[/green]")
        else:
            Prompt.ask("Press Enter when Chrome is fully closed (including system tray) to continue")
            
        downloader = GoogleDriveDownloader(selected_gdrive_profile)
        for g_url, (g_dir, g_title) in scraper.gdrive_links.items():
            success = downloader.download_pdf(g_url, g_dir, g_title)
            if not success:
                # If Playwright fails (e.g., login required or not an image PDF), fallback to CSV
                save_link_to_csv(g_dir, g_title, g_url)
                
        downloader.close_browser()
    elif not use_gdrive and scraper.gdrive_links:
        # User opted out, just save links directly
        for g_url, (g_dir, g_title) in scraper.gdrive_links.items():
            save_link_to_csv(g_dir, g_title, g_url)
            
    console.print("\n[bold green]Scraping completed! Files are in the 'downloads' directory.[/bold green]")

if __name__ == "__main__":
    main()
