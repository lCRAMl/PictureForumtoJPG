# gui/gui.py

import tkinter as tk
from tkinter import messagebox, font
import sv_ttk

from config import FORUM_URL, IMAGENAME
from main import start_download_process


def start_gui():
    def on_start():
        url = entry_url.get().strip()
        name = entry_name.get().strip()

        if not url or not name:
            messagebox.showerror("Fehler", "Bitte URL und Bildname eingeben.")
            return

        root.destroy()
        start_download_process(url, name)

    root = tk.Tk()
    root.title("Forum Image Downloader")
    sv_ttk.set_theme("dark")

    large_font = font.Font(family="Arial", size=14)

    tk.Label(root, text="Forum URL:").grid(row=0, column=0, sticky="w")
    entry_url = tk.Entry(root, width=150, font=large_font)
    entry_url.grid(row=0, column=1)
    entry_url.insert(0, FORUM_URL)

    tk.Label(root, text="Bildname:").grid(row=1, column=0, sticky="w")
    entry_name = tk.Entry(root, width=100, font=large_font)
    entry_name.grid(row=1, column=1)
    entry_name.insert(0, IMAGENAME)

    tk.Button(root, text="Start", command=on_start).grid(row=2, column=0, columnspan=2)

    # Fenster zentrieren
    root.update_idletasks()
    w = root.winfo_width()
    h = root.winfo_height()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    root.mainloop()
