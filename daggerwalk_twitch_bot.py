from datetime import datetime, timedelta, timezone, date
from urllib.parse import quote_plus
from twitchio.ext import commands
import pygetwindow as gw
from enum import Enum
import subprocess
import pywinauto
import aiofiles
import requests
import logging
import aiohttp
import asyncio
import pytz
import json
import time
import os

logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename="daggerwalk.log",
    filemode="a"  # Append mode
)


class GameKeys(Enum):
    """Mapping of game actions to keyboard inputs"""
    WALK = "\\"
    FORWARD = "w"
    BACK = "s"
    LEFT = "a"
    RIGHT = "d"
    UP = "{INSERT}"
    DOWN = "{DELETE}"
    JUMP = "{SPACE}"
    MAP = "v"
    SAVE = "{F9}"
    LOAD = "{F11}"
    CONSOLE = "`"
    ESC = "{ESC}"
    USE = "k"
    CAMERA = "O"

class Config:
    """Bot configuration settings"""
    PARAMS_FILE = "parameters.json"
    TWITCH_CHANNEL = "daggerwalk"
    BOT_USERNAME = "daggerwalk_bot"
    REFRESH_INTERVAL = 300  # 5 minutesa
    AUTOSAVE_INTERVAL = 600  # 10 minutes
    CHAT_DELAY = 1.5  # seconds
    VOTING_DURATION = 30  # seconds
    AUTHORIZED_USERS = ["billcrystals", "daggerwalk", "daggerwalk_bot"]
    MAX_INPUT_REPEATS = 100
    DJANGO_BASE_API_URL = "https://kershner.org/api/daggerwalk"
    DJANGO_LOG_URL = "https://kershner.org/daggerwalk/log/"
    
    ACTIVE_MODS = [
        "World of Daggerfall", "Interesting Eroded Terrains",
        "Wilderness Overhaul", "Basic Roads", "Dynamic Skies", "Real Grass",
        "Birds in Daggerfall", "HUD Be Gone", "Future Shock Weapons",
        "Immersive Footsteps", "Eye of the Beholder", "Render Distance Expander"
    ]

    WEATHER_TYPES_MAP = {
        "clear": 0,
        "cloudy": 1,
        "overcast": 2,
        "foggy": 3,
        "rainy": 4,
        "thunderstorm": 5,
        "snowy": 6,
    }

    WEATHER_EMOJIS = {"Sunny": "☀️", "Clear": "🌙", "Overcast": "🌥️", "Cloudy": "☁️", "Foggy": "🌫️",
                        "Rainy": "🌧️", "Snowy": "🌨️", "Thunderstorm": "⛈️"}
    
    SEASON_EMOJIS = {"Winter": "☃️", "Spring": "🌸", "Summer": "🌻", "Autumn": "🍂"}

    _params = None

    @classmethod
    def load_params(cls):
        """Load API keys and credentials from parameters file (only once)"""
        if cls._params is None:  # Load only if not already loaded
            if not os.path.exists(cls.PARAMS_FILE):
                logging.error(f"Missing {cls.PARAMS_FILE}")
                exit(1)
            with open(cls.PARAMS_FILE, "r") as file:
                cls._params = json.load(file)
        
        return cls._params
    
    @classmethod
    def get_oauth(cls):
        """Return Twitch OAuth credentials"""
        params = cls.load_params()
        return params.get("CLIENT_ID", ""), params.get("OAUTH_TOKEN", "")

    @classmethod
    def get_api_key(cls):
        """Return Daggerwalk API key"""
        params = cls.load_params()
        return params.get("daggerwalk_api_key", "")

def send_game_input(key: str, repeat: int = 1, delay: float = 0.2):
    """Send keyboard input to Daggerfall Unity window"""
    try:
        # Create a fresh Application instance each time
        window = next((w for w in gw.getWindowsWithTitle("Daggerfall Unity") 
                      if w.title == "Daggerfall Unity"), None)
                      
        if not window:
            logging.warning("Game window not found")
            return
            
        # Force a completely new connection every time, with no caching
        app = pywinauto.Application(backend="win32").connect(handle=window._hWnd)
        dlg = app.window(handle=window._hWnd)
        
        logging.info(f"Sending input: {key} ({repeat} times)")
        for _ in range(repeat):
            dlg.send_keystrokes(key)
            time.sleep(delay)
            
    except Exception as e:
        logging.error(f"Input error: {e}")

def post_to_django(data, reset=False):
    """Post game state data to Django endpoint in background"""
    API_KEY = Config.get_api_key()

    try:
        payload = {
            "worldX": int(data.get('worldX', 0)),
            "worldZ": int(data.get('worldZ', 0)),
            "mapPixelX": int(data.get('mapPixelX', 0)),
            "mapPixelY": int(data.get('mapPixelY', 0)),
            "region": data.get('region', 'Unknown'),
            "location": data.get('location', 'Unknown'),
            "locationType": data.get('locationType', 'Unknown'),
            "playerX": float(data.get('playerX', 0)),
            "playerY": float(data.get('playerY', 0)),
            "playerZ": float(data.get('playerZ', 0)),
            "date": data.get('date', ''),
            "weather": data.get('weather', 'Unknown'),
            "season": data.get('season', 'Unknown'),
            "currentSong": data.get('currentSong', None),
            "reset": reset,
            "chat_logs": []
        }

        # Read chat command logs and include in payload
        log_file = "chat_commands_log.txt"
        if os.path.exists(log_file):
            with open(log_file, "r") as f:
                payload["chat_logs"] = f.read().strip().splitlines()

        logging.info(f"Posting to Django: {Config.DJANGO_LOG_URL}")

        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        response = requests.post(
            Config.DJANGO_LOG_URL,
            json=payload,
            headers=headers,
            timeout=15
        )
        
        if response.status_code == 201:
            logging.info(f"Successfully posted to Django. Response: {response.json()}")
            # Clear chat log file after success
            open(log_file, "w").close()

            # Add next_log_time to the local state
            try:
                est = pytz.timezone("US/Eastern")
                next_time = datetime.now(est) + timedelta(minutes=5)
                if hasattr(bot_instance := globals().get("bot"), "_update_state"):
                    bot_instance._update_state("next_log_time", next_time)
            except Exception as e:
                logging.error(f"Failed to update next_log_time: {e}")
        else:
            logging.warning(f"Django post returned non-201 status: {response.status_code}. Response: {response.text}")

        return response            

    except requests.Timeout:
        logging.error(f"Timeout posting to Django after 15s: {Config.DJANGO_LOG_URL}")
    except requests.ConnectionError:
        logging.error(f"Connection error posting to Django: {Config.DJANGO_LOG_URL}")
    except Exception as e:
        logging.error(f"Error posting to Django: {str(e)}")

