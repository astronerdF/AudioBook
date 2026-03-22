"""
Telegram Bot for AudioBook generation.

Commands:
  /start           - Welcome message with VPN reminder + auto-health-check
  /search <query>  - Search libgen for EPUB books, shows numbered results
  /cancel          - Cancel current search session
  /status          - Check health of backend server + bot uptime
  /startserver     - Manually start the audiobook backend
  /stopserver      - Manually stop the audiobook backend
  <number>         - Select a book from search results to download & generate
  <epub upload>    - Direct EPUB upload triggers generation
"""

import os
import re
import sys
import time
import signal
import subprocess
import requests
import threading
import uuid
import json
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────

env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
TOKEN = None
ABS_API_KEY = None
if os.path.exists(env_file):
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "TELEGRAM_BOT_API" in line or "TELEGRAM_BOT API" in line:
                TOKEN = line.split("=", 1)[1].strip()
            elif "AUDIOBOOK_API" in line or "AUDIOBOOK API" in line:
                ABS_API_KEY = line.split("=", 1)[1].strip()

if not TOKEN:
    print("Error: No Telegram API token found in apps/.env")
    exit(1)

if not ABS_API_KEY:
    print("Warning: No Audiobookshelf API key found in apps/.env. Auto-scan disabled.")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TOKEN}"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
BOOKS_DIR = os.path.join(PROJECT_ROOT, "data", "books")
LOGS_DIR = os.path.join(PROJECT_ROOT, "data", "logs")
os.makedirs(BOOKS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# The epub service port — use 8001 since 8000 is taken by manager.py
EPUB_SERVICE_PORT = int(os.environ.get("EPUB_SERVICE_PORT", "8001"))
BACKEND_URL = f"http://localhost:{EPUB_SERVICE_PORT}/api/audiobooks"
TASKS_URL = f"http://localhost:{EPUB_SERVICE_PORT}/api/tasks"
BACKEND_HEALTH_URL = f"http://localhost:{EPUB_SERVICE_PORT}/api/books"

# Audiobookshelf config
ABS_PORT = int(os.environ.get("ABS_PORT", "3333"))
ABS_BASE_URL = f"http://localhost:{ABS_PORT}"

PYTHON_BIN = os.environ.get(
    "AUDIOBOOK_PYTHON",
    "/lhome/ahmadfn/.pyenv/versions/3.11.9/envs/Audio/bin/python",
)
EPUB_APP_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "epubToAudioBook")

# Libgen mirrors (from the libgen-downloader config.v3.json)
LIBGEN_MIRRORS = ["libgen.li", "libgen.vg", "libgen.gl"]

# Book categories
CATEGORIES = {
    "F": "FICTION",
    "N": "NONFICTION",
    "T": "TEXTBOOKS",
}
GENERATED_DIR = os.path.join(PROJECT_ROOT, "data", "generated")
for cat_dir in CATEGORIES.values():
    os.makedirs(os.path.join(GENERATED_DIR, cat_dir), exist_ok=True)

# Per-chat session state
# Each entry can be:
#   {"mode": "search", "results": [...]}           — waiting for book number
#   {"mode": "category", "epub_path": ..., "name": ...} — waiting for F/N/T
chat_sessions = {}

# Track the backend process we spawned (if any)
_backend_proc = None
_backend_lock = threading.Lock()

# Bot start time for uptime reporting
BOT_START_TIME = datetime.now()


# ──────────────────────────────────────────────
# Backend server management
# ──────────────────────────────────────────────

def is_backend_alive():
    """Check if the audiobook generation backend is running and healthy."""
    try:
        r = requests.get(BACKEND_HEALTH_URL, timeout=3)
        # The /api/books endpoint returns a list (even if empty) when the
        # audiobook FastAPI server is the one on this port.
        return r.status_code == 200
    except Exception:
        return False


