# v0.1 Standalone Funktion um die direkte Bild-URL von Pixhost zu extrahieren


import requests
from bs4 import BeautifulSoup
from typing import Optional

def get_real_postimg_url(image_url, debug: bool = False) -> Optional[str]:
    try:
        # Fetch the page to get the actual image URL
        response = requests.get(image_url)
        if response.status_code != 200:
            print(f"Failed to load postimg.cc page: {image_url}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        # Find all <a> tags with the class 'view-image'
        img_tag = soup.find("img", id="main-image")
        return img_tag["src"]

    except Exception as e:
        print(f"An error occurred while searching at postimg.cc: {e}")
        return []
    
# --- Standalone Ausführung ---
if __name__ == "__main__":
    import sys

    # URL aus Kommandozeile oder Hardcode
    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://postimg.cc"
    result = get_real_postimg_url(test_url, debug=True)
    if result:
        print("Bild-URL:", result)
    else:
        print("Kein Bild gefunden.")