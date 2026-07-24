# -*- coding: utf-8 -*-
# main_multiple.py
#
# Forum Image Downloader mit PyQt6-GUI
# - Start/Stopp als Toggle-Button
# - Mehrere Downloads nacheinander
# - Statusanzeige für alle Phasen (Login, URL-Suche, URL-Auflösung, Download)
# - Ein eigener Fortschrittsbalken pro parallelem Download-Slot

from __future__ import annotations

import asyncio
import os
import queue
import random
import re
import sys
import threading
from pathlib import Path
from typing import Callable, List, Optional
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
import requests
from bs4 import BeautifulSoup, Tag
from skimage import io as skio
from tenacity import retry, stop_after_attempt, wait_fixed

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QTabWidget, QLabel, QLineEdit, QPushButton,
    QCheckBox, QProgressBar, QPlainTextEdit,
    QGroupBox, QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QIcon, QPalette, QColor, QTextCursor, QCloseEvent

from providers.providers import (
    get_real_imagebam_url,
    get_real_imgbox_url,
    get_real_pixhost_url,
    get_real_postimg_url,
    get_real_turboimagehost_url,
)

from SplashScreenPython.splash_video_webP import SplashScreen

# ----------------------------------------------------------------------
# Konfiguration
# ----------------------------------------------------------------------

from build_version import BUILD_INFO, VERSION, BUILD_TIME, APP_NAME

DEFAULT_FORUM_URL = "https://picturepub.net/"
DEFAULT_IMAGENAME = "AOLBuildinNYC_22Aug2o16"
DEFAULT_PROXY_URL = "socks5h://127.0.0.1:9150"
IMG_DL_PATH = r"Z:\Downloads"
NBR_PARALLEL_DL = 5
USE_LOGIN = True

try:
    from credentials import PASSWORD, USERNAME
except ImportError:
    USERNAME = ""
    PASSWORD = ""

HOST_FUNCTIONS = {
    "imagebam.com": get_real_imagebam_url,
    "pixhost.to": get_real_pixhost_url,
    "pixhost.cc": get_real_pixhost_url,
    "postimg.cc": get_real_postimg_url,
    "imgbox.com": get_real_imgbox_url,
    "turboimagehost.com": get_real_turboimagehost_url,
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:101.0) Gecko/20100101 Firefox/101.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 12_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
    "Mozilla/5.0 (Linux; Android 11; SM-G960U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.72 Mobile Safari/537.36",
]


def build_headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.google.com",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "TE": "trailers",
    }


# ----------------------------------------------------------------------
# Helfer
# ----------------------------------------------------------------------

LogFn = Callable[..., None]


def is_valid_href(href: str) -> bool:
    if not href:
        return False
    href = href.strip().lower()
    if href.startswith(("[", "#", "javascript:", "mailto:", ":")):
        return False
    return True


def base_url_of(url: str) -> str:
    return "/".join(url.split("/")[:3])


def verify_image(img_file: str) -> bool:
    try:
        skio.imread(img_file)
        return True
    except Exception:
        return False


def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip() or "download"


# ----------------------------------------------------------------------
# Forum-Zugriff
# ----------------------------------------------------------------------

def login(
    base_url: str,
    username: str,
    password: str,
    log: LogFn = print,
    proxies: Optional[dict] = None,
) -> Optional[requests.Session]:
    login_url = f"{base_url}/login/login"
    session = requests.Session()
    session.headers.update(build_headers())
    if proxies:
        session.proxies.update(proxies)

    try:
        response = session.get(login_url, timeout=30)
    except requests.RequestException as e:
        log(f"Login-Seite nicht erreichbar: {e}")
        return None

    if response.status_code != 200:
        log(f"Login-Seite lieferte Status {response.status_code}.")
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    csrf_token_tag = (
        soup.find("input", {"name": "_xfToken"})
        or soup.find("input", {"id": "csrf_token"})
    )
    if not csrf_token_tag or "value" not in csrf_token_tag.attrs:
        log("CSRF-Token nicht gefunden.")
        return None

    payload = {
        "login": username,
        "register": "0",
        "password": password,
        "remember": 1,
        "cookie_check": 1,
        "redirect": "/",
        "_xfToken": csrf_token_tag["value"],
    }

    try:
        response = session.post(login_url, data=payload, timeout=30)
    except requests.RequestException as e:
        log(f"Login-Request fehlgeschlagen: {e}")
        return None

    if response.status_code != 200:
        log(f"Login fehlgeschlagen (Status {response.status_code}).")
        return None

    log("Login erfolgreich.")
    return session


