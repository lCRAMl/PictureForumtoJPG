# utils/file_utils.py
import os
import re
from bs4 import BeautifulSoup

def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', name)

def create_folder_from_forum_title(session, forum_url, save_path):
    page = session.get(forum_url)
    soup = BeautifulSoup(page.text, 'html.parser')

    title_tag = soup.find('h1', class_='p-title-value')
    if not title_tag:
        raise RuntimeError("Forum title not found")

    folder_name = sanitize_filename(title_tag.text.strip())
    fullpath = os.path.join(save_path, folder_name)

    os.makedirs(fullpath, exist_ok=True)
    return fullpath
