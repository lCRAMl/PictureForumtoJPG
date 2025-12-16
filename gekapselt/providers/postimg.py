# v0.1 Standalone Funktion um die direkte Bild-URL von Pixhost zu extrahieren


import requests
from bs4 import BeautifulSoup
from typing import Optional

def get_real_postimg_url(image_page_url: str, debug: bool = False) -> Optional[str]:
    """
    Extrahiert die echte Bild-URL von einer Postimages-Seite.
    Funktioniert, egal ob der Download-Button vorhanden ist oder nicht.
    
    Args:
        image_page_url (str): URL der Postimages-Seite (z.B. https://postimg.cc/xxxx)
        debug (bool): Wenn True, werden Debug-Infos ausgegeben.
    
    Returns:
        str | None: Direkter JPG-Link oder None, wenn nicht gefunden.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://postimg.cc/"
        }
        response = requests.get(image_page_url, headers=headers)
        if response.status_code != 200:
            if debug:
                print(f"Failed to load page: {image_page_url} (status {response.status_code})")
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # 1️⃣ Prüfe Download-Button
        download_link = soup.find("a", id="download")
        if download_link and download_link.get("href"):
            href = download_link["href"]
            # Sicherstellen, dass ?dl=1 am Ende steht
            if "?dl=1" not in href:
                href += "?dl=1"
            if debug:
                print("Found download button URL:", href)
            return href

        # 2️⃣ Fallback: og:image Meta-Tag
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            if debug:
                print("Found og:image URL:", og_image["content"])
            return og_image["content"]

        if debug:
            print("No image URL found on the page.")
        return None

    except Exception as e:
        if debug:
            print(f"Error while extracting image URL: {e}")
        return None
    
# --- Standalone Ausführung ---
if __name__ == "__main__":
    import sys

    # URL aus Kommandozeile oder Hardcode
    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://postimg.cc/svbvJ4Zd"
    result = get_real_postimg_url(test_url, debug=True)
    if result:
        print("Bild-URL:", result)
    else:
        print("Kein Bild gefunden.")