def start_backend_server():
    """Start the audiobook FastAPI backend on EPUB_SERVICE_PORT.
    
    Returns (success: bool, message: str).
    """
    global _backend_proc
    with _backend_lock:
        # Already running?
        if _backend_proc and _backend_proc.poll() is None:
            if is_backend_alive():
                return True, "Backend is already running."
            else:
                # Process exists but not healthy — kill and restart
                _backend_proc.terminate()
                _backend_proc.wait(timeout=5)

        # Check if something else already answers on that port
        if is_backend_alive():
            return True, "Backend is already running (externally managed)."

        # Start the server
        env = os.environ.copy()
        env["ABS_WORKSPACE_ROOT"] = PROJECT_ROOT
        env["ABS_DATA_DIR"] = os.path.join(PROJECT_ROOT, "data")
        env["ABS_BOOKS_DIR"] = BOOKS_DIR
        env["ABS_OUTPUT_DIR"] = os.path.join(PROJECT_ROOT, "data", "generated")
        env["ABS_GENERATOR_LOG_DIR"] = os.path.join(LOGS_DIR, "generator")

        log_file = os.path.join(LOGS_DIR, "epub_backend.log")

        try:
            with open(log_file, "a") as lf:
                _backend_proc = subprocess.Popen(
                    [
                        PYTHON_BIN, "-m", "uvicorn",
                        "app.backend.main:app",
                        "--host", "0.0.0.0",
                        "--port", str(EPUB_SERVICE_PORT),
                    ],
                    cwd=EPUB_APP_DIR,
                    env=env,
                    stdout=lf,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,  # Survives if bot restarts
                )
        except Exception as e:
            return False, f"Failed to start backend: {e}"

        # Wait a few seconds for it to come up
        for _ in range(10):
            time.sleep(1)
            if is_backend_alive():
                return True, f"Backend started on port {EPUB_SERVICE_PORT}."

        return False, (
            f"Backend process started (PID {_backend_proc.pid}) but is not "
            f"responding yet. Check logs: data/logs/epub_backend.log"
        )


def stop_backend_server():
    """Stop the backend server if we started it."""
    global _backend_proc
    with _backend_lock:
        if _backend_proc and _backend_proc.poll() is None:
            _backend_proc.terminate()
            try:
                _backend_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                _backend_proc.kill()
            _backend_proc = None
            return True, "Backend stopped."
        return False, "No backend process is being managed by this bot."


def ensure_backend(chat_id):
    """Check backend health. If down, try to auto-start it.
    
    Returns True if backend is alive after the check.
    """
    if is_backend_alive():
        return True

    send_message(chat_id, "⚙️ Backend is down. Attempting to auto-start...")
    ok, msg = start_backend_server()
    send_message(chat_id, f"{'✅' if ok else '⚠️'} {msg}")
    return ok


def get_status_text():
    """Build a status report string."""
    uptime = datetime.now() - BOT_START_TIME
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)

    lines = [
        "📊 System Status\n",
        f"🤖 Bot: Running (uptime: {hours}h {minutes}m {seconds}s)",
    ]

    # Backend
    if is_backend_alive():
        lines.append(f"🟢 Backend: Running on port {EPUB_SERVICE_PORT}")
    else:
        lines.append(f"🔴 Backend: DOWN (port {EPUB_SERVICE_PORT})")

    # Backend process
    global _backend_proc
    if _backend_proc and _backend_proc.poll() is None:
        lines.append(f"   └─ Managed PID: {_backend_proc.pid}")
    elif _backend_proc:
        lines.append(f"   └─ Last exit code: {_backend_proc.returncode}")

    # Disk
    try:
        gen_dir = os.path.join(PROJECT_ROOT, "data", "generated")
        if os.path.isdir(gen_dir):
            n_books = len([d for d in os.listdir(gen_dir)
                          if os.path.isdir(os.path.join(gen_dir, d))])
            lines.append(f"📚 Generated books: {n_books}")
    except Exception:
        pass

    lines.append(f"\n💻 Manual commands (on server):")
    lines.append(f"  Check health:")
    lines.append(f"    curl http://localhost:{EPUB_SERVICE_PORT}/api/books")
    lines.append(f"  Start server:")
    lines.append(f"    PORT={EPUB_SERVICE_PORT} ./scripts/start_epub_service.sh")
    lines.append(f"  View logs:")
    lines.append(f"    tail -f data/logs/epub_backend.log")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Telegram helpers
# ──────────────────────────────────────────────

def send_message(chat_id, text, parse_mode=None):
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"[send_message] Error: {e}")


def get_file_path(file_id):
    url = f"{TELEGRAM_API_URL}/getFile"
    try:
        res = requests.get(url, params={"file_id": file_id}, timeout=10).json()
        if res.get("ok"):
            return res["result"]["file_path"]
    except Exception as e:
        print(f"[get_file_path] Error: {e}")
    return None


def download_from_telegram(file_path, dest_path):
    url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
    try:
        res = requests.get(url, stream=True, timeout=30)
        res.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in res.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"[download_from_telegram] Error: {e}")
        return False


# ──────────────────────────────────────────────
# Libgen search & download
# ──────────────────────────────────────────────

