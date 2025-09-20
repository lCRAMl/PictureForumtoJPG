# v0.1 Standalone Funktion um die direkte Bild-URL von Pixhost zu extrahieren


import requests
from bs4 import BeautifulSoup
from typing import Optional

def get_real_postimg_url(image_url, debug: bool = False) -> Optional[str]:
    try:
        response = requests.get(image_url)
        if response.status_code != 200:
            if debug:
                print(f"Failed to load postimg.cc page: {image_url}")
            return None

        soup = BeautifulSoup(response.text, 'html.parser')

        # Fallback: Direktlink im Download-Button
        download_link = soup.find("a", id="download")
        if download_link and download_link.get("href"):
            return download_link["href"]

        if debug:
            print("Kein Bild gefunden auf der Seite:", image_url)
        return None

    except Exception as e:
        if debug:
            print(f"Error fetching postimg.cc URL {image_url}: {e}")
        return None
    
# --- Standalone Ausführung ---
if __name__ == "__main__":
    import sys

    # URL aus Kommandozeile oder Hardcode
    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://postimg.cc/cK21Bszx"
    result = get_real_postimg_url(test_url, debug=True)
    if result:
        print("Bild-URL:", result)
    else:
        print("Kein Bild gefunden.")