import subprocess
import time
import socket
import logging
import os
import signal
import sys

# Configure logging
logging.basicConfig(
    filename="connection_monitor.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(console_handler)

# Configuration
VENV_PYTHON_PATH = "daggerwalk_venv\\Scripts\\python.exe"  # Python interpreter in virtual environment
BOT_SCRIPT_PATH = "daggerwalk_twitch_bot.py"
CHECK_INTERVAL = 20  # Seconds between connectivity checks
TEST_HOST = "8.8.8.8"  # Google DNS to check connectivity
TEST_PORT = 53  # DNS port

bot_process = None

def check_internet():
    """Check if internet is connected by trying to reach Google DNS"""
    try:
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((TEST_HOST, TEST_PORT))
        return True
    except:
        return False

def start_bot():
    """Start the Twitch bot script"""
    global bot_process
    logging.info("Starting Twitch bot...")
    try:
        # Use Python from the virtual environment
        bot_process = subprocess.Popen(
            [VENV_PYTHON_PATH, BOT_SCRIPT_PATH]
        )
        logging.info(f"Bot started with PID: {bot_process.pid}")
    except Exception as e:
        logging.error(f"Failed to start bot: {e}")

def stop_bot():
    """Stop the Twitch bot script"""
    global bot_process
    if bot_process:
        logging.info(f"Stopping bot (PID: {bot_process.pid})...")
        try:
            bot_process.terminate()
            time.sleep(3)  # Simple wait instead of bot_process.wait with timeout
            if bot_process.poll() is None:  # If still running
                bot_process.kill()
        except Exception as e:
            logging.error(f"Error stopping bot: {e}")
        bot_process = None

# Signal handler
def cleanup_and_exit(signum, frame):
    logging.info("Monitor script terminating...")
    stop_bot()
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, cleanup_and_exit)
signal.signal(signal.SIGTERM, cleanup_and_exit)

# Main loop
if __name__ == "__main__":
    logging.info("=== Starting Connection Monitor ===")
    
    # Initial check
    was_connected = check_internet()
    if was_connected:
        start_bot()
    
    try:
        while True:
            is_connected = check_internet()
            
            if is_connected and not was_connected:
                # Internet just connected
                logging.info("Internet connection detected!")
                start_bot()
                was_connected = True
            elif not is_connected and was_connected:
                # Internet just disconnected
                logging.info("Internet connection lost!")
                stop_bot()
                was_connected = False
            
            time.sleep(CHECK_INTERVAL)
    except Exception as e:
        logging.error(f"Monitor script error: {e}")
        stop_bot()  # Make sure we clean up