def make_anonymous_session(proxies: Optional[dict] = None) -> requests.Session:
    s = requests.Session()
    s.headers.update(build_headers())
    if proxies:
        s.proxies.update(proxies)
    return s


def _collect_links_from_page(
    soup: BeautifulSoup,
    page_url: str,
) -> tuple[List[str], int, int]:
    container = soup.find("div", class_="block-body js-replyNewMessageContainer")
    if not isinstance(container, Tag):
        return [], 0, 0

    links: List[str] = []
    skipped = 0
    invalid = 0
    for a in container.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not is_valid_href(href):
            skipped += 1
            continue
        try:
            image_url = urljoin(page_url, href)
        except ValueError:
            invalid += 1
            continue
        if any(host in image_url for host in HOST_FUNCTIONS) and "gallery" not in image_url:
            links.append(image_url)
    return links, skipped, invalid


def _get_all_page_urls(soup: BeautifulSoup, first_url: str) -> List[str]:
    page_urls = [first_url]
    nav = soup.find("div", class_="pageNav")
    if not isinstance(nav, Tag):
        return page_urls
    for a in nav.select("ul.pageNav-main li.pageNav-page a"):
        href = a.get("href", "").strip()
        if not href:
            continue
        url = urljoin(first_url, href)
        if url not in page_urls:
            page_urls.append(url)
    return page_urls


def find_posted_pictures(
    session: requests.Session, forum_url: str, log: LogFn = print
) -> List[str]:
    log(f"Suche Bilder auf: {forum_url}")
    try:
        response = session.get(forum_url, timeout=30)
    except requests.RequestException as e:
        log(f"Forum-Seite nicht erreichbar: {e}")
        return []

    if response.status_code != 200:
        log(f"Forum-Seite lieferte Status {response.status_code}.")
        return []

    first_soup = BeautifulSoup(response.text, "html.parser")
    page_urls = _get_all_page_urls(first_soup, forum_url)
    if len(page_urls) > 1:
        log(f"{len(page_urls)} Seiten gefunden.")

    image_links: List[str] = []
    total_skipped = 0
    total_invalid = 0

    soups = [(first_soup, forum_url)] + [(None, u) for u in page_urls[1:]]
    for i, (soup, url) in enumerate(soups, 1):
        if len(page_urls) > 1:
            log(f"Durchsuche Seite {i}/{len(page_urls)} …")
        if soup is None:
            try:
                resp = session.get(url, timeout=30)
            except requests.RequestException as e:
                log(f"Seite {i} nicht erreichbar: {e}")
                continue
            if resp.status_code != 200:
                log(f"Seite {i} lieferte Status {resp.status_code}.")
                continue
            soup = BeautifulSoup(resp.text, "html.parser")

        links, skipped, invalid = _collect_links_from_page(soup, url)
        image_links.extend(links)
        total_skipped += skipped
        total_invalid += invalid

    log(f"{len(image_links)} Links gefunden (ignoriert: {total_skipped}, ungültig: {total_invalid}).")
    return image_links