def search_libgen(query, max_results=10):
    """Search libgen for EPUB books. Returns list of dicts."""
    for domain in LIBGEN_MIRRORS:
        url = f"https://{domain}/index.php?req={urllib.parse.quote(query)}&page=1&res=25"
        try:
            r = requests.get(url, timeout=15)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")

            table = soup.find("table", id="tablelibgen")
            if not table:
                continue
            tbody = table.find("tbody")
            if not tbody:
                continue

            books = []
            rows = tbody.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) < 9:
                    continue

                extension = cols[7].text.strip().lower()
                if extension != "epub":
                    continue

                author = cols[1].text.strip().replace(";", ",")
                if len(author) > 60:
                    author = author[:57] + "..."

                title_el = cols[0]
                for nobr in title_el.find_all("nobr"):
                    nobr.decompose()
                title = title_el.get_text(separator=" ", strip=True)
                title = re.sub(r"\s+\d{5,}$", "", title)
                if not title:
                    title = "Untitled"
                if len(title) > 80:
                    title = title[:77] + "..."

                size = cols[6].text.strip()
                language = cols[4].text.strip()
                year = cols[3].text.strip()

                mirror_tag = cols[8].find("a")
                if not mirror_tag:
                    continue
                mirror = mirror_tag["href"]
                if not mirror.startswith("http"):
                    mirror = f"https://{domain}/{mirror.lstrip('/')}"

                books.append({
                    "title": title,
                    "author": author,
                    "extension": extension,
                    "size": size,
                    "language": language,
                    "year": year,
                    "mirror_link": mirror,
                    "domain": domain,
                })
                if len(books) >= max_results:
                    break

            return books
        except Exception as e:
            print(f"[search_libgen] Error with {domain}: {e}")
            continue
    return []


