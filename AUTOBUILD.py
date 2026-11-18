#AUTOBUILD.py

from ensurepip import version
import subprocess
import tempfile
from datetime import datetime
import os
import shutil
import time

# =========================
# CONFIG
# =========================

TARGET_PY_FILE = "ForumImageDownloader.py"
APP_NAME = "Forum Image Downloader"

ICON_PATH = "assets/dl_img.ico"

ASSET_PATHS = {
    "assets": "assets",
    "SplashScreenPython\\assets": "assets"
}

VERSION_FILE = "build_version.py"

OUTPUT_DIR = "output"
BUILD_DIR = "pyinstaller_build"

AUTO_PY_TO_EXE_LAUNCH = False


# =========================
# VERSION HELPERS
# =========================

def get_git_version():
    try:
        return subprocess.check_output(
            ["git", "describe", "--tags", "--long"]
        ).decode().strip()
    except Exception:
        return "0.0.0-0-unknown"

def get_git_commit():
    return subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"]
    ).decode().strip()

def get_git_commit_url():
    try:
        # short commit hash
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"]
        ).decode().strip()

        # remote URL (origin)
        remote = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"]
        ).decode().strip()

        # normalize SSH → HTTPS
        if remote.startswith("git@github.com:"):
            remote = remote.replace("git@github.com:", "https://github.com/")
            remote = remote.replace(".git", "")
        elif remote.startswith("https://") and remote.endswith(".git"):
            remote = remote[:-4]

        # build URL (GitHub-style)
        if "github.com" in remote:
            return f"{remote}/commit/{commit}"

        # fallback generic
        return f"{remote}/commit/{commit}"

    except Exception:
        return "unknown-commit-url"

def get_build_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# =========================
# WRITE VERSION FILE
# =========================

def write_version_file(version, build_time, COMMIT, COMMIT_URL):
    content = f'''# AUTO GENERATED FILE
APP_NAME = "{APP_NAME}"
VERSION = "{version}"
BUILD_TIME = "{build_time}"
COMMIT = "{COMMIT}"
COMMIT_URL = "{COMMIT_URL}"
BUILD_INFO = "{APP_NAME} \\n{version} \\n{build_time}"
'''

    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅ Version file written: {VERSION_FILE}")


# =========================
# CLEAN OUTPUT
# =========================

def clean():
    if os.path.exists(BUILD_DIR):
        shutil.rmtree(BUILD_DIR, ignore_errors=True)

    # remove leftover spec files
    for file in os.listdir("."):
        if file.endswith(".spec"):
            os.remove(file)
            print(f"🧹 removed {file}")

PIN_OK = "📌 Kachel vorhanden - sie startet jetzt den neuen Bau"
PIN_HINT = ('📌 Noch keine Kachel. Einmal anheften: Start > Alle Apps > {name} > Rechtsklick > '
            '"An Start anheften". Alte Kacheln mit Versionsnummer im Namen loesen.')


def start_menu_programs_dir() -> str:
    """Startmenue-Ordner "Programme" des Benutzers, auch bei umgeleiteten Profilen.
    Aus ihm speist Windows die Liste "Alle Apps" - und die Kacheln."""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        # 0x0002 = CSIDL_PROGRAMS, 0 = SHGFP_TYPE_CURRENT
        if ctypes.windll.shell32.SHGetFolderPathW(0, 0x0002, 0, 0, buf) == 0 and buf.value:
            return buf.value
    except Exception:
        pass
    return os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs")


def start_tile_present(shortcut) -> bool:
    """Steht im Startmenue eine Kachel fuer diese Verknuepfung? Gelesen mit Export-StartLayout."""
    with tempfile.TemporaryDirectory() as tmp:
        layout = os.path.join(tmp, "layout.xml")
        subprocess.run(["powershell", "-NoProfile", "-Command", f"Export-StartLayout -Path '{layout}'"],
                       capture_output=True, timeout=60)
        if not os.path.exists(layout):
            return False
        with open(layout, encoding="utf-8", errors="ignore") as fh:
            text = fh.read().lower()
    return "\\" + os.path.basename(str(shortcut)).lower() in text


