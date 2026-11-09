"""Makes sure Ollama and the AI model are installed and running.

Exit code 0 means ready, 1 means failed. Everything is logged to logs/startup.log.
"""
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
OLLAMA_URL = "http://localhost:11434"
INSTALLER_URL = "https://ollama.com/download/OllamaSetup.exe"
# llama3.2:3b is the 3B model. (plain "llama3" is the 8B model.)
MODEL = os.environ.get("READFLAGS_MODEL", "llama3.2:3b")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def get_logger():
    LOGS.mkdir(exist_ok=True)
    logger = logging.getLogger("bootstrapper")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] bootstrapper: %(message)s")
        fh = logging.FileHandler(LOGS / "startup.log", encoding="utf-8")
        fh.setFormatter(fmt)
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(fh)
        logger.addHandler(sh)
    return logger


log = get_logger()


def find_ollama():
    """Return the command that runs Ollama, or None if it is not installed."""
    candidates = ["ollama"]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(str(Path(local) / "Programs" / "Ollama" / "ollama.exe"))
    for cmd in candidates:
        try:
            r = subprocess.run([cmd, "-v"], capture_output=True, text=True, timeout=20,
                               creationflags=NO_WINDOW)
            if r.returncode == 0:
                return cmd
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue
    return None


def download_installer():
    dest = Path(tempfile.gettempdir()) / "OllamaSetup.exe"
    log.info("Downloading Ollama installer to %s", dest)
    with requests.get(INSTALLER_URL, stream=True, timeout=30) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=256 * 1024):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  downloading: {done * 100 // total}% ({done // 1048576} MB)",
                          end="", flush=True)
    print()
    return dest


def install_ollama():
    if os.name != "nt":
        log.error("Auto-install only works on Windows. Install Ollama from https://ollama.com")
        return False
    try:
        installer = download_installer()
        log.info("Running Ollama installer silently (this can take a minute)")
        r = subprocess.run([str(installer), "/S", "/VERYSILENT", "/NORESTART"], timeout=900)
        log.info("Installer exited with code %s", r.returncode)
        if r.returncode != 0:
            return False
        for _ in range(30):  # wait for the install to become visible
            if find_ollama():
                return True
            time.sleep(1)
        log.error("Installer finished but Ollama was not found")
        return False
    except Exception:
        log.exception("Ollama installation failed")
        return False


def server_up():
    try:
        return requests.get(OLLAMA_URL, timeout=2).status_code == 200
    except requests.RequestException:
        return False


def ensure_server(exe):
    if server_up():
        log.info("Ollama server already running")
        return True
    log.info("Starting 'ollama serve' in the background")
    try:
        subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=NO_WINDOW)
    except OSError:
        log.exception("Could not launch ollama serve")
        return False
    for _ in range(40):
        if server_up():
            log.info("Ollama server is up")
            return True
        time.sleep(0.5)
    log.error("Ollama server did not respond after launch")
    return False


def model_installed(exe):
    try:
        r = subprocess.run([exe, "list"], capture_output=True, text=True, timeout=30,
                           creationflags=NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        log.exception("'ollama list' failed")
        return False
    for line in r.stdout.splitlines()[1:]:
        parts = line.split()
        if not parts:
            continue
        name = parts[0]
        if name == MODEL or (":" not in MODEL and name.split(":")[0] == MODEL):
            return True
    return False


def pull_model(exe):
    log.info("Model '%s' not found. Downloading (about 2 GB, one time only)", MODEL)
    print(f"\nDownloading AI model {MODEL}. Progress is shown below:\n")
    try:
        r = subprocess.run([exe, "pull", MODEL])  # inherits console so progress shows
    except OSError:
        log.exception("ollama pull failed to start")
        return False
    print()
    if r.returncode != 0:
        log.error("ollama pull exited with code %s", r.returncode)
        return False
    return True


def run():
    try:
        exe = find_ollama()
        if exe is None:
            log.warning("Ollama is not installed")
            if not install_ollama():
                return False
            exe = find_ollama()
            if exe is None:
                return False
        log.info("Ollama found: %s", exe)
        if not ensure_server(exe):
            return False
        if not model_installed(exe):
            if not pull_model(exe) or not model_installed(exe):
                return False
        log.info("AI is ready (model %s)", MODEL)
        return True
    except Exception:
        log.exception("Bootstrapper crashed")
        return False


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
