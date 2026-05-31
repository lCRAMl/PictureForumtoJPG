# v0.1 Standalone Funktion um die direkte Bild-URL von Pixhost zu extrahieren


import requests
from bs4 import BeautifulSoup
from typing import Optional

def get_real_pixhost_url(image_url, debug: bool = False, proxies: Optional[dict] = None) -> Optional[str]:

    try:
        # Fetch the page to get the actual image URL
        response = requests.get(image_url, proxies=proxies)
        if response.status_code != 200:
            print(f"Failed to load Pixhost page: {image_url}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        # Find all <a> tags with the class 'view-image'
        img_tags = [img["src"] for img in soup.select(".image img")]
        # Iterate through the <a> tags to find the href with the desired .jpg URL
        return img_tags[0]

    except Exception as e:
        print(f"An error occurred while searching at Pixhost: {e}")
        return []
    
    
# --- Standalone Ausführung ---
if __name__ == "__main__":
    import sys

    # URL aus Kommandozeile oder Hardcode
    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://pixhost.to/show/7875/630863093_img_6513.jpg"
    result = get_real_pixhost_url(test_url, debug=True)
    if result:
        print("Bild-URL:", result)
    else:
        print("Kein Bild gefunden.")