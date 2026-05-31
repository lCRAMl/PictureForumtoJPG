# v0.2 Standalone Funktion um die direkte Bild-URL von Pixhost zu extrahieren

from patchright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from typing import Optional
import os

PROFILE_DIR = os.path.abspath("./cf_profile")

def get_real_turboimagehost_url(image_url: str, debug: bool = False, proxies: Optional[dict] = None) -> Optional[str]:
    # Playwright erwartet {"server": "socks5://host:port"} — socks5h:// → socks5://
    playwright_proxy = None
    if proxies:
        proxy_server = proxies.get("https") or proxies.get("http")
        if proxy_server:
            playwright_proxy = {"server": proxy_server.replace("socks5h://", "socks5://")}

    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=PROFILE_DIR,
                channel="chrome",
                headless=False,
                no_viewport=True,           # nutzt echte Fenstergröße
                # WICHTIG: keinen user_agent setzen, keine viewport-Fixgröße,
                # keine extra args — das alles erkennt Cloudflare.
                proxy=playwright_proxy,
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(image_url, wait_until="domcontentloaded", timeout=60000)

            try:
                page.wait_for_selector("img#imageid", timeout=90000)
            except Exception:
                if debug:
                    print("Timeout — Challenge nicht gelöst?")

            html = page.content()
            context.close()

        soup = BeautifulSoup(html, "html.parser")
        img_tag = soup.find("img", id="imageid")
        return img_tag["src"] if img_tag and img_tag.get("src") else None

    except Exception as e:
        print(f"Fehler: {e}")
        return None
    
# --- Standalone Ausführung ---
if __name__ == "__main__":
    import sys

    # URL aus Kommandozeile oder Hardcode
    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://www.turboimagehost.com/p/121868482/Olivia_Wilde_39.jpg.html"
    result = get_real_turboimagehost_url(test_url, debug=True)
    if result:
        print("Bild-URL:", result)
    else:
        print("Kein Bild gefunden.")