# v0.1 Standalone Funktion um die direkte Bild-URL von Pixhost zu extrahieren


import requests
from bs4 import BeautifulSoup
from typing import Optional


def get_real_imgbox_url(image_url, debug: bool = False) -> Optional[str]:
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://imgbox.com/"
        }

        response = requests.get(image_url, headers=headers)
        if response.status_code != 200:
            print(f"Status code: {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        img_tag = soup.find("img", id="img")
        if img_tag and img_tag.has_attr("src"):
            return img_tag["src"]

        return None

    except Exception as e:
        print(f"An error occurred while searching at imgbox.com: {e}")
        return None
    
    
# --- Standalone Ausführung ---
if __name__ == "__main__":
    import sys

    # URL aus Kommandozeile oder Hardcode
    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://imgbox.com/bVwd82on"
    result = get_real_imgbox_url(test_url, debug=True)
    if result:
        print("Bild-URL:", result)
    else:
        print("Kein Bild gefunden.")