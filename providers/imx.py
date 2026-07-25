import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
from typing import Optional


def get_real_imx_url(url: str, timeout: int = 10, debug: bool = False, proxies: Optional[dict] = None):
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    })
    if proxies:
        session.proxies.update(proxies)
    # Cookie setzen wie beim Klick auf "Continue to your image"
    session.cookies.set("sfw_inter", "1", domain=".imx.to", path="/")

    def extract_image(html: str, base_url: str):
        soup = BeautifulSoup(html, "html.parser")

        # 1. Suche nach <img class="main-image"> (alt) oder <img class="centred"> (aktuell)
        img = soup.find("img", class_=["main-image", "centred"])
        if img and img.get("src"):
            return urljoin(base_url, img["src"])

        # 2. Alternativ direkte Links pruefen
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.search(r'images?\d*\.imx\.to/.*\.(jpe?g|png|gif|webp)$', href, re.I):
                return urljoin(base_url, href)

        # 3. Oder jedes <img> mit typischer Domain
        for img in soup.find_all("img", src=True):
            src = img["src"]
            if "imx.to" in src and re.search(r'\.(jpe?g|png|gif|webp)$', src, re.I):
                return urljoin(base_url, src)

        return None

    try:
        # Erste Seite laden
        r1 = session.get(url, timeout=timeout)
        r1.raise_for_status()
        html = r1.text
        current_url = r1.url
        soup = BeautifulSoup(html, "html.parser")

        # Klassischer Redirect ueber <meta http-equiv="refresh" content="x;url=/view/...">
        meta_refresh = soup.find("meta", attrs={"http-equiv": "refresh"})
        if meta_refresh and "url=" in meta_refresh.get("content", ""):
            part = meta_refresh["content"].split("url=")[-1]
            next_url = urljoin(current_url, part.strip())
            r2 = session.get(next_url, timeout=timeout, headers={"Referer": url})
            r2.raise_for_status()
            html = r2.text
            current_url = r2.url
            soup = BeautifulSoup(html, "html.parser")

        # Interstitial-Seite mit "Continue to your image..."-Button (Formular-POST)
        continue_input = soup.find("input", {"name": "imgContinue"}) or soup.find("input", {"id": "continuebutton"})
        if continue_input:
            form = continue_input.find_parent("form")
            action = form.get("action") if form else ""
            post_url = urljoin(current_url, action) if action else current_url
            field_name = continue_input.get("name", "imgContinue")
            field_value = continue_input.get("value", "Continue to your image...")
            r3 = session.post(
                post_url,
                data={field_name: field_value},
                timeout=timeout,
                headers={"Referer": current_url},
            )
            r3.raise_for_status()
            html = r3.text
            current_url = r3.url

        if debug:
            with open("debug_resp2.html", "w", encoding="utf-8") as fh:
                fh.write(html)

        result = extract_image(html, current_url)
        if result:
            return result

    except Exception as e:
        print(f"[get_real_imx_url] Fehler fuer {url}: {e}")

    return None


if __name__ == "__main__":
    test_url = "https://imx.to/i/6x15ot"
    result = get_real_imx_url(test_url, debug=True)
    print("Bild-URL:", result or "Kein Bild gefunden.")
