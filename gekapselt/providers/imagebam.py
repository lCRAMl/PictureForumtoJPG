import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

def get_real_imagebam_url(url: str, timeout: int = 10, debug: bool = False):
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    })
    # Cookie setzen wie beim Klick auf „Continue to your image“
    session.cookies.set("sfw_inter", "1", domain=".imagebam.com", path="/")

    try:
        # Erste Seite (intermediate)
        r1 = session.get(url, timeout=timeout)
        r1.raise_for_status()
        soup = BeautifulSoup(r1.text, "html.parser")

        # Suche nach <meta http-equiv="refresh" content="x;url=/view/...">
        meta_refresh = soup.find("meta", attrs={"http-equiv": "refresh"})
        if meta_refresh and "url=" in meta_refresh.get("content", ""):
            part = meta_refresh["content"].split("url=")[-1]
            next_url = urljoin(url, part.strip())
        else:
            next_url = url  # Fallback: gleiche Seite

        # Jetzt die „echte“ Bildseite laden
        r2 = session.get(next_url, timeout=timeout, headers={"Referer": url})
        r2.raise_for_status()

        if debug:
            with open("debug_resp2.html", "w", encoding="utf-8") as fh:
                fh.write(r2.text)

        soup2 = BeautifulSoup(r2.text, "html.parser")

        # 1. Suche nach <img class="main-image">
        img = soup2.find("img", {"class": "main-image"})
        if img and img.get("src"):
            return img["src"]

        # 2. Alternativ direkte Links prüfen
        for a in soup2.find_all("a", href=True):
            href = a["href"]
            if re.search(r'images\d+\.imagebam\.com/.*\.(jpe?g|png|gif|webp)$', href, re.I):
                return href

        # 3. Oder jedes <img> mit typischer Domain
        for img in soup2.find_all("img", src=True):
            src = img["src"]
            if "imagebam.com" in src and re.search(r'\.(jpe?g|png|gif|webp)$', src, re.I):
                return src

    except Exception as e:
        print(f"[get_imagebam_image_url] Fehler für {url}: {e}")

    return None


if __name__ == "__main__":
    test_url = "https://www.imagebam.com/image/3e5024500980632"
    result = get_real_imagebam_url(test_url, debug=True)
    print("Bild-URL:", result or "Kein Bild gefunden.")
