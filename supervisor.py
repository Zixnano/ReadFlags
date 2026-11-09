"""Read Flags launcher. Run this instead of the game directly: python supervisor.py"""
import logging
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app"
LOGS = ROOT / "logs"
DB = ROOT / "database.db"

LOGS.mkdir(exist_ok=True)
log = logging.getLogger("supervisor")
log.setLevel(logging.INFO)
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] supervisor: %(message)s")
_fh = logging.FileHandler(LOGS / "startup.log", encoding="utf-8")
_fh.setFormatter(_fmt)
_sh = logging.StreamHandler()
_sh.setFormatter(_fmt)
log.addHandler(_fh)
log.addHandler(_sh)


def write_crash(text):
    with open(LOGS / "crash.log", "a", encoding="utf-8") as f:
        f.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} =====\n{text}\n")
    log.error("Crash written to logs/crash.log")


def run():
    log.info("Read Flags starting")

    # 1. AI bootstrapper
    try:
        r = subprocess.run([sys.executable, str(APP / "bootstrapper.py")], cwd=str(ROOT))
    except Exception:
        log.exception("Could not run the bootstrapper")
        return 1
    if r.returncode != 0:
        log.error("Bootstrapper failed (exit code %s). See logs/startup.log", r.returncode)
        return 1

    # 2. Database
    if not DB.exists():
        log.info("database.db not found, creating it")
        try:
            r = subprocess.run([sys.executable, str(APP / "database.py")], cwd=str(ROOT))
        except Exception:
            log.exception("Could not run database.py")
            return 1
        if r.returncode != 0 or not DB.exists():
            log.error("Database creation failed")
            return 1

    # 3. Game
    log.info("Launching game")
    try:
        r = subprocess.run([sys.executable, str(APP / "main.py")], cwd=str(ROOT),
                           stderr=subprocess.PIPE, text=True)
        if r.returncode != 0:
            write_crash(f"main.py exited with code {r.returncode}\n{r.stderr}")
            return 1
    except Exception:
        write_crash(traceback.format_exc())
        return 1
    log.info("Game closed normally")
    return 0


if __name__ == "__main__":
    sys.exit(run())
