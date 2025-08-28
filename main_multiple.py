
# 2025-08-25 v0.2 added complete rewritten function for imagbam with CSRF handling and cookie setting
# 2025-08-25 v0.2 removed all functions to providers.py

import requests
from bs4 import BeautifulSoup
import os
import re
import tqdm
import asyncio
import httpx
import random
from skimage import io
from tenacity import retry, stop_after_attempt, wait_fixed
from providers.providers import get_real_imagebam_url, get_real_pixhost_url, get_real_postimg_url, get_real_imgbox_url, get_real_turboimagehost_url
from typing import List
import keyboard

FORUM_URL = "https://picturepub.net/threads/jenna-ortega-wednesday-season-2-press-conference-in-seoul-south-korea-august-11-2025.421919/"  # Replace with the forum thread URL
from credentials import USERNAME, PASSWORD
BASE_URL = "/".join(FORUM_URL.split("/")[:3])
IMG_DL_PATH = "Z:\\Downloads\\"  # Replace with your desired download path
IMAGENAME = "WednesdaySeason2PressConferenceinSeoul_11Aug2o25"  # Replace with the image name
nbrOfParallelDL = 5  # Number of parallel downloads

download_counter = 0

host_functions = {
        "imagebam.com": get_real_imagebam_url,
        "pixhost.to": get_real_pixhost_url,
        "postimg.cc": get_real_postimg_url,
        "imgbox.com": get_real_imgbox_url,
        "turboimagehost.com": get_real_turboimagehost_url
    }

user_agents = [ 
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:101.0) Gecko/20100101 Firefox/101.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36', 
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36', 
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36', 
    'Mozilla/5.0 (iPhone; CPU iPhone OS 12_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148', 
    'Mozilla/5.0 (Linux; Android 11; SM-G960U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.72 Mobile Safari/537.36' 
]
user_agent = random.choice(user_agents)

headers = {
    'User-Agent': user_agent,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Referer': 'https://www.google.com',
    'Connection': 'keep-alive',
    'Cache-Control': 'no-cache',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1',
    'TE': 'trailers',
}

def login(base_url, username, password):
    """
    Logs in to a XenForo forum.

    Args:
        base_url (str): The base URL of the XenForo forum (e.g., "https://example.com").
        username (str): The username for login.
        password (str): The password for login.

    Returns:
        requests.Session: A session object if login is successful.
        None: If login fails.
    """
    login_url = f"{base_url}/login/login"
    session = requests.Session()

    # Get the login page to retrieve the CSRF token
    response = session.get(login_url)
    if response.status_code != 200:
        print("Failed to load login page.")
        return None

    # Extract CSRF token from the response
    soup = BeautifulSoup(response.text, 'html.parser')
    csrf_token_tag = soup.find('input', {'name': '_xfToken'})  # Ensure '_xfToken' matches the actual CSRF token field name
    if not csrf_token_tag:
        csrf_token_tag = soup.find('input', {'id': 'csrf_token'})  # Example fallback, adjust based on actual HTML structure
    if csrf_token_tag and 'value' in csrf_token_tag.attrs:
        csrf_token = csrf_token_tag['value']
        #print(f"CSRF token retrieved: {csrf_token}")  # Debugging: Print the CSRF token
    else:
        print("CSRF token not found. Please check the login page structure.")
        #print("Page content for debugging:", soup.prettify())  # Debugging: Print the page content
        raise RuntimeError("CSRF token not found. Please check the login page structure.")

    # Prepare login payload
    payload = {
        "login": username,
        "register": "0",
        "password": password,
        'remember': 1,
        'cookie_check': 1,
        'redirect': '/',
        "_xfToken": csrf_token,
    }

    # Send login request
    response = session.post(login_url, data=payload)
    if response.status_code != 200:
        print("Return Code:", response.status_code)  # Debugging: Print the status code
        print("Login failed. Check your credentials.")
        return None

    print("Login successful.")
    return session

def find_posted_pictures(session, forum_url):
    """
    Finds all posted pictures in a forum link within a specific container,
    filtering by allowed hosts.

    Args:
        session (requests.Session): The logged-in session.
        forum_url (str): The URL of the forum thread or page.

    Returns:
        list: A list of direct image links found in the forum page that match the allowed hosts.
    """

    print("Searching Pictures in:", forum_url)
    response = session.get(forum_url)
    if response.status_code != 200:
        print("Failed to load forum page.")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    image_links = []

    # Search only within the specific container
    container = soup.find('div', class_='block-body js-replyNewMessageContainer')
    if not container:
        print("Specified container not found.")
        return []

    # Find all <a> tags that contain href attributes within the container
    links = container.find_all('a', href=True)
    for link in links:
        href = link['href']
        # Resolve relative URLs to absolute URLs
        image_url = requests.compat.urljoin(forum_url, href)
        #print("Found link:", image_url)  # Debugging: Print each found link
        # Check if image_url contains part of any link from host_functions.keys() <- optional
        if any(host in image_url for host in host_functions) and "gallery" not in image_url:
            image_links.append(image_url)

    print(f"Found {len(image_links)} image links within the specified container that match the allowed hosts.")
    #print(image_links)  # Debugging: Print the list of found image links
    return image_links