class DaggerfallBot(commands.Bot):
    def __init__(self):
        client_id, oauth = Config.get_oauth()
        super().__init__(token=oauth, prefix="!", initial_channels=[Config.TWITCH_CHANNEL])
        
        self._bot_started_at_monotonic = time.monotonic()
        self._latest_response_data = None
        self._latest_response_at = None
        self.last_autosave = datetime.now(timezone.utc)
        self.voting_active = False
        self.current_vote_type = None
        self.current_vote_message = None
        self.votes = {}
        self._state_ready = asyncio.Event()
        self._startup_tasks_started = False
        self._last_completed_quest_id = None

        self.state = {
            "song": None,
            "song_category": "all",
            "gravity": 20,
            "levitate": "off",
            "ai_enabled": False,
            "camera_mode": "third",
            "next_log_time": None,
        }
        
        self.votable_commands = {
            "reset": "reset to last known location",
            "song": "change the background music",
            "weather": "change the weather",
            "levitate": "start or stop levitating",
            "toggle_ai": "toggle enemy AI",
            "exit": "teleport out of the current building",
            "gravity": "set gravity level",
            "playvid": "play an in-game video",
            "camera": "toggle third-person camera"
        }

    def _update_state(self, key, value):
        """Safely update a local state field and log the change."""
        if key in self.state:
            old = self.state[key]
            self.state[key] = value
            logging.info(f"State updated: {key} = {value} (was {old})")
        else:
            logging.warning(f"Attempted to set unknown state key: {key}")

    async def event_ready(self):
        logging.info(f"Bot online as {self.nick}")
        if self._startup_tasks_started:
            logging.info("event_ready called again — tasks already started; ignoring.")
            return
        self._startup_tasks_started = True
        
        self.refresh_task = asyncio.create_task(self.data_refresh_loop())
        self.autosave_task = asyncio.create_task(self.autosave_loop())
        self.message_task = asyncio.create_task(self.message_scheduler())
        self.crash_monitor_task = asyncio.create_task(self.crash_monitor())
        self.side_effects_task = asyncio.create_task(self.side_effects_loop())
        self.local_state_refresh_task = asyncio.create_task(self.local_state_refresh_loop())

    async def message_scheduler(self):
        """Schedules periodic info (5m), help (20m), and quest (25m) messages."""
        logging.info("Starting message scheduler")

        # Wait until we have first successful refresh so we don't announce early/empty
        await self._state_ready.wait()

        INFO_INTERVAL = 300      # 5 minutes
        HELP_INTERVAL = 1200     # 20 minutes
        QUEST_INTERVAL = 1500    # 25 minutes

        HELP_OFFSET = 360        # 6 minutes after start
        QUEST_OFFSET = 120       # 2 minutes after start (staggered to avoid overlaps)

        async def run_periodic_message(message_coro, interval, initial_delay=0):
            if initial_delay > 0:
                await asyncio.sleep(initial_delay)
            while True:
                try:
                    await message_coro()
                except Exception as e:
                    logging.error(f"periodic message error: {e}")
                await asyncio.sleep(interval)

        # Small initial delay for !info so it doesn't race with manual commands at startup
        info_task = asyncio.create_task(
            run_periodic_message(self.game_info, INFO_INTERVAL, initial_delay=10)
        )
        help_task = asyncio.create_task(
            run_periodic_message(self.help, HELP_INTERVAL, initial_delay=HELP_OFFSET)
        )
        quest_task = asyncio.create_task(
            run_periodic_message(self.quest, QUEST_INTERVAL, initial_delay=QUEST_OFFSET)
        )

        await asyncio.gather(info_task, help_task, quest_task)


    async def data_refresh_loop(self):
        """Only refresh cached log/quest data; do NOT run side-effects here."""
        logging.info("Starting data refresh loop")
        first_success = False
        while True:
            try:
                data = await self.get_map_json_data()
                response = await asyncio.to_thread(post_to_django, data)
                if response and response.status_code == 201:
                    new_data = response.json()
                    
                    # Check for NEW quest completion BEFORE updating cache
                    await self._check_and_announce_quest_completion(new_data)
                    
                    # Then update cache
                    self._latest_response_data = new_data
                    self._latest_response_at = datetime.now(timezone.utc)

                    if not first_success:
                        first_success = True
                        self._state_ready.set()  # unblocks scheduler/commands that want initial state

                # Stuck check (run on a calm interval, not on every command/refresh)
                await self.check_if_bot_is_stuck()
            except Exception as e:
                logging.error(f"data_refresh_loop error: {e}")
            await asyncio.sleep(Config.REFRESH_INTERVAL)

    async def _check_and_announce_quest_completion(self, new_data):
        """Check if quest was completed and announce if so"""
        try:
            quest_completed = new_data.get('quest_completed', False)
            completed_quest = new_data.get('completed_quest') or {}
            completed_quest_id = completed_quest.get('id') if completed_quest else None
            
            logging.info(f"Quest check - completed: {quest_completed}, ID: {completed_quest_id}, last ID: {getattr(self, '_last_completed_quest_id', None)}")
            
            if (quest_completed and completed_quest_id and 
                completed_quest_id != getattr(self, '_last_completed_quest_id', None)):
                
                completion_line, _ = self._format_quest_lines_from_response(new_data)
                if completion_line and self.connected_channels:
                    await self.connected_channels[0].send(completion_line)
                    self._last_completed_quest_id = completed_quest_id
                    logging.info(f"Quest completion announced: {completed_quest_id}")
                else:
                    logging.warning(f"Quest completed but no completion_line generated or no channels")
            
        except Exception as e:
            logging.error(f"_check_and_announce_quest_completion error: {e}")

    async def side_effects_loop(self):
        """Run operational side-effects on a steady cadence, decoupled from refresh."""
        # Wait until we have at least one successful refresh
        await self._state_ready.wait()
        logging.info("Starting side effects loop")

        last_shutdown_notice_date = None

        while True:
            try:
                # Nightly shutdown notice: ensure once-per-day semantics
                est = pytz.timezone("US/Eastern")
                now_est = datetime.now(est)
                midnight_next = (now_est + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                minutes_until = int((midnight_next - now_est).total_seconds() // 60)

                if 0 < minutes_until <= 10:
                    if last_shutdown_notice_date != now_est.date():
                        last_shutdown_notice_date = now_est.date()
                        if self.connected_channels:
                            await self.connected_channels[0].send(
                                f"🛌 The Walker will rest for the night in {minutes_until} minutes, "
                                "at midnight EST. They'll be back in the morning!"
                            )

            except Exception as e:
                logging.error(f"side_effects_loop error: {e}")

            # Tweak interval as desired
            await asyncio.sleep(60)

    async def local_state_refresh_loop(self):
        """Check MapData.json periodically for song changes."""
        await self._state_ready.wait()
        logging.info("Starting local state refresh loop")

        # Ensure track map is loaded
        if not hasattr(self, "_track_map"):
            music_data_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "list_music_tracks.json")
            self._music_tracks = await self.load_json_async(music_data_path)
            self._track_map = {track["TrackName"]: track["TrackID"] for track in self._music_tracks}

        last_song = self.state.get("song")
        last_weather = self.state.get("weather")

        while True:
            try:
                data = await self.get_map_json_data()
                new_song_name = data.get("currentSong")

                if new_song_name and new_song_name != last_song:
                    track_id = self._track_map.get(new_song_name)
                    song_display = f"{new_song_name} (Track {track_id})" if track_id is not None else new_song_name
                    self._update_state("song", song_display)
                    last_song = new_song_name
                    logging.info(f"Detected new song: {song_display}")

            except Exception as e:
                logging.error(f"local_state_refresh_loop error: {e}")

            await asyncio.sleep(30)

    async def refresh_now(self):
        """One-shot refresh of cached data without chat output."""
        try:
            data = await self.get_map_json_data()
            response = await asyncio.to_thread(post_to_django, data)
            if response and response.status_code == 201:
                self._latest_response_data = response.json()
                self._latest_response_at = datetime.now(timezone.utc)
                return True
        except Exception as e:
            logging.error(f"refresh_now error: {e}")
        return False

    async def autosave_loop(self):
        """Periodic game auto-save"""
        logging.info("Starting autosave loop")
        while True:
            try:
                await asyncio.sleep(Config.AUTOSAVE_INTERVAL)
                await self.save_game()
                self.last_autosave = datetime.now(timezone.utc)
                logging.info(f"Auto-saved at {self.last_autosave}")
            except Exception as e:
                logging.error(f"Autosave error: {e}")

    def is_daggerfall_running(self):
        """Check if Daggerfall Unity process is running using built-in tasklist"""
        try:
            # logging.info("Checking running processes via tasklist...")
            output = subprocess.check_output("tasklist", shell=True, text=True)
            lines = output.strip().splitlines()
            process_names = [line.split()[0] for line in lines[3:] if line]  # Skip header lines
            return any("DaggerfallUnity.exe" == name for name in process_names)

        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to run tasklist: {e}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error in is_daggerfall_running: {e}")
            return False

    async def crash_monitor(self):
        logging.info("Starting crash monitor loop...")
        while True:
            await asyncio.sleep(10)
            if not self.is_daggerfall_running():
                logging.error("Daggerfall Unity process not found — assuming crash")
                if self.connected_channels:
                    try:
                        await self.connected_channels[0].send(
                            "⚠️ Daggerfall Unity has crashed! Restarting the stack, back in a sec..."
                        )
                    except Exception:
                        pass

                os._exit(100)  # special exit code that means "DFU crashed"

    async def log_chat_command(self, username, command, args):
        """Append chat commands to a local log file"""
        timestamp = datetime.now(timezone.utc).isoformat()
        entry = f"{timestamp} | {username} | {command} | {' '.join(args)}\n"
        try:
            async with aiofiles.open("chat_commands_log.txt", mode="a") as f:
                await f.write(entry)
        except Exception as e:
            logging.error(f"Failed to log chat command: {e}")
    
    async def event_message(self, message):
        """Handle incoming chat messages and commands"""
        if not message.author:
            return

        logging.info(f"Chat: {message.author.name}: {message.content}")
        
        parts = message.content.split()
        if not parts or not parts[0].startswith("!"):
            return
            
        command = parts[0][1:].lower()  # Remove ! prefix
        args = parts[1:] if len(parts) > 1 else []

        # Log the command asynchronously to a local file
        try:
            ts = datetime.now(timezone.utc).isoformat()
            logline = f"{ts} | {message.author.name} | {command} | {' '.join(args)}\n"
            async with aiofiles.open("chat_commands_log.txt", mode="a") as f:
                await f.write(logline)
        except Exception as e:
            logging.error(f"Failed to log chat command: {e}")

        # Handle voting commands
        if command in self.votable_commands:
            if command == "song" and not self.validate_song_arg(args)[0]:
                await message.channel.send(self.validate_song_arg(args)[1])
                return
            await self.start_vote(message, command)
            return

        if command in ["yes", "no"] and self.voting_active:
            await self.cast_vote(message.author.name, command)
            return

        # Map commands to methods
        command_map = {
            "walk": lambda: self.send_movement(GameKeys.WALK),
            "back": lambda: self.handle_movement_arg_required(message, GameKeys.BACK, args),
            "forward": lambda: self.handle_movement_arg_required(message, GameKeys.FORWARD, args),
            "left": lambda: self.handle_movement_arg_required(message, GameKeys.LEFT, args),
            "right": lambda: self.handle_movement_arg_required(message, GameKeys.RIGHT, args),
            "up": lambda: self.send_movement(GameKeys.UP, args),
            "down": lambda: self.send_movement(GameKeys.DOWN, args),
            "jump": lambda: self.send_movement(GameKeys.JUMP, repeat=10),
            "stop": lambda: self.handle_movement_arg_required(message, GameKeys.BACK, ["1"]),
            "use": lambda: self.send_movement(GameKeys.USE),
            "map": self.toggle_map,
            "camera": self.toggle_camera,
            "bighop": self.bighop,
            "shotgun": self.use_shotgun,
            "save": lambda: self.admin_command(message, self.save_game),
            "load": lambda: self.admin_command(message, self.load_game),
            "modlist": self.modlist,
            "help": self.help,
            "exec": lambda: self.admin_command(message, lambda: self.exec_command(args)),
            "esc": lambda: self.send_movement(GameKeys.ESC, args),
            "killall": self.killall,
            "info": self.game_info,
            "more": self.more_commands,
            "quest": self.quest,
            "state": self.show_state,
        }

        if command in command_map:
            await command_map[command]()

    async def admin_command(self, message, cmd):
        """Execute admin-only commands"""
        if message.author.name.lower() in Config.AUTHORIZED_USERS:
            await cmd()

    async def handle_movement_arg_required(self, message, key: GameKeys, args):
        """Require an integer arg for certain movement commands; otherwise prompt."""
        if not args:
            await message.channel.send('Enter the movement command followed by n (1-100), ex - !left 20')
            return
        await self.send_movement(key, args)

    async def send_movement(self, key: GameKeys, args=None, repeat=1):
        """Handle movement and action commands"""
        if args and args[0].isdigit():
            repeat = min(max(int(args[0]), 1), Config.MAX_INPUT_REPEATS)
        logging.info(f"Sending movement: {key.name} ({repeat} times)")
        send_game_input(key.value, repeat=repeat, delay=0.15)

    def validate_song_arg(self, args):
        """Validate song selection"""
        default_msg = f'Specify song number (-1 to 131), "category" or "random".'
        
        if not args:
            return False, default_msg
                
        song = args[0].lower()
        
        # Check for special string arguments first
        if song == "category" or song == "random":
            return True, None
                
        # Then try to convert to integer
        try:
            song_num = int(song)
            if -1 <= song_num <= 131:
                return True, None
            return False, default_msg
        except ValueError:
            # If it's not a valid string or convertible to int, it's invalid
            return False, default_msg
        
    def validate_weather_arg(self, args):
        """Validate weather selection"""
        if not args or args[0].lower() not in Config.WEATHER_TYPES_MAP:
            return False, f"Specify weather type: {', '.join(Config.WEATHER_TYPES_MAP.keys())}"
        return True, None
    
    def validate_levitate_args(self, args):
        """Validate levitate selection"""
        if not args or args[0].lower() not in ["on", "off"]:
            return False, 'Specify levitate setting: "on" or "off"'
        return True, None
    
    def validate_gravity_args(self, args):
        """Validate gravity setting"""
        if not args or not args[0].isdigit() or not (0 <= int(args[0]) <= 20):
            return False, 'Set gravity level: 0–20 (0=low, 20=default)'
        return True, None
    
    def validate_playvid_args(self, args):
        if not args or not args[0].isdigit():
            return False, "Usage: !playvid <0–15>"
        n = int(args[0])
        if 0 <= n <= 15:
            return True, None
        return False, "Usage: !playvid <0–15>"

    async def start_vote(self, message, vote_type):
        if self.voting_active:
            await message.channel.send("A vote is already in progress!")
            return

        # Special handling to validate command args
        if vote_type == "song":
            args = message.content.split()[1:] if len(message.content.split()) > 1 else []
            if args and args[0].lower() == "category":
                # If only "category" is provided without specific categories
                if len(args) == 1:
                    await message.channel.send("Choose categories for the song shuffle. Options: world, dungeon, misc, battle, all. Multiple categories supported. Ex: !song category world misc")
                    return
                # If they provided categories, proceed with vote for category shuffle
                # The validation will be handled in execute_voted_command
                pass
            else:
                # For regular song commands, validate as before
                if not self.validate_song_arg(args)[0]:
                    await message.channel.send(self.validate_song_arg(args)[1])
                    return
        elif vote_type == "weather":
            args = message.content.split()[1:] if len(message.content.split()) > 1 else []
            if not self.validate_weather_arg(args)[0]:
                await message.channel.send(self.validate_weather_arg(args)[1])
                return
        elif vote_type == "levitate":
            args = message.content.split()[1:] if len(message.content.split()) > 1 else []
            if not self.validate_levitate_args(args)[0]:
                await message.channel.send(self.validate_levitate_args(args)[1])
                return
        elif vote_type == "gravity":
            args = message.content.split()[1:] if len(message.content.split()) > 1 else []
            if not self.validate_gravity_args(args)[0]:
                await message.channel.send(self.validate_gravity_args(args)[1])
                return
        elif vote_type == "playvid":
            args = message.content.split()[1:] if len(message.content.split()) > 1 else []
            ok, msg = self.validate_playvid_args(args)
            if not ok:
                await message.channel.send(msg)
                return

        logging.info(f"Starting vote for {vote_type}")
        self.voting_active = True
        self.current_vote_type = vote_type
        self.current_vote_message = message
        self.votes = {}
        
        # Automatically count the vote initiator as a "yes" vote
        self.votes[message.author.name] = "yes"
        
        channel = self.connected_channels[0]
        # Update the message to show initial vote count
        await channel.send(f"🗳️ Vote started for:【{self.votable_commands[vote_type]}】- Use !yes or !no - {Config.VOTING_DURATION} seconds (Yes: 1 | No: 0)")
        self.voting_task = asyncio.create_task(self.end_vote_timer(channel))

    async def cast_vote(self, username, vote):
        if not self.voting_active:
            return
            
        logging.info(f"Vote cast by {username}: {vote}")
        self.votes[username] = vote
        yes_votes = sum(1 for v in self.votes.values() if v == "yes")
        no_votes = sum(1 for v in self.votes.values() if v == "no")
        
        channel = self.connected_channels[0]
        await channel.send(f"Votes for:【{self.votable_commands[self.current_vote_type]}】- Yes: {yes_votes} | No: {no_votes}")

    async def end_vote_timer(self, channel):
        await asyncio.sleep(Config.VOTING_DURATION)
        
        if not self.voting_active:
            return
            
        yes_votes = sum(1 for v in self.votes.values() if v == "yes")
        no_votes = sum(1 for v in self.votes.values() if v == "no")
        
        logging.info(f"Vote ended for {self.current_vote_type} - Yes: {yes_votes}, No: {no_votes}")
        await channel.send(f"✅ Vote ended for:【{self.votable_commands[self.current_vote_type]}】- Yes: {yes_votes} | No: {no_votes}")
        
        if yes_votes > no_votes:
            await self.execute_voted_command()
        
        self.voting_active = False
        self.current_vote_type = None
        self.votes = {}
        self.voting_task = None

    async def execute_voted_command(self):
        await asyncio.sleep(Config.CHAT_DELAY)
        
        logging.info(f"Executing voted command: {self.current_vote_type}")
        if self.current_vote_type == "reset":
            await self.reset()
        elif self.current_vote_type == "song":
            args = self.current_vote_message.content.split()[1:]
            
            if args and args[0].lower() == "category":
                # Handle category shuffle
                categories = args[1:] if len(args) > 1 else ["all"]
                await self.song_category(categories)
            else:
                # Handle regular song command
                song_choice = args[0] if args else "random"
                await self.song(song_choice)
        elif self.current_vote_type == "weather":
            args = self.current_vote_message.content.split()[1:]
            weather_choice = args[0] if args else "sunny"
            await self.weather(weather_choice)
        elif self.current_vote_type == "levitate":
            args = self.current_vote_message.content.split()[1:]
            levitate_choice = args[0] if args else "off"
            await self.levitate(levitate_choice)
        elif self.current_vote_type == "toggle_ai":
            await self.toggle_enemy_ai()
        elif self.current_vote_type == "exit":
            await self.exit_building()
        elif self.current_vote_type == "gravity":
            args = self.current_vote_message.content.split()[1:]
            gravity_level = args[0] if args else "20"
            await self.set_gravity(gravity_level)
        elif self.current_vote_type == "playvid":
            args = self.current_vote_message.content.split()[1:]
            await self.playvid(args[0])
        elif self.current_vote_type == "camera":
            await self.toggle_camera()

    async def toggle_map(self):
        """Toggle game map view with special handling for Ocean regions"""
        logging.info("Executing map command")
        
        # Get current map data to check region
        map_data = await self.get_map_json_data()
        current_region = map_data.get('region', '').strip()
        
        logging.info(f"Current region before map toggle: {current_region}")
        
        # Different behavior based on region
        if current_region == "Ocean":
            # No province to select for Ocean, so just open the map, wait a bit, and exit the map
            logging.info("Ocean region detected - using alternate map sequence")
            send_game_input(GameKeys.MAP.value)  # Open map
            time.sleep(7)
            send_game_input(GameKeys.MAP.value)  # Press V to exit
        else:
            # Original behavior for non-ocean regions
            send_game_input(GameKeys.MAP.value)  # Open map
            time.sleep(3)
            send_game_input("{ENTER}")  # Press ENTER
            time.sleep(6)  # Wait 6 seconds
            send_game_input(GameKeys.MAP.value)  # Press V
            time.sleep(2)
            send_game_input(GameKeys.MAP.value)  # Press V again

    async def toggle_camera(self):
        """Toggle Third Person Camera mod in game"""
        logging.info("Executing camera command")
        time.sleep(1)
        send_game_input(GameKeys.CAMERA.value)
        current = self.state.get("camera_mode", "first")
        new_mode = "third" if current == "first" else "first"
        self._update_state("camera_mode", new_mode)

    async def bighop(self):
        """Shortcut for common pattern to get unstuck"""
        logging.info("Executing BIGHOP command")
        send_game_input(GameKeys.BACK.value, repeat=100)
        send_game_input(GameKeys.WALK.value)
        send_game_input(GameKeys.JUMP.value)


    async def use_shotgun(self):
        """Use shotgun weapon by raising weapon, firing, and then lowering it"""
        logging.info("Executing shotgun command")
        
        # Raise weapon
        logging.info("Raising weapon")
        send_game_input('Z')
        time.sleep(0.5)
        
        # Fire weapon
        logging.info("Firing weapon")
        send_game_input('X')
        
        # Wait before lowering weapon
        time.sleep(2)
        send_game_input('Z')

    async def reset(self):
        """Reset to random location"""
        logging.info("Executing reset command")
        
        data = await self.get_map_json_data()
        
        cmd = f"tele2pixel {data['mapPixelX']} {data['mapPixelY']}"
        self.send_console_command(cmd)
        
        await asyncio.sleep(5)

        channel = self.connected_channels[0]
        await channel.send('Sent to last known location!')
        
    async def song(self, choice=None):
        """Change background music"""
        logging.info(f"Executing song command with choice: {choice}")
        
        self.send_console_command(f"song {choice}")
        
        await asyncio.sleep(5)
        
        channel = self.connected_channels[0]
        await channel.send('Song changed!')
        track_id = getattr(self, "_track_map", {}).get(str(choice), None)
        song_display = f"{choice} (Track {track_id})" if track_id is not None else str(choice)
        self._update_state("song", song_display)

    async def song_category(self, categories):
        """Change music to a random song from specified categories"""
        categories_str = " ".join(categories)
        logging.info(f"Executing song shuffle command with categories: {categories_str}")
        
        # Send the command to the game console
        self.send_console_command(f"song shuffle {categories_str}")
        
        await asyncio.sleep(5)
        
        channel = self.connected_channels[0]
        categories_str_display = ", ".join(categories)
        await channel.send(f'Song shuffle categories changed to: {categories_str_display}!')
        self._update_state("song_category", categories_str_display.lower())

    async def weather(self, weather_choice):
        """Change in-game weather"""
        logging.info(f"Executing weather command with choice: {weather_choice}")

        self.send_console_command(f"set_weather {Config.WEATHER_TYPES_MAP.get(weather_choice)}")

        await asyncio.sleep(5)
        
        channel = self.connected_channels[0]
        weather_emoji = Config.WEATHER_EMOJIS.get(weather_choice.title(), "🌈")
        await channel.send(f'Weather changed to: {weather_emoji}{weather_choice.title()}!')

    async def levitate(self, levitate_choice):
        """Toggle levitatation on/off"""
        logging.info(f"Executing levitate command with choice: {levitate_choice}")

        self.send_console_command(f"levitate {levitate_choice}")

        await asyncio.sleep(5)
        
        channel = self.connected_channels[0]
        await channel.send(f'Levitate set to: {levitate_choice}!')
        self._update_state("levitate", levitate_choice.lower())

    async def toggle_enemy_ai(self):
        """Toggle enemy AI on/off"""
        logging.info("Executing toggle_enemy_ai command")

        self.send_console_command("tai")

        await asyncio.sleep(5)
        
        channel = self.connected_channels[0]
        await channel.send("Toggled enemy AI!")
        current = self.state.get("ai_enabled", True)
        self._update_state("ai_enabled", not current)

    async def exit_building(self):
        """Teleport outside building/dungeon or do nothing"""
        logging.info("Executing exit command")

        send_game_input("=")
        
        await asyncio.sleep(5)
        
        channel = self.connected_channels[0]
        await channel.send("Teleported outside of current building, or did nothing if already outside.")

    async def set_gravity(self, gravity_level):
        """Set gravity level (0–20)"""
        logging.info(f"Executing gravity command with level: {gravity_level}")

        self.send_console_command(f"set_grav {gravity_level}")

        await asyncio.sleep(5)
        
        channel = self.connected_channels[0]
        await channel.send(f'Gravity set to: {gravity_level}!')
        self._update_state("gravity", int(gravity_level))

    async def playvid(self, idx_str: str):
        """Play an FMV: playvid anim00XX.vid, waits based on per-video durations."""
        try:
            n = int(idx_str)
            vid = f"anim00{n:02d}.vid"
            logging.info(f"Executing playvid for {vid}")

            # Map of known durations (fill these in as you measure them)
            durations = {
                0: 45,
                1: 14,
                2: 6,
                3: 15,
                4: 10,
                5: 46,
                6: 18,
                7: 16,
                8: 20,
                9: 20,
                10: 15,
                11: 6,
                12: 15,
                13: 13,
                14: 17,
                15: 22,
            }

            # Start video
            self.send_console_command(f"playvid {vid}")

            # Look up duration (default 10s if not found)
            secs = durations.get(n, 10)
            await asyncio.sleep(secs)

            # Close console after playback
            send_game_input(GameKeys.ESC.value)
            send_game_input(GameKeys.ESC.value)
            send_game_input(GameKeys.CONSOLE.value)
        except Exception as e:
            logging.error(f"playvid error: {e}")
            if self.connected_channels:
                await self.connected_channels[0].send("Failed to play that video.")

    async def killall(self):
        """Kill all enemies"""
        logging.info("Executing killall command")
        self.send_console_command("killall")
   
    def send_console_command(self, command: str):
        """Send command through game console"""
        logging.info(f"Sending console command: {command}")
        
        try:
            # Get the game window
            window = next((w for w in gw.getWindowsWithTitle("Daggerfall Unity") 
                          if w.title == "Daggerfall Unity"), None)
                          
            if not window:
                logging.warning("Game window not found for console command")
                return
                
            app = pywinauto.Application(backend="win32").connect(handle=window._hWnd)
            dlg = app.window(handle=window._hWnd)
            
            # Open console
            send_game_input(GameKeys.CONSOLE.value)
            time.sleep(0.5)
            
            send_game_input(command)  # Send command
            time.sleep(0.5)
            
            # Send ENTER and close console using regular game input
            send_game_input("{ENTER}")
            time.sleep(1)
            send_game_input(GameKeys.CONSOLE.value)
            
        except Exception as e:
            logging.error(f"Error sending console command: {e}")
    
    @staticmethod
    async def load_json_async(file_path):
        """Asynchronously loads and returns JSON data from a file."""
        async with aiofiles.open(file_path, 'r') as f:
            return json.loads(await f.read())

    async def get_map_json_data(self):
        """Get and process map data from Daggerfall Unity"""
        try:
            # Get map data path
            user_home = os.path.expanduser('~')
            mapdata_path = os.path.join(user_home, 'AppData', 'LocalLow', 
                                        'Daggerfall Workshop', 'Daggerfall Unity', 
                                        'MapData.json')
            
            # Load and process map data
            map_data = await self.load_json_async(mapdata_path)
            return {k: str(v).strip() for k, v in map_data.items()}
            
        except Exception as e:
            logging.error(f"Error reading map data: {e}")
            return {}

    async def update_stream_title(self, region: str, weather: str, time_str: str):
        try:
            hour = datetime.strptime(time_str, "%H:%M:%S").hour
            if 6 <= hour < 12:
                time_of_day = "morning"
            elif 12 <= hour < 18:
                time_of_day = "afternoon"
            else:
                time_of_day = "night"

            title = f"Walking through {region} on a {weather.lower()} {time_of_day}"

            client_id, oauth_token = Config.get_oauth()[:2]  # ignore client_secret

            # Remove "oauth:" prefix if present
            if oauth_token.startswith("oauth:"):
                oauth_token = oauth_token[6:]

            async with aiohttp.ClientSession() as session:
                # Get broadcaster ID
                async with session.get(
                    "https://api.twitch.tv/helix/users",
                    headers={
                        "Client-ID": client_id,
                        "Authorization": f"Bearer {oauth_token}",
                    }
                ) as resp:
                    data = await resp.json()
                    broadcaster_id = data["data"][0]["id"]

                # Update stream title
                async with session.patch(
                    f"https://api.twitch.tv/helix/channels?broadcaster_id={broadcaster_id}",
                    headers={
                        "Client-ID": client_id,
                        "Authorization": f"Bearer {oauth_token}",
                        "Content-Type": "application/json"
                    },
                    json={"title": title}
                ) as patch_resp:
                    if patch_resp.status == 204:
                        logging.info(f"Stream title updated to: {title}")
                    else:
                        err = await patch_resp.text()
                        raise Exception(f"{patch_resp.status} - {err}")

        except Exception as e:
            logging.error(f"Failed to update stream title: {e}")


    async def game_info(self):
        """Display game state information (cached only)."""
        await self.refresh_now()

        try:
            # Ensure we have cached data; do a one-shot refresh if empty or very stale
            if not self._latest_response_data or (
                self._latest_response_at and
                (datetime.now(timezone.utc) - self._latest_response_at).total_seconds() > Config.REFRESH_INTERVAL * 2
            ):
                ok = await self.refresh_now()
                if not ok and self.connected_channels:
                    await self.connected_channels[0].send("No info yet — gathering data…")
                    return

            # Cache music tracks if needed
            if not hasattr(self, '_music_tracks'):
                music_data_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'list_music_tracks.json')
                self._music_tracks = await self.load_json_async(music_data_path)
                self._track_map = {track['TrackName']: track['TrackID'] for track in self._music_tracks}

            response_data = self._latest_response_data

            # === Rest of the existing method unchanged ===
            log = response_data.get('log') or {}
            region_fk = log.get('region_fk') or {}
            poi = log.get('poi') or {}

            # Basics
            region = (log.get('region') or '').strip()
            location = (log.get('location') or '').strip()
            weather = (log.get('weather') or '').strip()
            season = (log.get('season') or '').strip()
            current_song = (log.get('current_song') or '').strip()

            # Ocean + "near" handling
            in_ocean = region.lower() == 'ocean'
            last_known_name = ''
            if in_ocean:
                lkr = log.get('last_known_region')
                if isinstance(lkr, dict):  # if you nest this in the serializer (recommended)
                    last_known_name = (lkr.get('name') or '').strip()

            # Climate/emoji (already proper Unicode via serializers; no decode needed)
            climate = (region_fk.get('climate') or '').strip()
            climate_emoji = region_fk.get('emoji') or ''

            poi_emoji = poi.get('emoji') or ''

            # Time formatting (date like: "…, HH:MM:SS")
            date_str = log.get('date', '') or ''
            date_val, time_12hr, time_hms = "", "", ""
            if date_str and ',' in date_str:
                parts = [p.strip() for p in date_str.split(',')]
                time_hms = parts[-1] if parts else ""
                try:
                    dt_t = datetime.strptime(time_hms, '%H:%M:%S')
                    time_12hr = dt_t.strftime('%I:%M %p').lstrip('0')
                    date_val = ", ".join(parts[:-1]).strip()
                except ValueError:
                    # leave raw if parse fails
                    date_val = date_str

            # Emojis
            weather_emoji = Config.WEATHER_EMOJIS.get(weather, "🌈")
            season_emoji = Config.SEASON_EMOJIS.get(season, "❓")

            # Music info
            track_id = getattr(self, '_track_map', {}).get(current_song, None)
            music_info = f"🎵{current_song} (Track {track_id})" if current_song and track_id is not None else ""

            # Map link
            map_link = "🗺️Map: https://kershner.org/daggerwalk"

            # Location string
            if in_ocean:
                near = f" near {last_known_name}" if last_known_name else ""
                location_part = f"🌊Ocean{near}"
            else:
                # e.g. "🌍Daggerfall🌲Woodlands 🏰Wayrest"
                left = f"🌍{region}{climate_emoji}{climate}".strip()
                right = f"{poi_emoji}{location}".strip()
                location_part = f"{left} {right}".strip()

            # Final status line
            status = " ".join(filter(None, [
                location_part,
                f"⌚{time_12hr}" if time_12hr else "",
                f"📅{date_val}" if date_val else "",
                f"{season_emoji}{season}" if season else "",
                f"{weather_emoji}{weather}" if weather else "",
                music_info,
                map_link,
            ]))

            # Debounce to avoid duplicate !info within a short window
            now_m = time.monotonic()
            last_m = getattr(self, "_last_info_sent_at", 0.0)
            if now_m - last_m >= 3.5:
                if self.connected_channels:
                    await self.connected_channels[0].send(status)
                self._last_info_sent_at = now_m
            else:
                logging.info("Suppressed duplicate !info within debounce window")

            # Update stream title when we have HH:MM:SS
            if time_hms:
                await self.update_stream_title(region or "", weather or "", time_hms)

        except Exception as e:
            logging.error(f"Info error: {e}")


    async def check_if_bot_is_stuck(self):
        logging.info("Starting stuck check...")
        
        # Skip stuck check for 5 minutes after bot startup
        uptime = time.monotonic() - self._bot_started_at_monotonic
        if uptime < 300:
            logging.info(f"Skipping stuck check - bot uptime only {uptime:.1f}s")
            return

        est = pytz.timezone("US/Eastern")
        now = datetime.now(est).time()
        logging.info(f"Current time EST: {now}")

        # Skip the first 10 minutes after midnight and 9 AM Eastern (handles DST automatically)
        if ((now.hour == 0 and now.minute < 10) or
            (now.hour == 9 and now.minute < 10)):
            logging.info(f"Skipping stuck check - in quiet hours (hour={now.hour}, minute={now.minute})")
            return
        
        try:
            base = Config.DJANGO_BASE_API_URL
            logging.info(f"Fetching logs from {base}/logs/...")

            logs = requests.get(f"{base}/logs/?limit=2&ordering=-id", timeout=5).json().get("results", [])
            logging.info(f"Retrieved {len(logs)} logs")
            
            if len(logs) < 2:
                logging.info("Not enough logs for stuck check")
                return

            pos1 = (logs[0].get("world_x"), logs[0].get("world_z"))
            pos2 = (logs[1].get("world_x"), logs[1].get("world_z"))
            logging.info(f"Position comparison: pos1={pos1}, pos2={pos2}")
            
            # Calculate distance between positions (allow for small movements)
            STUCK_TOLERANCE = 10  # Units
            if pos1[0] is not None and pos1[1] is not None and pos2[0] is not None and pos2[1] is not None:
                distance = ((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2) ** 0.5
                logging.info(f"Distance between positions: {distance:.1f} (tolerance: {STUCK_TOLERANCE})")
                
                if distance > STUCK_TOLERANCE:
                    logging.info("Movement detected - not stuck")
                    return
            else:
                logging.warning("Position data incomplete - skipping stuck check")
                return

            logging.info("Positions are identical - checking stop/walk commands...")

            # get last stop and walk
            stop_cmds = requests.get(f"{base}/chat_commands/?limit=1&ordering=-id&command=stop", timeout=5).json().get("results", [])
            walk_cmds = requests.get(f"{base}/chat_commands/?limit=1&ordering=-id&command=walk", timeout=5).json().get("results", [])
            stop_id = stop_cmds[0]["id"] if stop_cmds else 0
            walk_id = walk_cmds[0]["id"] if walk_cmds else 0
            logging.info(f"Last stop ID: {stop_id}, last walk ID: {walk_id}")

            # only consider stop newer than walk if the stop is from today
            if stop_cmds:
                stop_created = stop_cmds[0].get("created") or stop_cmds[0].get("timestamp")
                logging.info(f"Last stop timestamp: {stop_created}")
                if stop_created:
                    # handle ISO8601 with optional 'Z'
                    stop_time = datetime.fromisoformat(stop_created.replace("Z", "+00:00"))
                    logging.info(f"Stop time: {stop_time}, today: {date.today()}")
                    if stop_time.date() == date.today() and stop_id > walk_id:
                        logging.info("Recent stop command found - not attempting unstuck")
                        return

            # still grab most recent command overall (to handle bighop case)
            cmds = requests.get(f"{base}/chat_commands/?limit=1&ordering=-id", timeout=5).json().get("results", [])
            last_cmd = cmds[0]["command"].lower() if cmds else None
            logging.info(f"Last command: {last_cmd}")

            if not self.connected_channels:
                logging.warning("No connected channels for stuck message")
                return
            
            channel = self.connected_channels[0]
            logging.info("Bot appears stuck - sending unstuck message...")
            await channel.send("The Walker might be stuck, attempting to free them...")

            if last_cmd == "bighop":
                logging.info("Executing left 50 as unstuck action")
                await self.log_chat_command(Config.BOT_USERNAME, "left", ["50"])
                await channel.send("!left 50")
                await self.send_movement(GameKeys.LEFT, args=["50"])
            else:
                logging.info("Executing bighop as unstuck action")
                await self.log_chat_command(Config.BOT_USERNAME, "bighop", [])
                await channel.send("!bighop")
                await self.bighop()

        except Exception as e:
            logging.error(f"check_if_bot_is_stuck error: {e}")
            import traceback
            logging.error(traceback.format_exc())

    async def help(self):
        """Display available commands"""
        logging.info("Executing help command")
        channel = self.connected_channels[0]
        
        combined_message = (
            "💀🌲Daggerwalk Commands: "
            "!walk • !stop • !jump • !left • "
            "!right • !up • !down • !forward • "
            "!back • !map • !song • !state • "
            "!more"
        )
        
        await channel.send(combined_message)

    async def more_commands(self):
        """Display more commands"""
        logging.info("Executing more commands")
        channel = self.connected_channels[0]
        
        combined_message = (
            "🗡️More Daggerwalk Commands: "
            "!info • !quest • !use • !weather • !levitate • !toggle_ai • !exit • !gravity • !playvid • !modlist • !shotgun • !camera • !esc"
        )
        
        await channel.send(combined_message)
    
    async def modlist(self):
        """Display active mods"""
        logging.info("Executing modlist command")
        channel = self.connected_channels[0]
        await channel.send("Daggerwalk uses the following Daggerfall Unity mods:")
        await asyncio.sleep(Config.CHAT_DELAY)
        await channel.send(", ".join(Config.ACTIVE_MODS))

    async def save_game(self):
        """Save game state"""
        logging.info("Executing save command")
        send_game_input(GameKeys.SAVE.value)

    async def load_game(self):
        """Load last save"""
        logging.info("Executing load command")
        send_game_input(GameKeys.LOAD.value)

    async def exec_command(self, args):
        """Execute console command (admin only)"""
        if not args:
            await self.connected_channels[0].send("Usage: !exec <command> <args>")
            return
        logging.info(f"Executing admin command: {' '.join(args)}")
        self.send_console_command(" ".join(args))

    def _format_quest_lines_from_response(self, response_data):
        """Return (completion_line, current_line) based on latest response_data."""
        try:
            quest_completed = bool(response_data.get("quest_completed"))
            completed_quest = response_data.get("completed_quest") or {}
            current_quest = response_data.get("current_quest") or {}

            # Build "current_quest" line
            current_line = ""
            if current_quest:
                desc = (current_quest.get("description") or "").replace(".", "").strip()
                poi = current_quest.get("poi") or {}
                poi_region_obj = poi.get("region") or {}

                # Prefer nested poi.region.name; fall back to old top-level region_name if present
                region_name = (
                    current_quest.get("region_name")
                    or (poi_region_obj.get("name") if isinstance(poi_region_obj, dict) else None)
                    or ""
                ).strip()

                url = "https://kershner.org/daggerwalk/quest"
                current_line = f"🧭Current quest: {desc} in {region_name} 🗺️Map: {url}"

            # Build "completed_quest" line
            completion_line = ""
            if quest_completed:
                cq_name = (
                    completed_quest.get("name")
                    or completed_quest.get("poi_name")
                    or current_quest.get("poi_name")
                    or "Quest"
                )
                cq_xp = (
                    completed_quest.get("xp")
                    or completed_quest.get("xp_awarded")
                    or current_quest.get("xp")
                )

                # Compose: "✅{name} completed!  {xp} XP awarded!  {current_line}"
                parts = [f"✅{cq_name} completed!"]
                if cq_xp not in (None, "", 0):
                    parts.append(f"{cq_xp} XP awarded!")
                if current_line:
                    parts.append(current_line)

                # Join with two spaces between segments
                completion_line = "  ".join(parts)

            return completion_line, current_line

        except Exception as e:
            logging.error(f"_format_quest_lines_from_response error: {e}")
            return "", ""

    async def quest(self):
        """Report current quest (and most recent completion if present)."""
        await self.refresh_now()
        
        try:
            # If we’ve never cached a response (e.g., right after startup), try one-shot refresh
            if not self._latest_response_data:
                ok = await self.refresh_now()
                if not ok:
                    if self.connected_channels:
                        await self.connected_channels[0].send("No quest info available yet.")
                    return

            completion_line, current_line = self._format_quest_lines_from_response(self._latest_response_data)

            if self.connected_channels:
                # Prefer showing current quest; include completion if the last update completed one
                if current_line:
                    await self.connected_channels[0].send(current_line)
                if completion_line:
                    await self.connected_channels[0].send(completion_line)

        except Exception as e:
            logging.error(f"!quest error: {e}")
            if self.connected_channels:
                await self.connected_channels[0].send("Failed to fetch quest info.")

    async def show_state(self):
        """Display current local bot state in plain format."""
        try:
            parts = []
            s = self.state

            if s.get("song"):
                parts.append(f"Song: {s['song']}")
            if s.get("song_category"):
                parts.append(f"Song Category: {s['song_category']}")
            if s.get("gravity") is not None:
                parts.append(f"Gravity: {s['gravity']}")
            if s.get("levitate"):
                parts.append(f"Levitate: {s['levitate']}")
            if s.get("ai_enabled") is not None:
                ai_str = "on" if s['ai_enabled'] else "off"
                parts.append(f"AI: {ai_str}")
            if s.get("camera_mode"):
                parts.append(f"Camera: {s['camera_mode']}")
            if s.get("next_log_time"):
                est = pytz.timezone("US/Eastern")
                t = s['next_log_time'].astimezone(est)
                parts.append(f"Next log: {t.strftime('%I:%M %p EST').lstrip('0')}")

            msg = " • ".join(parts) if parts else "No state values set yet."
            if self.connected_channels:
                await self.connected_channels[0].send(msg)
            logging.info(f"Displayed state: {msg}")
        except Exception as e:
            logging.error(f"show_state error: {e}")

if __name__ == "__main__":
    bot = DaggerfallBot()
    bot.run()
