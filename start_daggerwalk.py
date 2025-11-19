import subprocess
import time
import psutil
import logging
import os
import pyautogui
import pygetwindow as gw
from pathlib import Path
import youtube_create_broadcast

# Configure logging
LOG_FILE = "daggerwalk.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(console_handler)

DAGGERFALL_EXE = r"C:\Daggerwalk\DaggerfallUnity\DaggerfallUnity.exe"
OBS_EXE = r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"
VIRTUAL_AUDIO_DEVICE = "VB-Audio Virtual Cable"
SOUNDVOLUMEVIEW_PATH = r"C:\Daggerwalk\Utilities\SoundVolumeView\SoundVolumeView.exe"

# === Readiness flag ===
READY_FLAG = Path(r"C:\Daggerwalk\runtime\dfu_ready.flag")

# Function to check if a process is running
def is_process_running(process_name):
    for proc in psutil.process_iter(["name"]):
        if process_name.lower() in (proc.info["name"] or "").lower():
            return True
    return False

# Function to terminate a process by name
def terminate_process(process_name):
    for proc in psutil.process_iter(["name"]):
        if process_name.lower() in (proc.info["name"] or "").lower():
            logging.info(f"Terminating {process_name} (PID: {proc.pid})...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except psutil.TimeoutExpired:
                logging.warning(f"Force killing {process_name}...")
                proc.kill()

def start_daggerfall():
    """
    Launches Daggerfall Unity and performs initial setup.
    Writes READY_FLAG when DFU is confirmed staged and ready.
    If DFU is already running, it still writes the flag so the supervisor can proceed.
    """
    # If already running, just ensure the ready flag exists and return
    if is_process_running("DaggerfallUnity.exe"):
        logging.info("Daggerfall Unity is already running.")
        try:
            READY_FLAG.parent.mkdir(parents=True, exist_ok=True)
            READY_FLAG.write_text("ready", encoding="utf-8")
            logging.info(f"Wrote DFU ready flag (already running): {READY_FLAG}")
        except Exception as e:
            logging.error(f"Failed to write DFU ready flag: {e}")
        return

    logging.info("Starting Daggerfall Unity...")
    try:
        # Start DFU
        subprocess.Popen(
            DAGGERFALL_EXE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(30)  # Wait for the game window/process to stabilize

        logging.info("Changing Daggerfall Unity audio output device...")
        set_daggerfall_audio_device()

        logging.info("Skipping intro video...")
        pyautogui.press("space")
        time.sleep(2)

        logging.info("Opening load game menu...")
        pyautogui.press("l")
        time.sleep(2)

        logging.info("Loading last save...")
        pyautogui.press("enter")
        time.sleep(25)  # Allow save to load fully

        pyautogui.press("`")  # Open the console (tilde key)

        # logging.info("Enabling God Mode...")
        # time.sleep(1)
        # pyautogui.write("tgm")
        # time.sleep(1)
        # pyautogui.press("enter")
        # time.sleep(1)

        logging.info("Setting jump to 50...")
        pyautogui.write("set_jump 50")
        time.sleep(1)
        pyautogui.press("enter")
        time.sleep(1)

        logging.info("Toggling AI...")
        pyautogui.write("tai")
        time.sleep(1)
        pyautogui.press("enter")
        time.sleep(1)

        logging.info("Toggling air control...")
        pyautogui.write("tac")
        time.sleep(1)
        pyautogui.press("enter")
        time.sleep(1)

        logging.info("Starting song shuffle...")
        pyautogui.write("song shuffle all")
        time.sleep(1)
        pyautogui.press("enter")
        time.sleep(1)

        pyautogui.press("`")  # Close the console

        time.sleep(1)
        logging.info("Pressing \\ to enable auto-walk...")
        pyautogui.press("\\")
        time.sleep(2)

        # Mark DFU ready at the very end
        READY_FLAG.parent.mkdir(parents=True, exist_ok=True)
        READY_FLAG.write_text("ready", encoding="utf-8")
        logging.info(f"Wrote DFU ready flag: {READY_FLAG}")

    except Exception as e:
        logging.error(f"Failed to start Daggerfall Unity: {e}")

# Function to set Daggerfall Unity's audio output device using SoundVolumeView
def set_daggerfall_audio_device():
    try:
        command = [SOUNDVOLUMEVIEW_PATH, "/SetAppDefault", VIRTUAL_AUDIO_DEVICE, "1", "DaggerfallUnity.exe"]
        subprocess.run(command, shell=True)
        logging.info(f"Set Daggerfall Unity audio to {VIRTUAL_AUDIO_DEVICE} using SoundVolumeView.")
    except Exception as e:
        logging.error(f"Failed to set audio output device: {e}")

# Function to start OBS minimized and begin streaming
def start_obs():
    if is_process_running("obs64.exe"):
        logging.info("OBS is already running.")
        return

    logging.info("Starting OBS Studio (minimized) and streaming...")
    try:
        # Close any existing OBS crash/safe mode prompt
        close_obs_safe_mode_prompt()

        # Launch OBS with --multi to avoid instance conflicts
        subprocess.Popen(
            [OBS_EXE, "--startstreaming", "--multi"],
            cwd=os.path.dirname(OBS_EXE),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False
        )

        time.sleep(5)  # Give OBS time to start
        handle_obs_safe_mode_prompt()

    except Exception as e:
        logging.error(f"Failed to start OBS: {e}")

# Function to close any existing OBS safe mode/crash prompt before starting OBS
def close_obs_safe_mode_prompt():
    time.sleep(1)
    for window in gw.getAllWindows():
        if "OBS Studio" in window.title and "Warning" in window.title:
            logging.info("Closing existing OBS warning dialog...")
            window.activate()
            time.sleep(0.5)
            pyautogui.press("enter")
            time.sleep(1)

# Function to handle the "Run in Safe Mode?" prompt if it appears
def handle_obs_safe_mode_prompt():
    time.sleep(3)
    for window in gw.getAllWindows():
        if "OBS Studio" in window.title and "Safe Mode" in window.title:
            logging.info("Safe Mode prompt detected! Selecting 'Run Normally'...")
            window.activate()
            time.sleep(0.5)
            pyautogui.press("tab")
            pyautogui.press("enter")
            time.sleep(1)

# === Wait/gate helpers ===
def wait_for_daggerfall_ready(timeout=240):
    start = time.time()
    while time.time() - start < timeout:
        if READY_FLAG.exists():
            logging.info("DFU ready flag detected.")
            return True
        time.sleep(1)
    return False

def ensure_dfu_ready(timeout=240):
    # Clear stale flag, (re)start DFU if not running, then wait for readiness
    try:
        READY_FLAG.unlink(missing_ok=True)
    except Exception:
        pass

    if not is_process_running("DaggerfallUnity.exe"):
        start_daggerfall()
    else:
        # If already running, make sure the flag exists so the wait doesn't stall
        try:
            READY_FLAG.parent.mkdir(parents=True, exist_ok=True)
            READY_FLAG.write_text("ready", encoding="utf-8")
            logging.info(f"Wrote DFU ready flag (already running): {READY_FLAG}")
        except Exception as e:
            logging.error(f"Failed to write DFU ready flag: {e}")

    ok = wait_for_daggerfall_ready(timeout=timeout)
    if not ok:
        logging.error("Timed out waiting for DFU readiness")
    return ok

def run_bot_supervised():
    base = os.path.dirname(__file__)
    # Prefer pythonw.exe to avoid a console window (fallback to python.exe + NO_WINDOW)
    pyw = os.path.join(base, "daggerwalk_venv", "Scripts", "pythonw.exe")
    pye = os.path.join(base, "daggerwalk_venv", "Scripts", "python.exe")
    exe = pyw if os.path.exists(pyw) else pye
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if exe == pye else 0

    bot = os.path.join(base, "daggerwalk_twitch_bot.py")

    while True:
        # Always ensure DFU is staged before (re)starting the bot
        ensure_dfu_ready(timeout=240)

        logging.info(f"Launching Twitch bot ({'pythonw' if exe==pyw else 'python + NO_WINDOW'})...")
        p = subprocess.Popen([exe, bot], cwd=base, creationflags=flags)
        rc = p.wait()
        logging.warning(f"Bot exited with code {rc}. Relaunching in 5s...")
        time.sleep(5)

# Main execution loop
if __name__ == "__main__":
    logging.info("=== Starting DaggerWalk Automation ===")

    # try:
    #     logging.info("Creating YouTube broadcast...")
    #     youtube_create_broadcast.create_daily_broadcast()
    # except Exception as e:
    #     logging.error(f"Failed to create YouTube broadcast: {e}")
    
    start_obs()
    # First-time DFU setup and every restart are gated inside the supervisor loop
    run_bot_supervised()
