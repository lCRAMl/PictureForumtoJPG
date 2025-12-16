# main.py

import asyncio

from config import (
    USE_LOGIN, USERNAME, PASSWORD,
    NBR_PARALLEL_DL, IMG_DL_PATH
)

from downloader.image_downloader import ImageDownloader
from utils.file_utils import create_folder_from_forum_title
from providers.providers import (
    get_real_imagebam_url,
    get_real_pixhost_url,
    get_real_postimg_url,
    get_real_imgbox_url,
    get_real_turboimagehost_url
)


host_functions = {
    "imagebam.com": get_real_imagebam_url,
    "pixhost.to": get_real_pixhost_url,
    "postimg.cc": get_real_postimg_url,
    "imgbox.com": get_real_imgbox_url,
    "turboimagehost.com": get_real_turboimagehost_url
}


def start_download_process(forum_url: str, image_basename: str):

    BASE_URL = "/".join(forum_url.split("/")[:3])

    # Downloader erzeugen
    downloader = ImageDownloader(
        use_login=USE_LOGIN,
        username=USERNAME,
        password=PASSWORD,
        max_parallel=NBR_PARALLEL_DL,
        host_resolvers=host_functions
    )

    session = downloader.login(BASE_URL)

    links = downloader.find_images(session, forum_url)
    real_links = downloader.resolve_links(links)

    dest_folder = create_folder_from_forum_title(session, forum_url, IMG_DL_PATH)

    asyncio.run(
        downloader.download_all(real_links, dest_folder, image_basename)
    )


if __name__ == "__main__":
    from gui.gui import start_gui
    start_gui()