def create_folder_from_forum_title(
    session: requests.Session, forum_url: str, save_path: str, log: LogFn = print
) -> Optional[str]:
    try:
        response = session.get(forum_url, timeout=30)
    except requests.RequestException as e:
        log(f"Titel-Request fehlgeschlagen: {e}")
        return None

    if response.status_code != 200:
        log(f"Titel-Request Status {response.status_code}.")
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    title_tag = soup.find("h1", class_="p-title-value")
    if not title_tag:
        log("Forum-Titel nicht gefunden.")
        return None

    folder_name = sanitize_filename(title_tag.text)
    folder_path = os.path.join(save_path, folder_name)
    try:
        os.makedirs(folder_path, exist_ok=True)
    except OSError as e:
        log(f"Ordner konnte nicht angelegt werden: {e}")
        return None
    log(f"Zielordner: {folder_path}")
    return folder_path


def find_real_image_urls(
    image_urls: List[str],
    cancel_event: threading.Event,
    log: LogFn = print,
    proxies: Optional[dict] = None,
) -> List[str]:
    filelist: List[str] = []
    total = len(image_urls)

    for i, url in enumerate(image_urls, 1):
        if cancel_event.is_set():
            log("Abbruch beim Auflösen der URLs.")
            break
        func = next((f for host, f in HOST_FUNCTIONS.items() if host in url), None)
        if not func:
            log(f"Nicht unterstützter Host: {url}")
            continue
        try:
            real_url = func(url, proxies=proxies)
            if real_url:
                filelist.append(real_url)
        except Exception as e:
            log(f"Fehler bei {url}: {e}")

        log(f"URLs aufgelöst: {i}/{total} (erfolgreich: {len(filelist)})", replace=True)

    log("", finalize_replace=True)
    return filelist


# ----------------------------------------------------------------------
# Download-Worker (async)
# ----------------------------------------------------------------------

class DownloadJob:
    def __init__(self, forum_url: str, image_name: str):
        self.forum_url = forum_url.strip()
        self.image_name = sanitize_filename(image_name)


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def _download_stream(
    client: httpx.AsyncClient,
    url: str,
    target_path: str,
    on_progress: Callable[[int, int], None],
) -> None:
    async with client.stream("GET", url, headers=build_headers()) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        on_progress(0, total)
        with open(target_path, "wb") as f:
            async for chunk in r.aiter_bytes():
                f.write(chunk)
                downloaded += len(chunk)
                on_progress(downloaded, total)


async def download_all(
    urls: List[str],
    dest_folder: str,
    name_prefix: str,
    nbr_parallel: int,
    post_gui: Callable[[tuple], None],
    log: LogFn,
    cancel_event: threading.Event,
    proxy_url: Optional[str] = None,
) -> None:
    slot_pool: asyncio.Queue[int] = asyncio.Queue()
    for s in range(nbr_parallel):
        await slot_pool.put(s)

    total_files = len(urls)
    done_count = 0
    done_lock = asyncio.Lock()

    async with httpx.AsyncClient(timeout=60, follow_redirects=True, proxy=proxy_url) as client:

        async def worker(index: int, url: str) -> None:
            nonlocal done_count
            if cancel_event.is_set():
                return

            slot = await slot_pool.get()
            filename = f"{name_prefix}_{index:03}.jpg"
            target = os.path.join(dest_folder, filename)
            post_gui(("slot_start", slot, filename))

            try:
                if os.path.exists(target):
                    ok = await asyncio.to_thread(verify_image, target)
                    if ok:
                        post_gui(("slot_done", slot, filename, "übersprungen (vorhanden)"))
                        return

                def on_progress(downloaded: int, total: int) -> None:
                    post_gui(("slot_progress", slot, downloaded, total))

                try:
                    await _download_stream(client, url, target, on_progress)
                    post_gui(("slot_done", slot, filename, "ok"))
                except asyncio.CancelledError:
                    try:
                        if os.path.exists(target):
                            os.remove(target)
                    except OSError:
                        pass
                    post_gui(("slot_done", slot, filename, "abgebrochen"))
                    raise
                except Exception as e:
                    log(f"Fehler bei {filename}: {e}")
                    post_gui(("slot_done", slot, filename, "fehler"))
            finally:
                async with done_lock:
                    done_count += 1
                    post_gui(("progress_total", done_count, total_files))
                await slot_pool.put(slot)

        tasks = [
            asyncio.create_task(worker(idx + 1, url))
            for idx, url in enumerate(urls)
        ]

        async def cancel_monitor() -> None:
            while not cancel_event.is_set():
                if all(t.done() for t in tasks):
                    return
                await asyncio.sleep(0.2)
            for t in tasks:
                if not t.done():
                    t.cancel()

        monitor_task = asyncio.create_task(cancel_monitor())
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            monitor_task.cancel()
            try:
                await monitor_task
            except (asyncio.CancelledError, Exception):
                pass