def get_direct_download_url(mirror_url, domain):
    """Resolve the mirror page to an actual file download URL."""
    try:
        r = requests.get(mirror_url, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")

        dl = soup.select_one("#main > tbody > tr:nth-child(1) > td:nth-child(2) > a")
        if not dl:
            dl = soup.select_one("#main > tr:nth-child(1) > td:nth-child(2) > a")
        if dl:
            href = dl.get("href", "")
            if href and not href.startswith("http"):
                href = f"https://{domain}/{href.lstrip('/')}"
            return href

        for a in soup.find_all("a"):
            href = a.get("href", "")
            if "get.php" in href:
                if not href.startswith("http"):
                    href = f"https://{domain}/{href.lstrip('/')}"
                return href
    except Exception as e:
        print(f"[get_direct_download_url] Error: {e}")
    return None


def download_from_libgen(download_url, dest_path):
    """Download the actual EPUB file from libgen."""
    try:
        r = requests.get(download_url, stream=True, timeout=60,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"[download_from_libgen] Error: {e}")
        return False


# ──────────────────────────────────────────────
# Backend interaction
# ──────────────────────────────────────────────

def check_task_status(job_id):
    try:
        res = requests.get(f"{TASKS_URL}/{job_id}", timeout=10).json()
        return res.get("status", "unknown")
    except Exception as e:
        print(f"[check_task_status] Error: {e}")
        return "unknown"


def submit_epub_to_backend(epub_path, file_name):
    """POST the EPUB to the FastAPI backend. Returns (job_id, book_id) or None."""
    try:
        with open(epub_path, "rb") as f:
            files = {"file": (file_name, f, "application/epub+zip")}
            data = {
                "voice": "af_heart",
                "device": "cuda",
                "chapter_start": "1",
                "chapter_end": "-1",
            }
            res = requests.post(BACKEND_URL, files=files, data=data, timeout=30)
        if res.status_code == 202:
            d = res.json()
            return d["job_id"], d["book_id"]
        else:
            print(f"[submit_epub_to_backend] Backend returned {res.status_code}: {res.text}")
    except Exception as e:
        print(f"[submit_epub_to_backend] Error: {e}")
    return None


def trigger_audiobookshelf_scan():
    """Trigger a library scan on ALL Audiobookshelf libraries."""
    if not ABS_API_KEY:
        print("[abs_scan] No API key, skipping scan.")
        return False

    headers = {"Authorization": f"Bearer {ABS_API_KEY}"}
    try:
        r = requests.get(f"{ABS_BASE_URL}/api/libraries", headers=headers, timeout=5)
        if r.status_code != 200:
            print(f"[abs_scan] Failed to list libraries: {r.status_code}")
            return False

        libraries = r.json().get("libraries", [])
        scanned = 0
        for lib in libraries:
            # Scan any library whose folder is inside data/generated/
            for folder in lib.get("folders", []):
                if GENERATED_DIR in folder.get("fullPath", ""):
                    resp = requests.post(
                        f"{ABS_BASE_URL}/api/libraries/{lib['id']}/scan",
                        headers=headers, timeout=10,
                    )
                    print(f"[abs_scan] Scanned '{lib['name']}': {resp.status_code}")
                    scanned += 1
                    break

        if scanned == 0:
            # Fallback: scan all
            for lib in libraries:
                requests.post(
                    f"{ABS_BASE_URL}/api/libraries/{lib['id']}/scan",
                    headers=headers, timeout=10,
                )
            print("[abs_scan] No matching libraries, scanned all.")

        return True
    except Exception as e:
        print(f"[abs_scan] Error: {e}")
        return False


def move_book_to_category(book_id, category_key):
    """Move a generated book folder into the correct category subfolder."""
    cat_name = CATEGORIES.get(category_key.upper())
    if not cat_name:
        return False, f"Unknown category: {category_key}"

    src = os.path.join(GENERATED_DIR, book_id)
    if not os.path.isdir(src):
        return False, f"Book folder not found: {book_id}"

    dest = os.path.join(GENERATED_DIR, cat_name, book_id)
    if os.path.exists(dest):
        return False, f"Destination already exists: {cat_name}/{book_id}"

    try:
        import shutil
        shutil.move(src, dest)
        return True, f"Moved to {cat_name}/{book_id}"
    except Exception as e:
        return False, str(e)


def poll_and_notify(chat_id, job_id, book_id, display_name, category_key=None):
    """Poll the backend until generation completes, then notify user."""
    while True:
        time.sleep(15)
        status = check_task_status(job_id)
        if status == "completed":
            # Move to category folder if specified
            move_msg = ""
            if category_key:
                ok, msg = move_book_to_category(book_id, category_key)
                cat_name = CATEGORIES.get(category_key.upper(), "?")
                if ok:
                    move_msg = f"\n📂 Filed under: {cat_name}"
                else:
                    move_msg = f"\n⚠️ Could not move to {cat_name}: {msg}"

            # Trigger Audiobookshelf scan
            scan_ok = trigger_audiobookshelf_scan()
            scan_msg = "\n📱 Library scan triggered — it should appear in the app shortly!" if scan_ok else ""

            send_message(
                chat_id,
                f"🎉 Generation complete for '{display_name}'!\n"
                f"📖 Book ID: {book_id}{move_msg}{scan_msg}",
            )
            break
        elif status in ("failed",):
            send_message(chat_id, f"⚠️ Generation failed for '{display_name}'.")
            break


# ──────────────────────────────────────────────
# High-level handlers
# ──────────────────────────────────────────────

def handle_document_upload(chat_id, document):
    """Handle a direct EPUB upload from the user."""
    file_name = document.get("file_name", "book.epub")
    file_id = document.get("file_id")
    mime = document.get("mime_type", "")

    if not (file_name.lower().endswith(".epub") or "epub" in mime):
        send_message(chat_id, "⚠️ Please upload an EPUB file. Other formats aren't supported yet.")
        return

    send_message(chat_id, f"📥 Downloading '{file_name}' from Telegram...")

    tg_path = get_file_path(file_id)
    if not tg_path:
        send_message(chat_id, "❌ Failed to retrieve file from Telegram.")
        return

    local_path = os.path.join(BOOKS_DIR, f"{uuid.uuid4()}_{file_name}")
    if not download_from_telegram(tg_path, local_path):
        send_message(chat_id, "❌ Failed to download from Telegram.")
        return

    send_message(
        chat_id,
        f"✅ Got it!\n\n"
        f"📂 Which category?\n"
        f"  F — Fiction\n"
        f"  N — Nonfiction\n"
        f"  T — Textbooks\n\n"
        f"Reply with F, N, or T.",
    )
    chat_sessions[chat_id] = {
        "mode": "category",
        "epub_path": local_path,
        "name": file_name,
    }


def handle_libgen_selection(chat_id, choice_num):
    """User picked a number from search results. Download from libgen & generate."""
    session = chat_sessions.get(chat_id, {})
    results = session.get("results") if session.get("mode") == "search" else None
    if not results:
        send_message(chat_id, "No active search. Use /search <query> first.")
        return

    if choice_num < 1 or choice_num > len(results):
        send_message(chat_id, f"Invalid choice. Please pick a number between 1 and {len(results)}.")
        return

    book = results[choice_num - 1]
    title = book["title"]
    domain = book["domain"]
    mirror = book["mirror_link"]

    send_message(chat_id, f"📖 You selected: {title}\n\n⏳ Resolving download link...")

    direct_url = get_direct_download_url(mirror, domain)
    if not direct_url:
        send_message(chat_id, "❌ Could not resolve a download link. The mirror may be down. Try /search again.")
        return

    safe_title = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")[:60]
    file_name = f"{safe_title}.epub"
    local_path = os.path.join(BOOKS_DIR, f"{uuid.uuid4()}_{file_name}")

    send_message(chat_id, f"📥 Downloading '{title}' from libgen ({book['size']})...")

    if not download_from_libgen(direct_url, local_path):
        send_message(chat_id, "❌ Download from libgen failed. The file may be unavailable.")
        return

    fsize = os.path.getsize(local_path)
    if fsize < 1024:
        send_message(chat_id, "❌ Downloaded file is suspiciously small. It may not be a valid EPUB.")
        os.remove(local_path)
        return

    send_message(
        chat_id,
        f"✅ Downloaded! ({fsize // 1024} KB)\n\n"
        f"📂 Which category?\n"
        f"  F — Fiction\n"
        f"  N — Nonfiction\n"
        f"  T — Textbooks\n\n"
        f"Reply with F, N, or T.",
    )
    chat_sessions[chat_id] = {
        "mode": "category",
        "epub_path": local_path,
        "name": file_name,
    }


def handle_category_selection(chat_id, category_key):
    """User replied F/N/T after downloading a book. Submit to backend with category."""
    session = chat_sessions.get(chat_id, {})
    if session.get("mode") != "category":
        return

    epub_path = session["epub_path"]
    display_name = session["name"]
    chat_sessions.pop(chat_id, None)

    cat_name = CATEGORIES.get(category_key.upper(), "NONFICTION")
    send_message(chat_id, f"📂 Category: {cat_name}\n⚙️ Submitting to audiobook generator...")

    _submit_and_track(chat_id, epub_path, display_name, category_key)


def _submit_and_track(chat_id, epub_path, display_name, category_key=None):
    """Submit an EPUB to the backend and start polling in background.
    
    Auto-starts the backend if it's down.
    """
    # Try to ensure backend is running
    if not is_backend_alive():
        send_message(chat_id, "⚙️ Backend is not running. Starting it automatically...")
        ok, msg = start_backend_server()
        if not ok:
            import shutil
            final_path = os.path.join(BOOKS_DIR, os.path.basename(epub_path))
            if epub_path != final_path and not os.path.exists(final_path):
                try:
                    shutil.copy2(epub_path, final_path)
                except Exception:
                    pass
            send_message(
                chat_id,
                f"⚠️ Could not start the backend: {msg}\n\n"
                f"📁 EPUB saved to: data/books/{os.path.basename(epub_path)}\n\n"
                f"Manual start on server:\n"
                f"  PORT={EPUB_SERVICE_PORT} ./scripts/start_epub_service.sh",
            )
            return
        send_message(chat_id, f"✅ {msg}")

    result = submit_epub_to_backend(epub_path, display_name)
    if not result:
        send_message(
            chat_id,
            "❌ Backend rejected the file. Check logs:\n"
            "  tail -f data/logs/epub_backend.log",
        )
        return

    job_id, book_id = result
    send_message(
        chat_id,
        f"🚀 Generation started for '{display_name}'\n"
        f"Job: {job_id[:8]}…  |  Book ID: {book_id}\n\n"
        f"This takes roughly 5–15 minutes depending on book length. "
        f"I'll message you when it's done!",
    )
    t = threading.Thread(
        target=poll_and_notify,
        args=(chat_id, job_id, book_id, display_name, category_key),
        daemon=True,
    )
    t.start()


def handle_search(chat_id, query):
    """Search libgen and present numbered results."""
    if not query.strip():
        send_message(chat_id, "Usage: /search <book title or author>\nExample: /search sapiens")
        return

    send_message(chat_id, f"🔍 Searching libgen for EPUB files matching: '{query}'...")

    results = search_libgen(query, max_results=10)
    if not results:
        send_message(chat_id, "😕 No EPUB results found. Try a different query or check your VPN.")
        return

    chat_sessions[chat_id] = {"mode": "search", "results": results}

    lines = [f"📚 Found {len(results)} EPUB result(s):\n"]
    for i, b in enumerate(results, 1):
        lang = f" [{b['language']}]" if b.get("language") else ""
        year = f" ({b['year']})" if b.get("year") else ""
        lines.append(f"{i}. {b['title']}{year}{lang}")
        lines.append(f"   ✍️ {b['author']}  |  📦 {b['size']}")
        lines.append("")

    lines.append("Reply with the number to download & generate.")
    lines.append("Or /cancel to clear results.")

    send_message(chat_id, "\n".join(lines))


# ──────────────────────────────────────────────
# Polling loop
# ──────────────────────────────────────────────

def get_updates(offset=None):
    url = f"{TELEGRAM_API_URL}/getUpdates"
    params = {"timeout": 30, "allowed_updates": ["message"]}
    if offset:
        params["offset"] = offset
    try:
        res = requests.get(url, params=params, timeout=40)
        return res.json()
    except Exception:
        pass
    return {}


def main():
    print(f"🤖 Telegram AudioBook Bot started. Polling for updates...")
    print(f"   Backend target: localhost:{EPUB_SERVICE_PORT}")
    offset = None
    while True:
        updates = get_updates(offset)
        if not updates or not updates.get("ok"):
            time.sleep(1)
            continue

        for update in updates.get("result", []):
            offset = update["update_id"] + 1
            message = update.get("message", {})
            chat_id = message.get("chat", {}).get("id")
            if not chat_id:
                continue

            text = (message.get("text") or "").strip()
            document = message.get("document")

            # ── Commands ──
            if text == "/start":
                # Auto-check backend health on /start
                backend_ok = is_backend_alive()
                backend_status = "🟢 Running" if backend_ok else "🔴 Down"

                send_message(
                    chat_id,
                    f"👋 Welcome to the AudioBook Bot!\n\n"
                    f"❗ Reminder: Make sure the Uni VPN is active.\n\n"
                    f"Server status: {backend_status}\n\n"
                    f"Commands:\n"
                    f"• /search <title> — Search & download EPUBs from libgen\n"
                    f"• /status — Check server health\n"
                    f"• /startserver — Start the generation backend\n"
                    f"• /stopserver — Stop the generation backend\n"
                    f"• Upload an EPUB file directly\n\n"
                    f"Each book gets its own folder and appears in Audiobookshelf automatically.",
                )

                # If backend is down, try to auto-start
                if not backend_ok:
                    send_message(chat_id, "⚙️ Backend is down. Attempting auto-start...")
                    ok, msg = start_backend_server()
                    send_message(chat_id, f"{'✅' if ok else '⚠️'} {msg}")

            elif text == "/status":
                send_message(chat_id, get_status_text())

            elif text == "/startserver":
                send_message(chat_id, "⚙️ Starting audiobook backend...")
                ok, msg = start_backend_server()
                send_message(chat_id, f"{'✅' if ok else '⚠️'} {msg}")

            elif text == "/stopserver":
                ok, msg = stop_backend_server()
                send_message(chat_id, f"{'✅' if ok else 'ℹ️'} {msg}")

            elif text == "/cancel":
                chat_sessions.pop(chat_id, None)
                send_message(chat_id, "🗑️ Search results cleared.")

            elif text.startswith("/search"):
                query = text[len("/search"):].strip()
                t = threading.Thread(target=handle_search, args=(chat_id, query), daemon=True)
                t.start()

            elif document:
                t = threading.Thread(target=handle_document_upload, args=(chat_id, document), daemon=True)
                t.start()

            elif text.upper() in CATEGORIES and chat_id in chat_sessions and chat_sessions[chat_id].get("mode") == "category":
                t = threading.Thread(target=handle_category_selection, args=(chat_id, text.upper()), daemon=True)
                t.start()

            elif text.isdigit() and chat_id in chat_sessions and chat_sessions[chat_id].get("mode") == "search":
                choice = int(text)
                t = threading.Thread(target=handle_libgen_selection, args=(chat_id, choice), daemon=True)
                t.start()

            elif text:
                msg = (
                    "🛡️ Did you start the Uni VPN?\n\n"
                    "• /search <title> — Search for books on libgen\n"
                    "• /status — Check server health\n"
                    "• /startserver — Start generation backend\n"
                    "• Upload an EPUB file directly\n"
                    "• /cancel — Clear current search results"
                )
                send_message(chat_id, msg)

        time.sleep(1)


if __name__ == "__main__":
    main()
