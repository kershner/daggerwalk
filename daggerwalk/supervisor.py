import subprocess
import time
import psutil
import logging
import os
import argparse
import pyautogui
import pygetwindow as gw

from .paths import LOG_FILE, READY_FLAG, REPO_ROOT, ensure_runtime_dir

# Configure logging
ensure_runtime_dir()
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(console_handler)

def first_existing_path(*paths):
    return next((path for path in paths if os.path.isfile(path)), paths[0])


DAGGERFALL_EXE = first_existing_path(
    r"C:\Daggerwalk\DaggerfallUnity\DaggerfallUnity.exe",  # production
    r"C:\DaggerfalUnity\1.1.1\DaggerfallUnity.exe",       # local dev
)
OBS_EXE = r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"
VIRTUAL_AUDIO_DEVICE = "VB-Audio Virtual Cable"
SOUNDVOLUMEVIEW_PATH = first_existing_path(
    r"C:\Daggerwalk\Utilities\SoundVolumeView\SoundVolumeView.exe",  # production
    r"C:\Daggerwalk\SoundVolumeView\SoundVolumeView.exe",            # local dev
)
SAVE_LOAD_WAIT_SECONDS = 45
DEV_SAVE_LOAD_WAIT_SECONDS = SAVE_LOAD_WAIT_SECONDS / 2


def save_load_wait_seconds(control_mode):
    return DEV_SAVE_LOAD_WAIT_SECONDS if control_mode == "dev" else SAVE_LOAD_WAIT_SECONDS

# Function to check if a process is running
def is_process_running(process_name):
    for proc in psutil.process_iter(["name"]):
        if process_name.lower() in (proc.info["name"] or "").lower():
            return True
    return False

# Function to terminate a process by name
def start_daggerfall(control_mode="twitch"):
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
        load_wait = save_load_wait_seconds(control_mode)
        logging.info("Waiting %.1fs for the save to load...", load_wait)
        time.sleep(load_wait)

        time.sleep(1)
        pyautogui.press("`")  # Open the console (tilde key)
        time.sleep(1)

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

        logging.info("Enabling no-target mode...")
        pyautogui.write("nt")
        time.sleep(1)
        pyautogui.press("enter")
        time.sleep(1)

        logging.info("Toggling air control...")
        pyautogui.write("tac")
        time.sleep(1)
        pyautogui.press("enter")
        time.sleep(1)

        logging.info("Starting song shuffle...")
        pyautogui.write("song shuffle off")
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

def ensure_dfu_ready(timeout=240, control_mode="twitch"):
    # Clear stale flag, (re)start DFU if not running, then wait for readiness
    try:
        READY_FLAG.unlink(missing_ok=True)
    except Exception:
        pass

    if not is_process_running("DaggerfallUnity.exe"):
        start_daggerfall(control_mode)
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

def run_control_supervised(control_mode):
    base = str(REPO_ROOT)
    pyw = os.path.join(base, "daggerwalk_venv", "Scripts", "pythonw.exe")
    pye = os.path.join(base, "daggerwalk_venv", "Scripts", "python.exe")

    if control_mode == "dev":
        exe = pye
        command = [exe, "-m", "daggerwalk.dev_server"]
        label = "dev server"
        flags = 0
    else:
        # Prefer pythonw.exe for the production bot to avoid a second console.
        exe = pyw if os.path.exists(pyw) else pye
        command = [exe, "-m", "daggerwalk.twitch_bot"]
        label = "Twitch bot"
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if exe == pye else 0

    while True:
        # Both modes pass through the same game startup/readiness gate.
        ensure_dfu_ready(timeout=240, control_mode=control_mode)

        logging.info(f"Launching {label}...")
        process = subprocess.Popen(command, cwd=base, creationflags=flags)
        rc = process.wait()
        logging.warning(f"{label.title()} exited with code {rc}. Relaunching in 5s...")
        time.sleep(5)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["dev", "twitch"], default="twitch")
    return parser.parse_args()

# Main execution loop
if __name__ == "__main__":
    args = parse_args()
    logging.info("=== Starting DaggerWalk Automation ===")
    logging.info(f"Control mode: {args.mode}")

    if args.mode == "twitch":
        start_obs()
    else:
        logging.info("Dev mode — skipping OBS and Twitch connectivity.")

    # First-time DFU setup and every restart are gated inside the supervisor loop
    run_control_supervised(args.mode)