def check_start_tile(shortcut) -> None:
    """Meldet, ob die Kachel steht. Anheften kann das Skript sie nicht: Windows 10 laesst
    "An Start anheften" nur den Explorer ausfuehren, jedes andere Programm bekommt
    "Zugriff verweigert". Weil der Name der Verknuepfung keine Version traegt, folgt eine
    einmal angeheftete Kachel jedem weiteren Bau und startet immer die neueste Fassung.
    """
    name = os.path.splitext(os.path.basename(str(shortcut)))[0]
    if start_tile_present(shortcut):
        print(PIN_OK)
    else:
        print(PIN_HINT.format(name=name))


def create_shortcut(app_name, target_exe, output_dir):
    try:
        import pythoncom
        from win32com.shell import shell

        pythoncom.CoInitialize()  # 🔥 CRITICAL FIX

        target_exe = os.path.realpath(os.path.abspath(target_exe))

        if not os.path.exists(target_exe):
            raise FileNotFoundError(target_exe)

        # Im Startmenue und ohne Version im Namen: eine dort angeheftete Kachel
        # startet nach jedem Bau die neueste .exe.
        shortcut_path = os.path.join(start_menu_programs_dir(), f"{app_name}.lnk")

        shell_link = pythoncom.CoCreateInstance(
            shell.CLSID_ShellLink,
            None,
            pythoncom.CLSCTX_INPROC_SERVER,
            shell.IID_IShellLinkW
        )

        for _ in range(50):
            if os.path.exists(target_exe) and os.path.getsize(target_exe) > 0:
                break
            time.sleep(0.1)
        else:
            raise FileNotFoundError("EXE not ready yet: " + target_exe)

        shell_link.SetPath(target_exe)
        shell_link.SetWorkingDirectory(os.path.abspath(output_dir))
        shell_link.SetDescription(app_name)

        persist_file = shell_link.QueryInterface(pythoncom.IID_IPersistFile)
        persist_file.Save(shortcut_path, 0)
        print(f"🔗 Startmenue-Verknuepfung zeigt auf den neuen Bau: {shortcut_path}")
        check_start_tile(shortcut_path)

        print(f"🔗 Shortcut created: {shortcut_path}")

    except Exception as e:
        print(f"⚠ Shortcut creation failed: {e}")


# =========================
# PYINSTALLER BUILD
# =========================

def build_pyinstaller(exe_name):

    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",

        # output control
        f"--name={exe_name}",
        f"--distpath={OUTPUT_DIR}",
        f"--workpath={BUILD_DIR}",

        "--clean",
        "--noconfirm",

        f"--icon={ICON_PATH}",
    ]

    # =========================
    # ADD DATA FIXED MAPPING
    # =========================
    for source, target in ASSET_PATHS.items():
        if os.path.exists(source):
            cmd.append(f"--add-data={source}{os.pathsep}{target}")

    cmd.append(TARGET_PY_FILE)

    print("\n🚀 Running build:\n")
    print(" ".join(cmd))
    print("\n")

    subprocess.run(cmd, check=True)


# =========================
# MAIN
# =========================

def main():
    print("🔧 Build started...")

    version = get_git_version()
    build_time = get_build_time()
    COMMIT = get_git_commit()
    COMMIT_URL = get_git_commit_url()

    print(f"📦 Git Version: {version}")
    print(f"⏱ Build Time: {build_time}")
    print(f"🔗 Commit: {COMMIT}")
    print(f"🌐 Commit URL: {COMMIT_URL}")

    write_version_file(version, build_time, COMMIT, COMMIT_URL)

    safe_app = APP_NAME.replace(" ", "")
    safe_version = version.replace("+", "_").replace(" ", "_")
    exe_name = f"{safe_app}_{safe_version}"

    build_pyinstaller(exe_name)
    
    exe_file = f"{exe_name}.exe"
    exe_path = os.path.abspath(os.path.join(OUTPUT_DIR, exe_file))

    create_shortcut(safe_app, exe_path, OUTPUT_DIR)
    clean()

    print("\n✅ DONE")


if __name__ == "__main__":
    main()