import subprocess
import time
import psutil
import logging
import os
import pyautogui
import pygetwindow as gw

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

# Function to check if a process is running
def is_process_running(process_name):
    for proc in psutil.process_iter(["name"]):
        if process_name.lower() in proc.info["name"].lower():
            return True
    return False

# Function to terminate a process by name
def terminate_process(process_name):
    for proc in psutil.process_iter(["name"]):
        if process_name.lower() in proc.info["name"].lower():
            logging.info(f"Terminating {process_name} (PID: {proc.pid})...")
            proc.terminate()
            try:
                proc.wait(timeout=5)  # Wait up to 5 seconds for process to close
            except psutil.TimeoutExpired:
                logging.warning(f"Force killing {process_name}...")
                proc.kill()

def start_daggerfall():
    if is_process_running("DaggerfallUnity.exe"):
        logging.info("Daggerfall Unity is already running.")
        return

    logging.info("Starting Daggerfall Unity...")
    try:
        subprocess.Popen(
            DAGGERFALL_EXE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(25)  # Wait for the game to start

        logging.info("Changing Daggerfall Unity audio output device...")
        set_daggerfall_audio_device()
        
        time.sleep(10)

        logging.info("Skipping intro video...")
        pyautogui.press("space")  # Press Space to skip intro
        time.sleep(2)

        logging.info("Opening load game menu...")
        pyautogui.press("l")  # Press L to open load game menu
        time.sleep(2)

        logging.info("Loading last save...")
        pyautogui.press("enter")  # Press Enter to load the save
        time.sleep(20)  # Wait for the save to load
        
        pyautogui.press("`")  # Open the console (tilde key)
        
        logging.info("Enabling God Mode...")
        time.sleep(1)
        pyautogui.write("tgm")  # Type 'tgm' to enable God Mode
        time.sleep(1)
        pyautogui.press("enter")  # Press Enter to confirm
        time.sleep(1)

        logging.info("Setting jump to 50...")
        pyautogui.write("set_jump 50")
        time.sleep(1)
        pyautogui.press("enter")  # Press Enter to confirm
        time.sleep(1)

        logging.info("Toggling AI...")
        pyautogui.write("tai")
        time.sleep(1)
        pyautogui.press("enter")  # Press Enter to confirm
        time.sleep(1)

        logging.info("Toggling air control...")
        pyautogui.write("tac")
        time.sleep(1)
        pyautogui.press("enter")  # Press Enter to confirm
        time.sleep(1)

        logging.info("Starting song shuffle...")
        pyautogui.write("song shuffle all")
        time.sleep(1)
        pyautogui.press("enter")  # Press Enter to confirm
        time.sleep(1)

        pyautogui.press("`")  # Close the console

        time.sleep(1) 
        logging.info("Pressing \ to enable auto-walk...")
        pyautogui.press("\\")
        time.sleep(2)  # Give it a moment before moving the window

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
        obs_directory = os.path.dirname(OBS_EXE)

        # Close any existing OBS crash/safe mode prompt
        close_obs_safe_mode_prompt()

        # Launch OBS with --multi to avoid instance conflicts
        subprocess.Popen(
            [OBS_EXE, "--startstreaming", "--multi"],
            cwd=os.path.dirname(OBS_EXE),  # Ensure correct working directory
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False  # Avoids command shell issues
        )

        
        time.sleep(5)  # Give OBS time to start

        # Handle the "Run in Safe Mode?" prompt if it appears
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
            pyautogui.press("enter")  # Close it by pressing Enter
            time.sleep(1)

# Function to handle the "Run in Safe Mode?" prompt if it appears
def handle_obs_safe_mode_prompt():
    time.sleep(3)  # Wait to see if the prompt appears
    for window in gw.getAllWindows():
        if "OBS Studio" in window.title and "Safe Mode" in window.title:
            logging.info("Safe Mode prompt detected! Selecting 'Run Normally'...")
            window.activate()
            time.sleep(0.5)
            pyautogui.press("tab")  # Move selection to "Run Normally"
            pyautogui.press("enter")  # Confirm selection
            
            time.sleep(1)

def start_bot_monitor():
    logging.info("Starting Twitch bot...")
    subprocess.Popen([r"daggerwalk_venv\Scripts\python.exe", "daggerwalk_bot_monitor.py"], cwd=os.path.dirname(__file__))

def start_bot_monitor():
    # Check if the bot monitor batch file is already running
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline")
            if cmdline and "start_daggerwalk_bot_monitor.bat" in " ".join(cmdline).lower():
                logging.info("Bot monitor already running. Skipping.")
                return
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    logging.info("Starting bot monitor via batch script...")
    subprocess.Popen(
        ["start", "", "start_daggerwalk_bot_monitor.bat"],
        shell=True,
        cwd=os.path.dirname(__file__)
    )

# Main execution loop
if __name__ == "__main__":
    logging.info("=== Starting DaggerWalk Automation ===")

    start_obs()
    start_daggerfall()
    start_bot_monitor()
    
    logging.info("DaggerWalk is now running! (Press Ctrl+C to stop)")