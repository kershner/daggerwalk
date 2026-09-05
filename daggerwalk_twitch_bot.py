from datetime import datetime, timedelta, timezone
from twitchio.ext import commands
import pygetwindow as gw
from enum import Enum
import subprocess
import pywinauto
import pyautogui
import aiofiles
import requests
import logging
import aiohttp
import asyncio
import pytz
import json
import time
import os
import ctypes
import math
from contextlib import asynccontextmanager


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
    CURSOR = "{ENTER}"
    USE = "k"
    CAMERA = "O"

class Config:
    """Bot configuration settings"""
    PARAMS_FILE = "parameters.json"
    TWITCH_CHANNEL = "daggerwalk"
    BOT_USERNAME = "daggerwalk_bot"
    REFRESH_INTERVAL = 300  # 5 minutes
    AUTOSAVE_INTERVAL = 600  # 10 minutes
    CHAT_DELAY = 1.5  # seconds
    VOTING_DURATION = 20  # seconds
    AUTHORIZED_USERS = ["billcrystals", "daggerwalk", "daggerwalk_bot"]
    MAX_INPUT_REPEATS = 100
    DEFAULT_MOVEMENT_AMOUNT = 10
    TRANSLATION_SECONDS_PER_STEP = 0.1
    CONTROL_TICK_SECONDS = 0.02
    MOUSE_STEP_PIXELS = 20
    MAX_PENDING_MOUSE_PIXELS = 5000
    MAX_PENDING_TRANSLATION_SECONDS = 10.0
    COMMAND_ALIASES = {
        "w": "walk",
        "s": "stop",
        "f": "forward",
        "b": "back",
        "l": "left",
        "r": "right",
        "u": "up",
        "d": "down",
        "j": "jump",
    }
    HELP_COMMANDS = (
        "walk", "stop", "jump", "left", "right", "up", "down", "forward",
        "back", "cursor", "click", "map", "song", "state", "more",
    )
    MORE_COMMANDS = (
        "info", "quest", "use", "weather", "levitate", "toggle_ai", "exit",
        "gravity", "playvid", "modlist", "shotgun", "camera", "killall", "bighop",
    )
    COMMAND_HELP = {
        "walk": "Start autowalk • Usage: !walk",
        "stop": "Stop autowalk and clear all pending movement • Usage: !stop",
        "jump": "Jump repeatedly • Usage: !jump",
        "left": "Look left smoothly by an optional amount from 1–100 (default 10) • Usage: !left [amount]",
        "right": "Look right smoothly by an optional amount from 1–100 (default 10) • Usage: !right [amount]",
        "up": "Look up smoothly by an optional amount from 1–100 (default 10) • Usage: !up [amount]",
        "down": "Look down smoothly by an optional amount from 1–100 (default 10) • Usage: !down [amount]",
        "forward": "Hold forward by an optional amount from 1–100 (default 10) • Usage: !forward [amount]",
        "back": "Hold backward by an optional amount from 1–100 (default 10) • Usage: !back [amount]",
        "cursor": "Toggle the in-game cursor by pressing Enter • Usage: !cursor",
        "click": "Click the left mouse button • Usage: !click",
        "map": "Briefly show the world map • Usage: !map",
        "song": "Start a vote to change the music • Usage: !song <number|random|category>",
        "state": "Show the bot's current local settings • Usage: !state",
        "help": "List commands or show details for one command • Usage: !help [command]",
        "more": "List additional commands • Usage: !more",
        "info": "Show current journey and character information • Usage: !info",
        "quest": "Show active quests or one quest slot • Usage: !quest [1-3]",
        "use": "Use or activate the targeted object • Usage: !use",
        "weather": "Start a vote to change the weather • Usage: !weather <type>",
        "levitate": "Start a vote to toggle levitation • Usage: !levitate <on|off>",
        "toggle_ai": "Start a vote to toggle enemy AI • Usage: !toggle_ai",
        "exit": "Start a vote to teleport outside the current building • Usage: !exit",
        "gravity": "Start a vote to set gravity from 0–20 • Usage: !gravity <0-20>",
        "playvid": "Start a vote to play a video numbered 0–15 • Usage: !playvid <0-15>",
        "modlist": "List the active Daggerfall Unity mods • Usage: !modlist",
        "shotgun": "Raise, fire, and lower the equipped shotgun • Usage: !shotgun",
        "camera": "Start a vote to toggle the third-person camera • Usage: !camera",
        "killall": "Kill all nearby enemies • Usage: !killall",
        "bighop": "Run the extended unstuck movement sequence • Usage: !bighop",
        "save": "Admin only: save the game • Usage: !save",
        "load": "Admin only: load the latest save • Usage: !load",
        "exec": "Admin only: run a game-console command • Usage: !exec <command>",
    }
    DJANGO_BASE_API_URL = "https://kershner.org/api/daggerwalk"
    DJANGO_LOG_URL = "https://kershner.org/daggerwalk/log/"
    QUEST_COMPLETION_STATE_FILE = "quest_completion_state.json"

    STREAM_TAGS = [
        "Retro",
        "RPG",
        "PC",
        "chill",
        "Cozy",
        "Interactive",
        "Exploration",
        "elderscrolls",
        "Programming",
        "Automation"
    ]
    
    ACTIVE_MODS = [
        "World of Daggerfall", "Interesting Eroded Terrains",
        "Wilderness Overhaul", "Basic Roads", "Dynamic Skies", "Real Grass",
        "Birds in Daggerfall", "HUD Be Gone",  "Immersive Footsteps", "Eye of the Beholder", 
        "Render Distance Expander", "Dynamic Ambience", "DIAAMM Part 1", "Animated Water",
        "Seasons of the Iliac Bay",
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

    @staticmethod
    def get_weather_display(weather: str) -> str:
        return "Thunderstorming" if weather.lower() == "thunderstorm" else weather
    
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
        client_id = params.get("CLIENT_ID", "")
        oauth_token = params.get("OAUTH_TOKEN", "")
        
        # Remove 'oauth:' prefix if present
        if oauth_token.startswith("oauth:"):
            oauth_token = oauth_token[6:]
        
        return client_id, oauth_token

    @classmethod
    def get_api_key(cls):
        """Return Daggerwalk API key"""
        params = cls.load_params()
        return params.get("daggerwalk_api_key", "")

    @classmethod
    def get_bluesky_credentials(cls):
        """Return Bluesky handle and app password"""
        params = cls.load_params()
        handle = params.get("BLUESKY_HANDLE", "")
        password = params.get("BLUESKY_APP_PASSWORD", "")
        return handle, password

def get_game_dialog():
    """Return a fresh automation handle for the game window."""
    window = next((w for w in gw.getWindowsWithTitle("Daggerfall Unity")
                   if w.title == "Daggerfall Unity"), None)
    if not window:
        logging.warning("Game window not found")
        return None
    app = pywinauto.Application(backend="win32").connect(handle=window._hWnd)
    return app.window(handle=window._hWnd)


def send_game_input(key: str, repeat: int = 1, delay: float = 0.2):
    """Send keyboard input to Daggerfall Unity window."""
    try:
        dialog = get_game_dialog()
        if dialog is None:
            return
        logging.info(f"Sending input: {key} ({repeat} times)")
        for _ in range(repeat):
            dialog.send_keystrokes(key)
            time.sleep(delay)
    except Exception as e:
        logging.error(f"Input error: {e}")


def focus_game_window() -> bool:
    """Focus Daggerfall Unity before sending global mouse or held-key input."""
    try:
        dialog = get_game_dialog()
        if dialog is None:
            return False
        dialog.set_focus()
        return True
    except Exception as e:
        logging.error(f"Could not focus game window: {e}")
        return False


def move_mouse_relative(dx: int, dy: int):
    """Send one relative mouse movement event."""
    ctypes.windll.user32.mouse_event(0x0001, int(dx), int(dy), 0, 0)


def left_click():
    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.1)
    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)


