
# v0.3 Standalone Funktion um die direkte Bild-URL von ImageBam zu extrahieren

import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import re
from typing import Optional

def get_real_imagebam_url(url: str, timeout: int = 10, debug: bool = False) -> Optional[str]:
    """
    Nimmt eine ImageBam 'inter' oder 'view' URL und versucht die direkte Bild-URL
    zu extrahieren. Gibt die Bild-URL als string zurück oder None, wenn nichts gefunden.
    Setze debug=True um die erhaltene view-HTML in 'debug_resp2.html' zu schreiben.
    """
    session = requests.Session()
    # Browser-like header
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    })
    
    # inter -> view
    url = url.replace("/inter/", "/view/")

    try:
        # 1) Erste Seite anfragen (kann inter/ view oder direkte id sein)
        r = session.get(url, timeout=timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Optional: CSRF auslesen (nur informativ)
        meta = soup.find("meta", {"name": "csrf-token"})
        if meta and meta.get("content"):
            csrf = meta["content"]
            # print("CSRF:", csrf)  # falls benötigt

        # 2) Cookie setzen wie das JS es tun würde
        # setze für beide Domain-Formen, falls der Server streng prüft
        session.cookies.set("sfw_inter", "1", domain=".imagebam.com", path="/")
        session.cookies.set("sfw_inter", "1", domain="imagebam.com", path="/")

        # 3) Bestimme die "view"-URL (wenn inter gegeben wurde, ersetze)
        parsed = urlparse(url)
        path = parsed.path or ""
        if "/inter/" in path:
            view_path = path.replace("/inter/", "/view/")
        elif "/view/" in path:
            view_path = path
        else:
            # Fallback: versuche /view/<last-segment>
            segs = [s for s in path.split("/") if s]
            if segs:
                view_path = "/view/" + segs[-1]
            else:
                view_path = path

        base = f"{parsed.scheme}://{parsed.netloc}"
        view_url = urljoin(base, view_path)

        # 4) Die view-Seite abrufen (Referer setzen)
        r2 = session.get(view_url, timeout=timeout, headers={"Referer": url})
        r2.raise_for_status()

        if debug:
            with open("debug_resp2.html", "w", encoding="utf-8") as fh:
                fh.write(r2.text)

        soup2 = BeautifulSoup(r2.text, "html.parser")

        # 5) Suche nach einem Link mit "Download" im Text (case-insensitive)
        a_download = soup2.find("a", string=lambda s: bool(s and "download" in s.lower()))
        if a_download and a_download.get("href"):
            href = urljoin(view_url, a_download["href"])
            if re.search(r'\.(jpe?g|png|gif|webp|bmp)$', href, re.I):
                return href
            return href  # auch wenn keine Endung - zurückgeben und prüfen

        # 6) Fallback: Links, die auf image-Hosts oder direkte Bilddateien zeigen
        for a in soup2.find_all("a", href=True):
            href = a["href"]
            # typisches ImageBam images host pattern
            if re.search(r'images\d+\.imagebam\.com/.*\.(jpe?g|png|gif|webp|bmp)$', href, re.I):
                return urljoin(view_url, href)
            if re.search(r'\.(jpe?g|png|gif|webp|bmp)$', href, re.I):
                return urljoin(view_url, href)

        # 7) Letzter Fallback: <img> tags
        for img in soup2.find_all("img", src=True):
            src = img["src"]
            if re.search(r'\.(jpe?g|png|gif|webp|bmp)$', src, re.I):
                return urljoin(view_url, src)

    except Exception as exc:
        # Fehler ausgeben, aber Funktion gibt None zurück
        print(f"[get_imagebam_image_url] Fehler für {url}: {exc}")

    return None


# --- Standalone Ausführung ---
if __name__ == "__main__":
    import sys

    # URL aus Kommandozeile oder Hardcode
    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://www.imagebam.com/inter/ME14NC0J"
    result = get_real_imagebam_url(test_url, debug=True)
    if result:
        print("Bild-URL:", result)
    else:
        print("Kein Bild gefunden.")