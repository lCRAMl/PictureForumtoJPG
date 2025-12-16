# downloader/image_downloader.py

import os
import random
import asyncio
import requests
import httpx
import tqdm
from bs4 import BeautifulSoup
from typing import List
from tenacity import retry, stop_after_attempt, wait_fixed
from skimage import io


class ImageDownloader:

    def __init__(self,
                 use_login: bool,
                 username: str = None,
                 password: str = None,
                 max_parallel: int = 5,
                 host_resolvers: dict = None):

        self.use_login = use_login
        self.username = username
        self.password = password

        self.host_resolvers = host_resolvers or {}
        self.sem = asyncio.Semaphore(max_parallel)

        # Headers + UA
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:101.0) Gecko/20100101 Firefox/101.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
        ]
        self.headers = {
            "User-Agent": random.choice(self.user_agents)
        }

        self.session = None

    # ─────────────────────────────────────────────
    # LOGIN
    # ─────────────────────────────────────────────
    def login(self, base_url: str):
        if not self.use_login:
            print("Login skipped.")
            self.session = requests.Session()
            return self.session

        login_url = f"{base_url}/login/login"
        session = requests.Session()

        page = session.get(login_url)
        soup = BeautifulSoup(page.text, "html.parser")

        token = soup.find("input", {"name": "_xfToken"})
        if not token:
            raise RuntimeError("CSRF token not found")

        payload = {
            "login": self.username,
            "password": self.password,
            "_xfToken": token["value"],
        }

        r = session.post(login_url, data=payload)
        if r.status_code != 200:
            raise RuntimeError("Login failed")

        print("Login OK")
        self.session = session
        return session

    # ─────────────────────────────────────────────
    # LINKS FINDEN
    # ─────────────────────────────────────────────
    def find_images(self, session, forum_url: str) -> List[str]:
        page = session.get(forum_url)
        soup = BeautifulSoup(page.text, "html.parser")

        container = soup.find("div", class_="block-body js-replyNewMessageContainer")
        if not container:
            return []

        links = []
        for a in container.find_all("a", href=True):
            full = requests.compat.urljoin(forum_url, a["href"])
            if any(host in full for host in self.host_resolvers.keys()):
                links.append(full)

        print(f"Found {len(links)} image link containers")
        return links

    # ─────────────────────────────────────────────
    # DIREKTE BILDLINKS ERMITTELN
    # ─────────────────────────────────────────────
    def resolve_links(self, links: List[str]) -> List[str]:
        out = []
        for l in links:
            for host, func in self.host_resolvers.items():
                if host in l:
                    real = func(l)
                    if real:
                        out.append(real)

        return list(dict.fromkeys(out))

    # ─────────────────────────────────────────────
    # EINZELNER DOWNLOAD
    # ─────────────────────────────────────────────
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def download_file(self, url: str, dest: str):

        async with httpx.AsyncClient(timeout=60, headers=self.headers) as client:
            async with client.stream("GET", url) as r:
                if r.status_code != 200:
                    raise RuntimeError(f"Bad response: {r.status_code}")

                total = int(r.headers.get("content-length", 0))

                with tqdm.tqdm(total=total, unit="B", unit_scale=True,
                               desc=os.path.basename(dest)) as pb:

                    with open(dest, "wb") as f:
                        async for chunk in r.aiter_bytes():
                            f.write(chunk)
                            pb.update(len(chunk))

    async def safe_download(self, url, dest):
        async with self.sem:
            await self.download_file(url, dest)

    # ─────────────────────────────────────────────
    # ALLE DOWNLOADEN
    # ─────────────────────────────────────────────
    async def download_all(self, urls: List[str], folder: str, basename: str):
        tasks = []

        for idx, url in enumerate(urls, 1):
            filename = f"{basename}_{idx:03}.jpg"
            fullpath = os.path.join(folder, filename)

            tasks.append(
                asyncio.create_task(self.safe_download(url, fullpath))
            )

        await asyncio.gather(*tasks)
        print("All downloads finished.")