def set_movement_key(key: str, pressed: bool):
    """Set W/S state without sleeps or PyAutoGUI's implicit pause."""
    virtual_keys = {"w": 0x57, "s": 0x53}
    flags = 0 if pressed else 0x0002
    ctypes.windll.user32.keybd_event(virtual_keys[key], 0, flags, 0)


class MovementController:
    """Blend chat movement into one smooth, cancellable input stream."""

    def __init__(self, mouse_move=move_mouse_relative, key_state=set_movement_key):
        self._mouse_move = mouse_move
        self._key_state = key_state
        self._yaw_pixels = 0.0
        self._pitch_pixels = 0.0
        self._translation_seconds = 0.0
        self._held_key = None
        self._generation = 0

    @property
    def generation(self):
        return self._generation

    @property
    def translation_active(self):
        return bool(self._translation_seconds or self._held_key)

    @staticmethod
    def _clamp(value, limit):
        return max(-limit, min(limit, value))

    def add_view(self, yaw_steps=0, pitch_steps=0):
        step = Config.MOUSE_STEP_PIXELS
        limit = Config.MAX_PENDING_MOUSE_PIXELS
        self._yaw_pixels = self._clamp(self._yaw_pixels + yaw_steps * step, limit)
        self._pitch_pixels = self._clamp(self._pitch_pixels + pitch_steps * step, limit)

    def add_translation(self, steps):
        seconds = steps * Config.TRANSLATION_SECONDS_PER_STEP
        self._translation_seconds = self._clamp(
            self._translation_seconds + seconds,
            Config.MAX_PENDING_TRANSLATION_SECONDS,
        )
        return self._generation

    def cancel_all(self):
        self._generation += 1
        self._yaw_pixels = self._pitch_pixels = self._translation_seconds = 0.0
        self.pause()

    def pause(self):
        """Release a held key while retaining pending chat movement."""
        if self._held_key:
            self._key_state(self._held_key, False)
            self._held_key = None

    def tick(self):
        """Advance all active axes by one fixed control interval."""
        step = Config.MOUSE_STEP_PIXELS
        dx = self._clamp(self._yaw_pixels, step)
        dy = self._clamp(self._pitch_pixels, step)
        self._yaw_pixels -= dx
        self._pitch_pixels -= dy

        desired_key = None
        if self._translation_seconds:
            desired_key = "w" if self._translation_seconds > 0 else "s"
            elapsed = min(abs(self._translation_seconds), Config.CONTROL_TICK_SECONDS)
            self._translation_seconds -= math.copysign(elapsed, self._translation_seconds)

        if desired_key != self._held_key:
            self.pause()
            if desired_key:
                self._key_state(desired_key, True)
            self._held_key = desired_key

        if dx or dy:
            self._mouse_move(round(dx), round(dy))


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
    def __init__(self, dev_channel=None):
        self._dev_channel = dev_channel
        self._dev_mode = dev_channel is not None
        oauth = "dev" if self._dev_mode else Config.get_oauth()[1]
        super().__init__(token=oauth, prefix="!", initial_channels=[Config.TWITCH_CHANNEL])
        
        self._bot_started_at_monotonic = time.monotonic()
        self._latest_response_data = None
        self._latest_response_at = None
        self._recent_world_positions = []
        self._latest_command_state = None
        self.last_autosave = datetime.now(timezone.utc)
        self.voting_active = False
        self.current_vote_type = None
        self.current_vote_message = None
        self.votes = {}
        self._state_ready = asyncio.Event()
        self._startup_tasks_started = False
        self._refresh_lock = asyncio.Lock()
        self._ui_lock = asyncio.Lock()
        self._active_command_tasks = set()
        self._movement = MovementController()
        self._announced_quest_completion_keys = set()
        self._pending_quest_completions = {}
        self._last_bluesky_quest_post_date = None
        self._load_quest_completion_state()

        self.state = {
            "song": None,
            "song_category": "all",
            "gravity": 20,
            "levitate": "off",
            "ai_enabled": False,
            "camera_mode": "third",
            "next_log_time": None,
            "bluesky_live_text": "",
        }
        
        self.votable_commands = {
            "song": "change the background music",
            "weather": "change the weather",
            "levitate": "start or stop levitating",
            "toggle_ai": "toggle enemy AI",
            "exit": "teleport out of the current building",
            "gravity": "set gravity level",
            "playvid": "play an in-game video",
            "camera": "toggle third-person camera"
        }
        
        # Bluesky client initialization
        self.bluesky_client = None
        if not self._dev_mode:
            self._init_bluesky()


    @property
    def connected_channels(self):
        """Use the browser-backed channel when running without Twitch."""
        if self._dev_channel is not None:
            return [self._dev_channel]
        return super().connected_channels


    def _update_state(self, key, value):
        """Safely update a local state field and log the change."""
        if key in self.state:
            old = self.state[key]
            self.state[key] = value
            logging.info(f"State updated: {key} = {value} (was {old})")
        else:
            logging.warning(f"Attempted to set unknown state key: {key}")


    def _init_bluesky(self):
        try:
            global bluesky_live
            import bluesky_live

            handle, password = Config.get_bluesky_credentials()
            self.bluesky_client = bluesky_live.login(handle, password)
            if self.bluesky_client:
                logging.info(f"Bluesky logged in: {handle}")
        except Exception as e:
            logging.error(f"Bluesky init failed: {e}")
            self.bluesky_client = None


    async def event_ready(self):
        logging.info(f"Bot online as {self.nick}")
        await self._start_runtime()

    async def _start_runtime(self):
        """Start the same background services for Twitch and local dev mode."""
        if self._startup_tasks_started:
            logging.info("Runtime tasks already started; ignoring duplicate startup.")
            return
        self._startup_tasks_started = True

        if not self._dev_mode:
            await self.set_stream_tags()

        if self._dev_mode:
            self._state_ready.set()
        else:
            self.refresh_task = asyncio.create_task(self.data_refresh_loop())
        self.autosave_task = asyncio.create_task(self.autosave_loop())
        self.message_task = asyncio.create_task(self.message_scheduler())
        self.crash_monitor_task = asyncio.create_task(self.crash_monitor())
        self.side_effects_task = asyncio.create_task(self.side_effects_loop())
        self.local_state_refresh_task = asyncio.create_task(self.local_state_refresh_loop())  
        self.movement_control_task = asyncio.create_task(self.movement_control_loop())

    async def movement_control_loop(self):
        """Continuously apply blended mouse turns and W/S holds."""
        logging.info("Starting movement control loop")
        try:
            while True:
                try:
                    if self._ui_lock.locked():
                        self._movement.pause()
                    else:
                        self._movement.tick()
                except Exception as e:
                    logging.error(f"Movement control error: {e}")
                    self._movement.cancel_all()
                await asyncio.sleep(Config.CONTROL_TICK_SECONDS)
        finally:
            self._movement.cancel_all()

    def _start_command_task(self, name, command_factory):
        """Launch an ordinary command without blocking Twitch message handling."""
        async def run_command():
            try:
                await command_factory()
            except Exception:
                logging.exception(f"Command !{name} failed")

        task = asyncio.create_task(run_command())
        self._active_command_tasks.add(task)
        task.add_done_callback(self._active_command_tasks.discard)

    @asynccontextmanager
    async def _game_ui(self):
        async with self._ui_lock:
            self._movement.pause()
            yield

    async def message_scheduler(self):
        """Schedule periodic help (20m) and quest (25m) messages."""
        logging.info("Starting message scheduler")

        # Wait until we have first successful refresh so we don't announce early/empty
        await self._state_ready.wait()

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

        help_task = asyncio.create_task(
            run_periodic_message(self.help, HELP_INTERVAL, initial_delay=HELP_OFFSET)
        )
        quest_task = asyncio.create_task(
            run_periodic_message(self.quest, QUEST_INTERVAL, initial_delay=QUEST_OFFSET)
        )

        await asyncio.gather(help_task, quest_task)

    async def set_stream_tags(self):
        """Set Twitch stream tags"""
        try:
            client_id, oauth = Config.get_oauth()
            
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {oauth}",
                    "Client-Id": client_id
                }
                
                # Get broadcaster ID
                async with session.get(
                    f"https://api.twitch.tv/helix/users?login={Config.TWITCH_CHANNEL}",
                    headers=headers
                ) as resp:
                    if resp.status != 200:
                        logging.error(f"Failed to get user ID: {resp.status}")
                        return
                    data = await resp.json()
                    broadcaster_id = data["data"][0]["id"]
                
                # Set tags
                async with session.patch(
                    f"https://api.twitch.tv/helix/channels?broadcaster_id={broadcaster_id}",
                    headers=headers,
                    json={"tags": Config.STREAM_TAGS}
                ) as resp:
                    if resp.status == 204:
                        logging.info(f"✓ Set stream tags: {', '.join(Config.STREAM_TAGS)}")
                    else:
                        text = await resp.text()
                        logging.error(f"Failed to set tags: {resp.status} - {text}")
                        
        except Exception as e:
            logging.error(f"Error setting stream tags: {e}")


    async def data_refresh_loop(self):
        """Only refresh cached log/quest data; do NOT run side-effects here."""
        logging.info("Starting data refresh loop")
        first_success = False
        while True:
            try:
                if await self.refresh_now():
                    if not first_success:
                        first_success = True
                        self._state_ready.set()  # unblocks scheduler/commands that want initial state
                    await self.game_info()

                # Stuck check (run on a calm interval, not on every command/refresh)
                await self.check_if_bot_is_stuck()
            except Exception as e:
                logging.error(f"data_refresh_loop error: {e}")
            await asyncio.sleep(Config.REFRESH_INTERVAL)

    async def _check_and_announce_quest_completion(self, new_data):
        """Queue newly completed quests and deliver all pending announcements."""
        try:
            active_quests, completed_quests = self._get_quests_from_response(new_data)
            active_quests_by_slot = {
                quest.get("slot"): quest
                for quest in active_quests
                if quest.get("slot") is not None
            }
            logging.info(
                "Quest check - completion keys: %s",
                [self._quest_completion_key(quest) for quest in completed_quests],
            )

            for completed_quest in completed_quests:
                completion_key = self._quest_completion_key(completed_quest)
                if completion_key in self._announced_quest_completion_keys:
                    continue
                self._pending_quest_completions.setdefault(
                    completion_key,
                    {
                        "completed_quest": completed_quest,
                        "new_quest": active_quests_by_slot.get(completed_quest.get("slot")),
                        "completion_sent": False,
                        "bluesky_sent": False,
                        "new_quest_sent": False,
                    },
                )

            # A pending event restored after a crash might not yet have its replacement.
            # Enrich it from the current active quest in the same stable slot.
            for event in self._pending_quest_completions.values():
                completed_quest = event.get("completed_quest") or {}
                if not event.get("new_quest"):
                    event["new_quest"] = active_quests_by_slot.get(completed_quest.get("slot"))

            # Persist before attempting Twitch delivery. If the process exits or Twitch is
            # disconnected, the announcement will be retried after the next startup/refresh.
            if completed_quests:
                self._save_quest_completion_state()

            await self._drain_quest_completion_outbox()
        except Exception:
            logging.exception("_check_and_announce_quest_completion error")

    def _quest_completion_key(self, quest):
        """Return a stable deduplication key, including support for legacy payloads."""
        if quest.get("id") not in (None, ""):
            return f"id:{quest['id']}"
        fields = (
            quest.get("slot"),
            quest.get("quest_name") or quest.get("description") or quest.get("poi_name"),
            quest.get("completed_at"),
            quest.get("xp"),
        )
        return "legacy:" + "|".join(str(value or "") for value in fields)

    async def _drain_quest_completion_outbox(self):
        """Send pending quest completions, retaining failures for a later retry."""
        if not self._pending_quest_completions:
            return
        if not self.connected_channels:
            logging.warning(
                "Quest completion announcement deferred: Twitch channel is not connected"
            )
            return

        channel = self.connected_channels[0]
        for completion_key, event in list(self._pending_quest_completions.items()):
            completed_quest = event.get("completed_quest") or {}
            new_quest = event.get("new_quest")

            if not event.get("completion_sent"):
                try:
                    await channel.send(self._format_quest_completion(completed_quest))
                except Exception:
                    logging.exception(
                        "Quest completion announcement failed; queued for retry: %s",
                        completion_key,
                    )
                    continue

                # Record this stage before sending the new quest so a failure on the
                # second Twitch message never causes the completion to be duplicated.
                event["completion_sent"] = True
                self._save_quest_completion_state()

            if not event.get("bluesky_sent"):
                if self.bluesky_client:
                    today_eastern = datetime.now(
                        pytz.timezone("US/Eastern")
                    ).date().isoformat()
                    if self._last_bluesky_quest_post_date == today_eastern:
                        logging.info(
                            "Bluesky quest completion skipped for %s: daily post already sent",
                            completion_key,
                        )
                        event["bluesky_sent"] = True
                        self._save_quest_completion_state()
                    else:
                        # Feed-post record keys must be TIDs. Persist one before the
                        # request so every retry targets the same record.
                        if not event.get("bluesky_rkey"):
                            event["bluesky_rkey"] = bluesky_live.new_tid()
                            self._save_quest_completion_state()
                        try:
                            await asyncio.to_thread(
                                bluesky_live.post_quest_completion,
                                self.bluesky_client,
                                completed_quest,
                                event["bluesky_rkey"],
                            )
                        except Exception:
                            logging.exception(
                                "Bluesky quest completion failed; queued for retry: %s",
                                completion_key,
                            )
                        else:
                            event["bluesky_sent"] = True
                            self._last_bluesky_quest_post_date = today_eastern
                            self._save_quest_completion_state()
                else:
                    logging.warning(
                        "Bluesky quest completion skipped: client is unavailable"
                    )
                    event["bluesky_sent"] = True
                    self._save_quest_completion_state()

            if not new_quest:
                logging.warning(
                    "New quest announcement deferred for %s: no replacement in slot %s",
                    completion_key,
                    completed_quest.get("slot"),
                )
                continue

            if not event.get("new_quest_sent"):
                try:
                    await channel.send(self._format_new_quest(new_quest))
                except Exception:
                    logging.exception(
                        "New quest announcement failed; queued for retry: %s",
                        completion_key,
                    )
                    continue
                event["new_quest_sent"] = True
                self._save_quest_completion_state()

            if not event.get("bluesky_sent"):
                continue

            self._announced_quest_completion_keys.add(completion_key)
            del self._pending_quest_completions[completion_key]
            self._save_quest_completion_state()
            logging.info("Quest completion announced: %s", completion_key)

    def _load_quest_completion_state(self):
        """Restore undelivered quest announcements from disk."""
        try:
            if not os.path.exists(Config.QUEST_COMPLETION_STATE_FILE):
                return
            with open(Config.QUEST_COMPLETION_STATE_FILE, "r", encoding="utf-8") as state_file:
                saved_state = json.load(state_file)
            if isinstance(saved_state, dict):
                events = saved_state.get("events", [])
                self._last_bluesky_quest_post_date = saved_state.get(
                    "last_bluesky_quest_post_date"
                )
            else:
                # Backward compatibility with the original list-only file.
                events = saved_state
            for event in events:
                completed_quest = event.get("completed_quest") or {}
                event.setdefault("completion_sent", False)
                event.setdefault("bluesky_sent", False)
                event.setdefault("new_quest_sent", False)
                self._pending_quest_completions[
                    self._quest_completion_key(completed_quest)
                ] = event
        except Exception as e:
            logging.error(f"Could not load quest completion state: {e}")

    def _save_quest_completion_state(self):
        """Atomically persist quest announcement state."""
        state_path = Config.QUEST_COMPLETION_STATE_FILE
        temp_path = f"{state_path}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as state_file:
                json.dump({
                    "events": list(self._pending_quest_completions.values()),
                    "last_bluesky_quest_post_date": self._last_bluesky_quest_post_date,
                }, state_file, ensure_ascii=False)
            os.replace(temp_path, state_path)
        except Exception as e:
            logging.error(f"Could not save quest completion state: {e}")

    async def side_effects_loop(self):
        """Run operational side-effects on a steady cadence, decoupled from refresh."""
        await self._state_ready.wait()
        logging.info("Starting side effects loop")

        last_shutdown_notice_date = None

        while True:
            try:
                est = pytz.timezone("US/Eastern")
                now_est = datetime.now(est)

                midnight_next = (now_est + timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                minutes_until = int((midnight_next - now_est).total_seconds() // 60)

                # OFF window: last 10 min before midnight + first 10 min after
                off_window = (
                    (0 < minutes_until <= 10)
                    or (now_est.hour == 0 and now_est.minute < 10)
                )

                if off_window:
                    if self.bluesky_client:
                        await asyncio.to_thread(
                            bluesky_live.clear_live, self.bluesky_client
                        )

                    if (
                        0 < minutes_until <= 10
                        and last_shutdown_notice_date != now_est.date()
                    ):
                        last_shutdown_notice_date = now_est.date()
                        if self.connected_channels:
                            await self.connected_channels[0].send(
                                f"🛌 The Walker will rest for the night in {minutes_until} minutes, "
                                "at midnight EST. They'll be back in the morning!"
                            )
                else:
                    if self.bluesky_client:
                        title = self.state.get("bluesky_live_text") or "Live"
                        await asyncio.to_thread(
                            bluesky_live.ensure_live,
                            self.bluesky_client,
                            title,
                            "",
                        )

            except Exception as e:
                logging.error(f"side_effects_loop error: {e}")

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
        """Refresh cached data and reliably process completion events."""
        if getattr(self, "_dev_mode", False):
            logging.info("Skipping server refresh in dev mode")
            return False
        async with self._refresh_lock:
            try:
                data = await self.get_map_json_data()
                response = await asyncio.to_thread(post_to_django, data)
                if response and response.status_code == 201:
                    new_data = response.json()
                    await self._check_and_announce_quest_completion(new_data)
                    self._latest_response_data = new_data
                    self._latest_response_at = datetime.now(timezone.utc)
                    self._latest_command_state = new_data.get("command_state")
                    log = new_data.get("log") or {}
                    position = (log.get("world_x"), log.get("world_z"))
                    if None not in position:
                        self._recent_world_positions.append(position)
                        self._recent_world_positions = self._recent_world_positions[-2:]
                    return True
            except Exception:
                logging.exception("refresh_now error")
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
                logging.error("Daggerfall Unity process not found; assuming crash")
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
        if self._dev_mode:
            return
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
        command = Config.COMMAND_ALIASES.get(command, command)
        args = parts[1:] if len(parts) > 1 else []

        # This file is uploaded on the next production refresh, so never mix in dev commands.
        if not getattr(self, "_dev_mode", False):
            try:
                ts = datetime.now(timezone.utc).isoformat()
                logline = f"{ts} | {message.author.name} | {command} | {' '.join(args)}\n"
                async with aiofiles.open("chat_commands_log.txt", mode="a") as f:
                    await f.write(logline)
            except Exception as e:
                logging.error(f"Failed to log chat command: {e}")

        # Handle voting commands
        if command in self.votable_commands:
            if self.voting_active:
                await message.channel.send("A vote is already in progress!")
                return
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
            "walk": lambda: self.start_walking(message.channel),
            "back": lambda: self.send_movement(GameKeys.BACK, args),
            "forward": lambda: self.send_movement(GameKeys.FORWARD, args),
            "left": lambda: self.send_movement(GameKeys.LEFT, args),
            "right": lambda: self.send_movement(GameKeys.RIGHT, args),
            "up": lambda: self.send_movement(GameKeys.UP, args),
            "down": lambda: self.send_movement(GameKeys.DOWN, args),
            "jump": lambda: self.send_movement(GameKeys.JUMP, repeat=10),
            "stop": lambda: self.stop_movement(message.channel),
            "use": lambda: self.send_movement(GameKeys.USE),
            "cursor": self.toggle_cursor,
            "click": self.send_click,
            "map": self.toggle_map,
            "bighop": self.bighop,
            "shotgun": self.use_shotgun,
            "save": lambda: self.admin_command(message, self.save_game),
            "load": lambda: self.admin_command(message, self.load_game),
            "modlist": self.modlist,
            "help": lambda: self.help(args),
            "exec": lambda: self.admin_command(message, lambda: self.exec_command(args)),
            "killall": self.killall,
            "info": self.game_info,
            "more": self.more_commands,
            "quest": lambda: self.quest(args),
            "state": self.show_state,
        }

        if command in command_map:
            self._start_command_task(command, command_map[command])

    async def admin_command(self, message, cmd):
        """Execute admin-only commands"""
        if message.author.name.lower() in Config.AUTHORIZED_USERS:
            await cmd()

    @staticmethod
    def _movement_amount(args):
        if not args:
            return Config.DEFAULT_MOVEMENT_AMOUNT
        try:
            value = float(args[0])
        except (TypeError, ValueError):
            return Config.DEFAULT_MOVEMENT_AMOUNT
        if not math.isfinite(value):
            return Config.DEFAULT_MOVEMENT_AMOUNT
        return max(1.0, min(float(Config.MAX_INPUT_REPEATS), value))

    async def send_movement(self, key: GameKeys, args=None, repeat=1):
        """Handle movement and action commands"""
        amount = self._movement_amount(args)
        logging.info(f"Sending movement: {key.name} ({amount:g})")
        view_directions = {
            GameKeys.LEFT: (-amount, 0),
            GameKeys.RIGHT: (amount, 0),
            GameKeys.UP: (0, -amount),
            GameKeys.DOWN: (0, amount),
        }
        if key in view_directions:
            if await asyncio.to_thread(focus_game_window):
                yaw, pitch = view_directions[key]
                self._movement.add_view(yaw, pitch)
            return

        if key in (GameKeys.FORWARD, GameKeys.BACK):
            if await asyncio.to_thread(focus_game_window):
                self._movement.add_translation(
                    amount if key == GameKeys.FORWARD else -amount
                )
            return

        await asyncio.to_thread(send_game_input, key.value, repeat, 0.15)

    async def start_walking(self, channel):
        await self.send_movement(GameKeys.WALK)
        await channel.send("Autowalk started.")

    async def stop_movement(self, channel):
        """Cancel pending/held movement immediately and stop the autowalk mod."""
        self._movement.cancel_all()
        async with self._game_ui():
            await asyncio.to_thread(send_game_input, GameKeys.BACK.value, 1, 0.1)
        await channel.send("All movement stopped.")

    async def toggle_cursor(self):
        async with self._game_ui():
            await asyncio.to_thread(send_game_input, GameKeys.CURSOR.value)

    async def send_click(self):
        async with self._game_ui():
            if await asyncio.to_thread(focus_game_window):
                await asyncio.to_thread(left_click)

    def validate_song_arg(self, args):
        """Validate song selection"""
        default_msg = f'Specify song number (-1 to 131), "category" or "random."  ex - !song 127.  Full list: https://kershner.org/daggerwalk/?tab=songs'
        
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
            return False, f"Specify weather type: {', '.join(Config.WEATHER_TYPES_MAP.keys())}.  ex - !weather snowy"
        return True, None
    
    def validate_levitate_args(self, args):
        """Validate levitate selection"""
        if not args or args[0].lower() not in ["on", "off"]:
            return False, 'Specify levitate setting: "on" or "off." ex - !levitate on'
        return True, None
    
    def validate_gravity_args(self, args):
        """Validate gravity setting"""
        if not args or not args[0].isdigit() or not (0 <= int(args[0]) <= 20):
            return False, 'Set gravity level: 0–20 (0=low, 20=default).  ex - !gravity 5'
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
                    await message.channel.send("Choose categories for the song shuffle. Options: world, dungeon, misc, battle, all, off. Multiple categories supported. Ex: !song category world misc")
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
        if self.current_vote_type == "song":
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
        async with self._game_ui():
            if current_region == "Ocean":
                # No province to select for Ocean, so just open the map, wait a bit, and exit the map
                logging.info("Ocean region detected - using alternate map sequence")
                await asyncio.to_thread(send_game_input, GameKeys.MAP.value)
                await asyncio.sleep(7)
                await asyncio.to_thread(send_game_input, GameKeys.MAP.value)
            else:
                await asyncio.to_thread(send_game_input, GameKeys.MAP.value)
                await asyncio.sleep(3)
                await asyncio.to_thread(send_game_input, "{ENTER}")
                await asyncio.sleep(6)
                await asyncio.to_thread(send_game_input, GameKeys.MAP.value)
                await asyncio.sleep(2)
                await asyncio.to_thread(send_game_input, GameKeys.MAP.value)

    async def toggle_camera(self):
        """Toggle Third Person Camera mod in game"""
        logging.info("Executing camera command")
        await asyncio.sleep(1)
        await asyncio.to_thread(send_game_input, GameKeys.CAMERA.value)
        current = self.state.get("camera_mode", "first")
        new_mode = "third" if current == "first" else "first"
        self._update_state("camera_mode", new_mode)

    async def bighop(self):
        """Shortcut for common pattern to get unstuck"""
        logging.info("Executing BIGHOP command")
        if not await asyncio.to_thread(focus_game_window):
            return
        generation = self._movement.add_translation(-Config.MAX_INPUT_REPEATS)
        while self._movement.translation_active:
            if generation != self._movement.generation:
                return
            await asyncio.sleep(Config.CONTROL_TICK_SECONDS)
        await asyncio.to_thread(send_game_input, GameKeys.WALK.value)
        await self.send_movement(GameKeys.JUMP, repeat=10)

    async def use_shotgun(self):
        """Use shotgun weapon by raising weapon, firing, and then lowering it"""
        logging.info("Executing shotgun command")
        
        # Raise weapon
        logging.info("Raising weapon")
        await asyncio.to_thread(send_game_input, 'Z')
        await asyncio.sleep(0.5)
        
        # Fire weapon
        logging.info("Firing weapon")
        await asyncio.to_thread(send_game_input, 'X')
        
        # Wait before lowering weapon
        await asyncio.sleep(2)
        await asyncio.to_thread(send_game_input, 'Z')

    async def song(self, choice=None):
        """Change background music"""
        logging.info(f"Executing song command with choice: {choice}")
        
        await self.send_console_command(f"song {choice}")
        
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
        await self.send_console_command(f"song shuffle {categories_str}")
        
        await asyncio.sleep(5)
        
        channel = self.connected_channels[0]
        categories_str_display = ", ".join(categories)
        await channel.send(f'Song shuffle categories changed to: {categories_str_display}!')
        self._update_state("song_category", categories_str_display.lower())

    async def weather(self, weather_choice):
        """Change in-game weather"""
        logging.info(f"Executing weather command with choice: {weather_choice}")

        await self.send_console_command(f"set_weather {Config.WEATHER_TYPES_MAP.get(weather_choice)}")

        await asyncio.sleep(5)
        
        channel = self.connected_channels[0]
        weather_emoji = Config.WEATHER_EMOJIS.get(weather_choice.title(), "🌈")
        weather_display = Config.get_weather_display(weather_choice)
        await channel.send(f'Weather changed to: {weather_emoji}{weather_display}!')

    async def levitate(self, levitate_choice):
        """Toggle levitatation on/off"""
        logging.info(f"Executing levitate command with choice: {levitate_choice}")

        await self.send_console_command(f"levitate {levitate_choice}")

        await asyncio.sleep(5)
        
        channel = self.connected_channels[0]
        await channel.send(f'Levitate set to: {levitate_choice}!')
        self._update_state("levitate", levitate_choice.lower())

    async def toggle_enemy_ai(self):
        """Toggle enemy AI on/off"""
        logging.info("Executing toggle_enemy_ai command")

        await self.send_console_command("tai")

        await asyncio.sleep(5)
        
        channel = self.connected_channels[0]
        await channel.send("Toggled enemy AI!")
        current = self.state.get("ai_enabled", True)
        self._update_state("ai_enabled", not current)

    async def exit_building(self):
        """Teleport outside building/dungeon or do nothing"""
        logging.info("Executing exit command")

        await asyncio.to_thread(send_game_input, "=")
        
        await asyncio.sleep(5)
        
        channel = self.connected_channels[0]
        await channel.send("Teleported outside of current building, or did nothing if already outside.")

    async def set_gravity(self, gravity_level):
        """Set gravity level (0–20)"""
        logging.info(f"Executing gravity command with level: {gravity_level}")

        await self.send_console_command(f"set_grav {gravity_level}")

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
            async with self._game_ui():
                await asyncio.to_thread(self._send_console_command_sync, f"playvid {vid}")
                secs = durations.get(n, 10)
                await asyncio.sleep(secs)
                await asyncio.to_thread(send_game_input, GameKeys.ESC.value)
                await asyncio.to_thread(send_game_input, GameKeys.ESC.value)
                await asyncio.to_thread(send_game_input, GameKeys.CONSOLE.value)
        except Exception as e:
            logging.error(f"playvid error: {e}")
            if self.connected_channels:
                await self.connected_channels[0].send("Failed to play that video.")

    async def killall(self):
        """Kill all enemies"""
        logging.info("Executing killall command")
        await self.send_console_command("killall")
   
    async def send_console_command(self, command: str):
        """Serialize only the console transaction, not unrelated chat commands."""
        async with self._game_ui():
            await asyncio.to_thread(self._send_console_command_sync, command)

    def _send_console_command_sync(self, command: str):
        """Send command through game console"""
        logging.info(f"Sending console command: {command}")
        
        try:
            dialog = get_game_dialog()
            if dialog is None:
                return

            dialog.send_keystrokes(GameKeys.CONSOLE.value)
            time.sleep(0.5)
            pyautogui.write(command)
            time.sleep(0.5)
            dialog.send_keystrokes("{ENTER}")
            time.sleep(1)
            dialog.send_keystrokes(GameKeys.CONSOLE.value)
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

    @staticmethod
    def get_qualified_season(date_str: str) -> str:
        """Return the early/mid/late season represented by a Daggerfall date."""
        season_map = [
            ("Winter", ["eveningstar", "morningstar", "sunsdawn"]),
            ("Spring", ["firstseed", "rainshand", "secondseed"]),
            ("Summer", ["midyear", "sunsheight", "lastseed"]),
            ("Autumn", ["hearthfire", "frostfall", "sunsdusk"]),
        ]

        try:
            month = date_str.split(',')[1].strip().split(' ', 1)[1]
            month_key = month.lower().replace("'", "").replace(" ", "")
            for season, months in season_map:
                if month_key in months:
                    phase = ["early", "mid", "late"][months.index(month_key)]
                    return f"{phase} {season}"
        except (AttributeError, IndexError):
            pass

        return ""

    def build_live_text(
        self,
        region: str,
        weather: str,
        time_str: str,
        date_str: str = "",
        last_known_region: str = "",
    ) -> str:
        game_time = datetime.strptime(time_str, "%H:%M:%S")
        hour = game_time.hour
        if 6 <= hour < 12:
            time_of_day = "morning"
        elif 12 <= hour < 18:
            time_of_day = "afternoon"
        elif 18 <= hour < 21:
            time_of_day = "evening"
        else:
            time_of_day = "night"
        qualified_season = self.get_qualified_season(date_str)
        weather_display = Config.get_weather_display(weather).lower()
        conditions = " ".join(filter(None, [weather_display, qualified_season, time_of_day]))
        clock_time = game_time.strftime("%I:%M %p").lstrip("0").lower()
        clock_time = clock_time.replace(":00 ", " ")
        place = region
        if region.strip().lower() == "ocean":
            place = "the ocean"
            if last_known_region:
                place += f" near {last_known_region}"
        return f"Walking through {place} on a {conditions} ({clock_time})"

    async def update_stream_title(
        self,
        region: str,
        weather: str,
        time_str: str,
        date_str: str = "",
        last_known_region: str = "",
    ):
        try:
            title = self.build_live_text(
                region, weather, time_str, date_str, last_known_region
            )

            client_id, oauth_token = Config.get_oauth()

            if oauth_token.startswith("oauth:"):
                oauth_token = oauth_token[6:]

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.twitch.tv/helix/users",
                    headers={
                        "Client-ID": client_id,
                        "Authorization": f"Bearer {oauth_token}",
                    }
                ) as resp:
                    data = await resp.json()
                    broadcaster_id = data["data"][0]["id"]

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
        
        try:
            # Ensure we have cached data; do a one-shot refresh if empty or very stale
            if not self._latest_response_data or (
                self._latest_response_at and
                (datetime.now(timezone.utc) - self._latest_response_at).total_seconds() > Config.REFRESH_INTERVAL * 2
            ):
                ok = await self.refresh_now()
                if not ok and self.connected_channels:
                    await self.connected_channels[0].send("No info yet. Gathering data…")
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
            weather_display = Config.get_weather_display(weather)
            season_emoji = Config.SEASON_EMOJIS.get(season, "❓")
            season_display = self.get_qualified_season(date_str) or season

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
                f"{season_emoji}{season_display}" if season_display else "",
                f"{weather_emoji}{weather_display}" if weather else "",
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
                live_text = self.build_live_text(
                    region or "", weather or "", time_hms, date_str, last_known_name
                )
                self._update_state("bluesky_live_text", live_text)
                await self.update_stream_title(
                    region or "", weather or "", time_hms, date_str, last_known_name
                )

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
            positions = getattr(self, "_recent_world_positions", [])
            if len(positions) < 2:
                logging.info("Not enough locally cached positions for stuck check")
                return

            pos1, pos2 = positions[-1], positions[-2]
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

            command_state = getattr(self, "_latest_command_state", None)
            if not isinstance(command_state, dict):
                logging.warning("Command state unavailable; deferring stuck recovery")
                return

            last_stop = command_state.get("last_stop") or {}
            last_walk = command_state.get("last_walk") or {}
            stop_id = last_stop.get("id", 0)
            walk_id = last_walk.get("id", 0)
            logging.info(f"Last stop ID: {stop_id}, last walk ID: {walk_id}")

            # only consider stop newer than walk if the stop is from today
            if last_stop:
                stop_created = last_stop.get("timestamp")
                logging.info(f"Last stop timestamp: {stop_created}")
                if stop_created:
                    # handle ISO8601 with optional 'Z'
                    stop_time = datetime.fromisoformat(stop_created.replace("Z", "+00:00"))
                    if stop_time.tzinfo is None:
                        stop_time = est.localize(stop_time)
                    stop_date = stop_time.astimezone(est).date()
                    today = datetime.now(est).date()
                    logging.info(f"Stop time: {stop_time}, today: {today}")
                    if stop_date == today and stop_id > walk_id:
                        logging.info("Recent stop command found - not attempting unstuck")
                        return

            # Use the piggybacked latest command to alternate recovery after bighop.
            last_command = command_state.get("last_command") or {}
            last_cmd = (last_command.get("command") or "").lower() or None
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

    async def help(self, args=None):
        """List commands or describe one command and its aliases."""
        logging.info("Executing help command")
        channel = self.connected_channels[0]

        if args:
            requested = args[0].lower().lstrip("!")
            command = Config.COMMAND_ALIASES.get(requested, requested)
            detail = Config.COMMAND_HELP.get(command)
            if not detail:
                await channel.send(f"Unknown command: !{requested}. Use !help for the command list.")
                return
            aliases = [
                f"!{alias}" for alias, target in Config.COMMAND_ALIASES.items()
                if target == command
            ]
            suffix = f" • Aliases: {', '.join(aliases)}" if aliases else ""
            await channel.send(f"!{command}: {detail}{suffix}")
            return

        commands_text = " • ".join(f"!{command}" for command in Config.HELP_COMMANDS)
        await channel.send(
            f"💀🌲Daggerwalk Commands: {commands_text} "
            "• Details: !help <command>"
        )

    async def more_commands(self):
        """Display more commands"""
        logging.info("Executing more commands")
        channel = self.connected_channels[0]
        commands_text = " • ".join(f"!{command}" for command in Config.MORE_COMMANDS)
        await channel.send(
            f"🗡️More Daggerwalk Commands: {commands_text} • Details: !help <command>"
        )
    
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
        await asyncio.to_thread(send_game_input, GameKeys.SAVE.value)

    async def load_game(self):
        """Load last save"""
        logging.info("Executing load command")
        await asyncio.to_thread(send_game_input, GameKeys.LOAD.value)

    async def exec_command(self, args):
        """Execute console command (admin only)"""
        if not args:
            await self.connected_channels[0].send("Usage: !exec <command> <args>")
            return
        logging.info(f"Executing admin command: {' '.join(args)}")
        await self.send_console_command(" ".join(args))

    def _get_quests_from_response(self, response_data):
        """Return active and completed quest lists with legacy API fallbacks."""
        active_quests = response_data.get("active_quests")
        if active_quests is None:
            current_quest = response_data.get("current_quest") or {}
            active_quests = [current_quest] if current_quest else []

        completed_quests = response_data.get("completed_quests")
        if completed_quests is None:
            completed_quest = response_data.get("completed_quest") or {}
            completed_quests = [completed_quest] if response_data.get("quest_completed") and completed_quest else []

        active_quests.sort(key=lambda quest: quest.get("slot") or 99)
        return active_quests, completed_quests

    def _format_quest_summary(self, active_quests):
        parts = []
        for quest in active_quests:
            poi = quest.get("poi") or {}
            region = poi.get("region") or {}
            destination = f"{poi.get('emoji') or ''}{poi.get('name') or 'Unknown'}"
            if region.get("name"):
                destination += f", {region['name']}"
            parts.append(f"[{quest.get('slot')}] {destination} • {quest.get('xp', 0)} XP")

        if not parts:
            return "The Walker does not currently have any active quests."
        detail_commands = " • ".join(
            f"!quest {quest.get('slot')}" for quest in active_quests
        )
        return (
            f"🧭 {len(parts)} active quests: {' • '.join(parts)} "
            f"Details: {detail_commands} 🗺️Map: https://kershner.org/daggerwalk"
        )

    def _format_quest_detail(self, quest):
        poi = quest.get("poi") or {}
        description = (quest.get("description") or quest.get("quest_name") or "Quest").strip()
        giver = quest.get("quest_giver_name")
        line = f"🧭Quest {quest.get('slot')}: {description}"
        if giver:
            line += f" • {giver}"
        line += f" • {quest.get('xp', 0)} XP"

        x = poi.get("map_pixel_x")
        y = poi.get("map_pixel_y")
        url = "https://kershner.org/daggerwalk"
        if x is not None and y is not None:
            url += f"?map_focus_x={x}&map_focus_y={y}"
        return f"{line} 🗺️Map: {url}"

    def _format_quest_completion(self, quest):
        name = quest.get("quest_name") or quest.get("poi_name") or "Quest"
        line = f"✅Quest {quest.get('slot')}: {name} completed!"
        if quest.get("xp") not in (None, "", 0):
            line += f"  {quest['xp']} XP awarded!"
        return line

    def _format_new_quest(self, quest):
        """Format the replacement quest paired with a completion announcement."""
        poi = quest.get("poi") or {}
        name = quest.get("quest_name") or quest.get("description") or "Quest"
        line = f"📜New Quest {quest.get('slot')}: {name}"
        giver = quest.get("quest_giver_name")
        if giver:
            line += f" • {giver}"
        line += f" • {quest.get('xp', 0)} XP"

        url = "https://kershner.org/daggerwalk"
        x = poi.get("map_pixel_x")
        y = poi.get("map_pixel_y")
        if x is not None and y is not None:
            url += f"?map_focus_x={x}&map_focus_y={y}"
        return f"{line} 🗺️Map: {url}"

    async def quest(self, args=None):
        """Report all active quests, or details for one stable slot."""
        try:
            cache_age = (
                (datetime.now(timezone.utc) - self._latest_response_at).total_seconds()
                if self._latest_response_at else None
            )
            if not self._latest_response_data or (
                cache_age is not None and cache_age > Config.REFRESH_INTERVAL * 2
            ):
                ok = await self.refresh_now()
                if not ok:
                    if self.connected_channels:
                        await self.connected_channels[0].send("No quest info available yet.")
                    return

            active_quests, _ = self._get_quests_from_response(self._latest_response_data)

            if self.connected_channels:
                if args:
                    if len(args) != 1 or args[0] not in ("1", "2", "3"):
                        await self.connected_channels[0].send("Usage: !quest or !quest <1-3>")
                        return
                    slot = int(args[0])
                    selected = next((quest for quest in active_quests if quest.get("slot") == slot), None)
                    if not selected:
                        await self.connected_channels[0].send(f"Quest slot {slot} is not active yet.")
                        return
                    await self.connected_channels[0].send(self._format_quest_detail(selected))
                else:
                    await self.connected_channels[0].send(self._format_quest_summary(active_quests))

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