def create_folder_from_forum_title(session, forum_url, save_path):
    """
    Extracts the forum title from the given URL, sanitizes it for folder creation,
    and creates a folder in the specified save path.

    Args:
        forum_url (str): The URL of the forum thread or page.
        save_path (str): The base path where the folder will be created.

    Returns:
        str: The full path of the created folder.
    """
    try:
        # Fetch the forum page
        response = session.get(forum_url)
        if response.status_code != 200:
            print("Failed to load forum page.")
            return None

        # Parse the page to extract the title
        soup = BeautifulSoup(response.text, 'html.parser')
        title_tag = soup.find('h1', class_='p-title-value')
        if not title_tag:
            print("Forum title not found.")
            return None

        # Sanitize the title for folder creation
        folder_name = title_tag.text.strip()
        folder_name = re.sub(r'[<>:"/\\|?*]', '_', folder_name)  # Replace invalid characters with '_'

        # Create the folder
        folder_path = os.path.join(save_path, folder_name)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path, exist_ok=True)
            print(f"Folder created: {folder_path}")
        else:
            print(f"Folder already exists: {folder_path}")
        return folder_path
    except Exception as e:
        print(f"An error occurred while creating the folder: {e}")
        return None

def find_real_image_urls(image_urls: List[str]) -> List[str]:
    """Extrahiert reale Bild-URLs für bekannte Hosts."""

    filelist = []

    for url in image_urls:
        if keyboard.is_pressed("esc"):
            break
        try:
            # Suche passende Funktion
            func = next((f for host, f in host_functions.items() if host in url), None)
            if func:
                real_url = func(url)
                if real_url:
                    filelist.append(real_url)
            else:
                print(f"Unsupported host for URL: {url}")
        except Exception as e:
            print(f"An error occurred while processing {url}: {e}")

        print(f"\rFound {len(filelist)} image URLs from {len(image_urls)} so far.", end="")

    return filelist

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def download(imagepath: str, destination: str):
    global download_counter
    download_counter += 1
    fulldestinationname = os.path.join(destination, f"{IMAGENAME}_{download_counter:03}.jpg")

    if not os.path.exists(fulldestinationname) or (os.path.exists(fulldestinationname) and not verify_image(fulldestinationname)):
        async with httpx.AsyncClient(timeout=60) as client:
            for attempt in range(3):
                try:
                    async with client.stream('GET', imagepath, headers=headers) as r:
                        if r.status_code == 200:
                            with open(fulldestinationname, 'wb') as f:
                                r.raise_for_status()
                                total = int(r.headers.get('content-length', 0))
                                tqdm_params = {
                                    #'desc': imagepath,
                                    'desc': f"{IMAGENAME}_{download_counter:03}.jpg",
                                    'total': total,
                                    'miniters': 1,
                                    'unit': 'B',
                                    'unit_scale': True,
                                    'unit_divisor': 1024,
                                }
                                with tqdm.tqdm(**tqdm_params) as pb:
                                    downloaded = r.num_bytes_downloaded
                                    async for chunk in r.aiter_bytes():
                                        pb.update(r.num_bytes_downloaded - downloaded)
                                        f.write(chunk)
                                        downloaded = r.num_bytes_downloaded
                            break  # Success, exit retry loop
                        else:
                            print(f"{imagepath} Response: {r.status_code}")
                            if attempt == 2:
                                print(f"Failed after 3 attempts: {imagepath}")
                                break
                except (httpx.RequestError, httpx.HTTPStatusError, httpx.RemoteProtocolError) as exc:
                    print(f"Attempt {attempt+1}/3: Error while requesting {imagepath}: {exc}")
                    if attempt == 2:
                        print(f"Failed after 3 attempts: {imagepath}")
                except httpx.HTTPStatusError as exc:
                    print(f"Error response {exc.response.status_code} while requesting {exc.request.url!r}.")
                except httpx.RemoteProtocolError as exc:
                    print(f"Remote end closed connection without response: {exc}")

def verify_image(img_file):
    try:
        io.imread(img_file)
        return True
    except Exception:
        return False

sem = asyncio.Semaphore(nbrOfParallelDL)

async def safe_download(file, dest):
    async with sem:
        return await download(file, dest)

async def main():
    session = login(BASE_URL, USERNAME, PASSWORD)
    if session:
        images = find_posted_pictures(session, FORUM_URL)
        dest_folder = create_folder_from_forum_title(session, FORUM_URL, IMG_DL_PATH)
        dlurls = find_real_image_urls(images)

    else:
        print("Login failed. Exiting.")
        exit(1)

    tasks = [asyncio.create_task(safe_download(file, dest_folder)) for file in dlurls]
    await asyncio.gather(*tasks, return_exceptions=True)

if __name__ == '__main__':
    asyncio.run(main())