# ----------------------------------------------------------------------
# Dark theme
# ----------------------------------------------------------------------

def _apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    p = QPalette()
    dark     = QColor(30, 30, 30)
    mid_dark = QColor(45, 45, 45)
    fg       = QColor(220, 220, 220)
    disabled = QColor(110, 110, 110)
    accent   = QColor(0, 120, 215)

    p.setColor(QPalette.ColorRole.Window,          dark)
    p.setColor(QPalette.ColorRole.WindowText,      fg)
    p.setColor(QPalette.ColorRole.Base,            mid_dark)
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(55, 55, 55))
    p.setColor(QPalette.ColorRole.ToolTipBase,     mid_dark)
    p.setColor(QPalette.ColorRole.ToolTipText,     fg)
    p.setColor(QPalette.ColorRole.Text,            fg)
    p.setColor(QPalette.ColorRole.Button,          QColor(50, 50, 50))
    p.setColor(QPalette.ColorRole.ButtonText,      fg)
    p.setColor(QPalette.ColorRole.Link,            accent)
    p.setColor(QPalette.ColorRole.Highlight,       accent)
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.Mid,             QColor(80, 80, 80))
    p.setColor(QPalette.ColorRole.Shadow,          QColor(0, 0, 0))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,       disabled)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled)
    app.setPalette(p)


# ----------------------------------------------------------------------
# Button stylesheets
# ----------------------------------------------------------------------

_STYLE_ACCENT = (
    "QPushButton { background-color: #0078d7; color: white; border-radius: 4px;"
    " font-weight: bold; padding: 4px 12px; }"
    "QPushButton:hover { background-color: #1484d9; }"
    "QPushButton:pressed { background-color: #005fa3; }"
    "QPushButton:disabled { background-color: #3a3a3a; color: #666; }"
)
_STYLE_STOP = (
    "QPushButton { background-color: #555; color: #ddd; border-radius: 4px;"
    " padding: 4px 12px; }"
    "QPushButton:hover { background-color: #666; }"
    "QPushButton:disabled { background-color: #3a3a3a; color: #666; }"
)


# ----------------------------------------------------------------------
# GUI
# ----------------------------------------------------------------------

class DownloaderApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.gui_queue: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker_thread: Optional[threading.Thread] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

        self.slot_labels: List[QLabel] = []
        self.slot_bars: List[QProgressBar] = []
        self._pending_replace_line = False

        self._build_ui()

        self._queue_timer = QTimer(self)
        self._queue_timer.setInterval(50)
        self._queue_timer.timeout.connect(self._pump_queue)
        self._queue_timer.start()

    # ---------- UI-Aufbau ----------

    def _build_ui(self) -> None:
        self.setWindowTitle(BUILD_INFO)
        self.resize(900, 760)
        self.setMinimumSize(720, 580)

        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.center().x() - 450, geo.center().y() - 380)

        icon_path = (
            Path(sys._MEIPASS) / "assets/dl_img.ico"  # type: ignore[attr-defined]
            if getattr(sys, "frozen", False)
            else Path("assets/dl_img.ico")
        )
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setSpacing(8)
        root_layout.setContentsMargins(12, 12, 12, 12)

        # ---- Tabs ----
        tabs = QTabWidget()
        root_layout.addWidget(tabs)

        # Tab 1: Download
        tab1 = QWidget()
        tabs.addTab(tab1, "Download")
        g = QGridLayout(tab1)
        g.setContentsMargins(12, 12, 12, 12)
        g.setColumnStretch(1, 1)

        g.addWidget(QLabel("Forum URL:"), 0, 0, Qt.AlignmentFlag.AlignLeft)
        self.entry_url = QLineEdit(DEFAULT_FORUM_URL)
        self.entry_url.setFont(QFont("Segoe UI", 12))
        g.addWidget(self.entry_url, 0, 1)

        g.addWidget(QLabel("Bildname:"), 1, 0, Qt.AlignmentFlag.AlignLeft)
        self.entry_name = QLineEdit(DEFAULT_IMAGENAME)
        self.entry_name.setFont(QFont("Segoe UI", 12))
        self.entry_name.textChanged.connect(self._strip_whitespace_image_name)
        g.addWidget(self.entry_name, 1, 1)

        self.chk_login = QCheckBox("Login verwenden")
        self.chk_login.setChecked(USE_LOGIN)
        g.addWidget(self.chk_login, 2, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)

        btn_container = QWidget()
        btn_row = QHBoxLayout(btn_container)
        btn_row.setContentsMargins(0, 6, 0, 0)
        btn_row.setSpacing(12)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.start_button = QPushButton("Start")
        self.start_button.setFixedSize(160, 36)
        self.start_button.setFont(QFont("Segoe UI", 10))
        self.start_button.setStyleSheet(_STYLE_ACCENT)
        self.start_button.clicked.connect(self.on_start_or_stop)
        btn_row.addWidget(self.start_button)

        self.info_button = QPushButton("ℹ")
        self.info_button.setFixedSize(40, 36)
        self.info_button.setFont(QFont("Segoe UI", 14))
        self.info_button.setToolTip("Info / About")
        self.info_button.clicked.connect(self._show_splash)
        btn_row.addWidget(self.info_button)

        self.quit_button = QPushButton("Beenden")
        self.quit_button.setFixedSize(160, 36)
        self.quit_button.setFont(QFont("Segoe UI", 10))
        self.quit_button.clicked.connect(self.on_close)
        btn_row.addWidget(self.quit_button)

        g.addWidget(btn_container, 3, 0, 1, 2)

        # Tab 2: Proxy
        tab2 = QWidget()
        tabs.addTab(tab2, "Proxy")
        g2 = QGridLayout(tab2)
        g2.setContentsMargins(12, 12, 12, 12)
        g2.setColumnStretch(1, 1)

        self.chk_proxy = QCheckBox("Proxy verwenden")
        self.chk_proxy.setChecked(False)
        self.chk_proxy.stateChanged.connect(self._on_proxy_toggle)
        g2.addWidget(self.chk_proxy, 0, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)

        g2.addWidget(QLabel("Proxy URL:"), 1, 0, Qt.AlignmentFlag.AlignLeft)
        self.entry_proxy_url = QLineEdit(DEFAULT_PROXY_URL)
        self.entry_proxy_url.setFont(QFont("Segoe UI", 12))
        g2.addWidget(self.entry_proxy_url, 1, 1)

        g2.addWidget(QLabel("Benutzername:"), 2, 0, Qt.AlignmentFlag.AlignLeft)
        self.entry_proxy_user = QLineEdit()
        self.entry_proxy_user.setFont(QFont("Segoe UI", 12))
        g2.addWidget(self.entry_proxy_user, 2, 1)

        g2.addWidget(QLabel("Passwort:"), 3, 0, Qt.AlignmentFlag.AlignLeft)
        self.entry_proxy_pass = QLineEdit()
        self.entry_proxy_pass.setFont(QFont("Segoe UI", 12))
        self.entry_proxy_pass.setEchoMode(QLineEdit.EchoMode.Password)
        g2.addWidget(self.entry_proxy_pass, 3, 1)

        self._on_proxy_toggle()

        # ---- Gesamtfortschritt ----
        grp_total = QGroupBox("Gesamtfortschritt")
        lay_total = QVBoxLayout(grp_total)
        lay_total.setSpacing(4)
        self.total_label = QLabel("bereit.")
        lay_total.addWidget(self.total_label)
        self.total_bar = QProgressBar()
        self.total_bar.setRange(0, 100)
        self.total_bar.setValue(0)
        lay_total.addWidget(self.total_bar)
        root_layout.addWidget(grp_total)

        # ---- Slot-Fortschritte ----
        grp_slots = QGroupBox(f"Aktive Downloads ({NBR_PARALLEL_DL} parallel)")
        lay_slots = QVBoxLayout(grp_slots)
        lay_slots.setSpacing(4)
        for i in range(NBR_PARALLEL_DL):
            lbl = QLabel(f"[Slot {i + 1}] idle")
            lbl.setFont(QFont("Segoe UI", 9))
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setFixedHeight(14)
            lay_slots.addWidget(lbl)
            lay_slots.addWidget(bar)
            self.slot_labels.append(lbl)
            self.slot_bars.append(bar)
        root_layout.addWidget(grp_slots)

        # ---- Status-Log ----
        grp_status = QGroupBox("Status")
        lay_status = QVBoxLayout(grp_status)
        self.status_text = QPlainTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setFont(QFont("Consolas", 10))
        lay_status.addWidget(self.status_text)
        root_layout.addWidget(grp_status, stretch=2)

    # ---------- Eingabe-Filter ----------

    def _strip_whitespace_image_name(self, text: str) -> None:
        cleaned = re.sub(r"\s+", "", text)
        if cleaned != text:
            self.entry_name.blockSignals(True)
            self.entry_name.setText(cleaned)
            self.entry_name.blockSignals(False)

    # ---------- Proxy ----------

    def _on_proxy_toggle(self) -> None:
        enabled = self.chk_proxy.isChecked()
        self.entry_proxy_url.setEnabled(enabled)
        self.entry_proxy_user.setEnabled(enabled)
        self.entry_proxy_pass.setEnabled(enabled)

    def _get_proxy_url(self) -> Optional[str]:
        if not self.chk_proxy.isChecked():
            return None
        url = self.entry_proxy_url.text().strip()
        if not url:
            return None
        user = self.entry_proxy_user.text().strip()
        pwd = self.entry_proxy_pass.text()
        if user:
            parts = urlsplit(url)
            netloc = f"{user}:{pwd}@{parts.hostname}"
            if parts.port:
                netloc += f":{parts.port}"
            url = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
        return url

    # ---------- Kommunikation Worker ↔ GUI ----------

    def post(self, event: tuple) -> None:
        self.gui_queue.put(event)

    def _pump_queue(self) -> None:
        try:
            while True:
                event = self.gui_queue.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass

    def _handle_event(self, event: tuple) -> None:
        kind = event[0]

        if kind == "log":
            msg      = event[1] if len(event) > 1 else ""
            replace  = event[2] if len(event) > 2 else False
            finalize = event[3] if len(event) > 3 else False
            self._append_log(msg, replace=replace, finalize=finalize)

        elif kind == "slot_start":
            _, slot, filename = event
            self.slot_labels[slot].setText(f"[Slot {slot + 1}] {filename}  – startet …")
            self.slot_bars[slot].setRange(0, 0)  # indeterminate

        elif kind == "slot_progress":
            _, slot, downloaded, total = event
            bar = self.slot_bars[slot]
            if total > 0:
                pct = (downloaded / total) * 100
                bar.setRange(0, 100)
                bar.setValue(int(pct))
                self.slot_labels[slot].setText(
                    f"[Slot {slot + 1}] {self._slot_filename(slot)}  "
                    f"{self._fmt_bytes(downloaded)} / {self._fmt_bytes(total)}  ({pct:.1f}%)"
                )
            else:
                bar.setRange(0, 0)
                self.slot_labels[slot].setText(
                    f"[Slot {slot + 1}] {self._slot_filename(slot)}  "
                    f"{self._fmt_bytes(downloaded)} (unbekannte Größe)"
                )

        elif kind == "slot_done":
            _, slot, filename, result = event
            bar = self.slot_bars[slot]
            bar.setRange(0, 100)
            bar.setValue(100 if result == "ok" else 0)
            self.slot_labels[slot].setText(f"[Slot {slot + 1}] {filename}  – {result}")

        elif kind == "progress_total":
            _, done, total = event
            pct = (done / total * 100) if total else 0
            self.total_bar.setValue(int(pct))
            self.total_label.setText(f"{done}/{total} Dateien ({pct:.0f}%)")

        elif kind == "state":
            _, state = event
            if state == "running":
                self._set_running(True)
            elif state == "finished":
                self._set_running(False)
                self._reset_ui_after_run()

    def _slot_filename(self, slot: int) -> str:
        text = self.slot_labels[slot].text()
        m = re.match(r"\[Slot \d+\]\s+(\S+)", text)
        return m.group(1) if m else "?"

    @staticmethod
    def _fmt_bytes(n: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} TB"

    # ---------- Log ----------

    def _append_log(self, msg: str, replace: bool = False, finalize: bool = False) -> None:
        txt = self.status_text

        if finalize:
            self._pending_replace_line = False
            return

        if replace:
            if self._pending_replace_line:
                cursor = txt.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                cursor.movePosition(
                    QTextCursor.MoveOperation.StartOfBlock,
                    QTextCursor.MoveMode.KeepAnchor,
                )
                cursor.removeSelectedText()
                if cursor.position() > 0:
                    cursor.deletePreviousChar()
                txt.setTextCursor(cursor)
            txt.appendPlainText(msg)
            self._pending_replace_line = True
        else:
            self._pending_replace_line = False
            if msg:
                txt.appendPlainText(msg)

        txt.ensureCursorVisible()

    # ---------- Button-Zustände ----------

    def _set_running(self, running: bool) -> None:
        if running:
            self.start_button.setText("Stopp")
            self.start_button.setStyleSheet(_STYLE_STOP)
            for w in (self.entry_url, self.entry_name, self.chk_login,
                      self.chk_proxy, self.entry_proxy_url,
                      self.entry_proxy_user, self.entry_proxy_pass):
                w.setEnabled(False)
        else:
            self.start_button.setText("Start")
            self.start_button.setStyleSheet(_STYLE_ACCENT)
            self.start_button.setEnabled(True)
            for w in (self.entry_url, self.entry_name, self.chk_login, self.chk_proxy):
                w.setEnabled(True)
            self._on_proxy_toggle()

    def _reset_ui_after_run(self) -> None:
        self.entry_url.setFocus()
        self.total_bar.setValue(0)
        self.total_label.setText("bereit für nächsten Download.")
        for i, (lbl, bar) in enumerate(zip(self.slot_labels, self.slot_bars)):
            bar.setRange(0, 100)
            bar.setValue(0)
            lbl.setText(f"[Slot {i + 1}] idle")

    # ---------- Start/Stop ----------

    def on_start_or_stop(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            self._request_stop()
        else:
            self._start()

    def _start(self) -> None:
        forum_url  = self.entry_url.text().strip()
        image_name = self.entry_name.text().strip()
        if not forum_url or not image_name:
            QMessageBox.critical(self, "Fehler", "Bitte URL und Bildname eingeben.")
            return

        self.total_bar.setValue(0)
        self.total_label.setText("startet …")
        for i, (lbl, bar) in enumerate(zip(self.slot_labels, self.slot_bars)):
            bar.setRange(0, 100)
            bar.setValue(0)
            lbl.setText(f"[Slot {i + 1}] idle")

        self.status_text.clear()
        self._pending_replace_line = False
        self.cancel_event.clear()
        self.post(("state", "running"))

        job = DownloadJob(forum_url, image_name)
        self.worker_thread = threading.Thread(
            target=self._run_worker, args=(job,), daemon=True
        )
        self.worker_thread.start()

    def _request_stop(self) -> None:
        if self.cancel_event.is_set():
            return
        self._post_log("Stopp angefordert – laufende Downloads werden abgebrochen …")
        self.cancel_event.set()
        self.start_button.setText("Stoppe …")
        self.start_button.setEnabled(False)

    # ---------- Worker-Thread ----------

    def _run_worker(self, job: DownloadJob) -> None:
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self._async_main(job))
        except Exception as e:
            self._post_log(f"Unerwarteter Fehler: {e}")
        finally:
            try:
                if self.loop is not None:
                    self.loop.close()
            except Exception:
                pass
            self.loop = None
            self.post(("state", "finished"))

    async def _async_main(self, job: DownloadJob) -> None:
        log = self._make_log_fn()
        proxy_url = self._get_proxy_url()
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

        try:
            if self.chk_login.isChecked():
                log("Melde an …")
                session = await asyncio.to_thread(
                    login, base_url_of(job.forum_url), USERNAME, PASSWORD, log, proxies
                )
                if session is None:
                    log("Login fehlgeschlagen. Abbruch.")
                    return
            else:
                log("Login deaktiviert – verwende anonyme Session.")
                session = make_anonymous_session(proxies)

            if self.cancel_event.is_set():
                return

            images = await asyncio.to_thread(find_posted_pictures, session, job.forum_url, log)
            if not images or self.cancel_event.is_set():
                log("Keine Bilder gefunden oder Abbruch.")
                return

            folder = await asyncio.to_thread(
                create_folder_from_forum_title, session, job.forum_url, IMG_DL_PATH, log
            )
            if folder is None or self.cancel_event.is_set():
                log("Kein Zielordner – Abbruch.")
                return

            log(f"Löse {len(images)} URL(s) auf …")
            dlurls = await asyncio.to_thread(
                find_real_image_urls, images, self.cancel_event, log, proxies
            )
            dlurls = list(dict.fromkeys(dlurls))
            log(f"{len(dlurls)} eindeutige Download-URL(s) bereit.")
            if not dlurls or self.cancel_event.is_set():
                return

            log(f"Starte Download nach '{folder}' …")
            await download_all(
                urls=dlurls,
                dest_folder=folder,
                name_prefix=job.image_name,
                nbr_parallel=NBR_PARALLEL_DL,
                post_gui=self.post,
                log=log,
                cancel_event=self.cancel_event,
                proxy_url=proxy_url,
            )
            if self.cancel_event.is_set():
                log("Abgebrochen.")
            else:
                log("Fertig.")
        except Exception as e:
            log(f"Fehler im Ablauf: {e}")

    def _make_log_fn(self) -> LogFn:
        def _log(msg: str, replace: bool = False, finalize_replace: bool = False) -> None:
            self.post(("log", msg, replace, finalize_replace))
        return _log

    def _post_log(self, msg: str) -> None:
        self.post(("log", msg, False, False))

    # ---------- Beenden ----------

    def on_close(self) -> None:
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            reply = QMessageBox.question(
                self,
                "Beenden",
                "Ein Download läuft noch. Wirklich abbrechen und beenden?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.cancel_event.set()
            self.worker_thread.join(timeout=2.0)
        event.accept()

    # ---------- Splash ----------

    def _show_splash(self) -> None:
        splash = SplashScreen(
            build_info=BUILD_INFO,
            parent=self,
        )
        splash.show_centered(self)

# ----------------------------------------------------------------------
# Einstiegspunkt
# ----------------------------------------------------------------------

def main() -> None:
    app = QApplication(sys.argv)
    _apply_dark_theme(app)
    window = DownloaderApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
