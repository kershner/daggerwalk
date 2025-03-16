from datetime import datetime, timezone
from twitchio.ext import commands
from datetime import datetime
import pygetwindow as gw
from enum import Enum
import pywinauto
import aiofiles
import requests
import logging
import asyncio
import json
import time
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

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

class Config:
    """Bot configuration settings"""
    PARAMS_FILE = "parameters.json"
    TWITCH_CHANNEL = "daggerwalk"
    BOT_USERNAME = "daggerwalk_bot"
    AUTOSAVE_INTERVAL = 600  # 10 minutes
    CHAT_DELAY = 1.5  # seconds
    VOTING_DURATION = 30  # seconds
    AUTHORIZED_USERS = ["billcrystals", "daggerwalk", "daggerwalk_bot"]
    MAX_INPUT_REPEATS = 100
    DJANGO_LOG_URL = 'https://www.kershner.org/daggerwalk/log/'
    
    ACTIVE_MODS = [
        "World of Daggerfall", "Interesting Eroded Terrains",
        "Wilderness Overhaul", "Basic Roads", "Dynamic Skies", "Real Grass"
    ]

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
        window = next((w for w in gw.getWindowsWithTitle("Daggerfall Unity") 
                      if w.title == "Daggerfall Unity"), None)
        if not window:
            logging.warning("Game window not found")
            return
            
        app = pywinauto.Application().connect(handle=window._hWnd)
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
            "reset": reset
        }

        logging.info(f"Posting to Django: {Config.DJANGO_LOG_URL}")

        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        response = requests.post(
            Config.DJANGO_LOG_URL,
            json=payload,
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 201:
            logging.info(f"Successfully posted to Django. Response: {response.json()}")
        else:
            logging.warning(f"Django post returned non-201 status: {response.status_code}. Response: {response.text}")

    except requests.Timeout:
        logging.error(f"Timeout posting to Django after 5s: {Config.DJANGO_LOG_URL}")
    except requests.ConnectionError:
        logging.error(f"Connection error posting to Django: {Config.DJANGO_LOG_URL}")
    except Exception as e:
        logging.error(f"Error posting to Django: {str(e)}")

class DaggerfallBot(commands.Bot):
    def __init__(self):
        client_id, oauth = Config.get_oauth()
        super().__init__(token=oauth, prefix="!", initial_channels=[Config.TWITCH_CHANNEL])
        
        self.last_autosave = datetime.now(timezone.utc)
        self.voting_active = False
        self.current_vote_type = None
        self.current_vote_message = None
        self.votes = {}
        
        self.votable_commands = {
            "reset": "reset to last known location",
            "song": "change the background music"
        }

    async def event_ready(self):
        logging.info(f"Bot online as {self.nick}")
        self.autosave_task = asyncio.create_task(self.autosave_loop())
        self.message_task = asyncio.create_task(self.message_scheduler())

    async def message_scheduler(self):
        """Schedules periodic info (5min) and help (20min) messages"""
        logging.info("Starting message scheduler")
        INFO_INTERVAL = 300  # 5 minutes in seconds
        HELP_INTERVAL = 1200  # 20 minutes in seconds
        HELP_OFFSET = 360  # 6 minute offset
        
        async def run_periodic_message(message_func, interval, initial_delay=0):
            # Wait for initial delay before first execution
            if initial_delay > 0:
                await asyncio.sleep(initial_delay)
                
            while True:
                await message_func()
                await asyncio.sleep(interval)
        
        # Create tasks with appropriate initial delays
        info_task = asyncio.create_task(run_periodic_message(self.game_info, INFO_INTERVAL))
        help_task = asyncio.create_task(run_periodic_message(self.help, HELP_INTERVAL, HELP_OFFSET))
        
        # Wait for both tasks indefinitely
        await asyncio.gather(info_task, help_task)

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

    async def event_message(self, message):
        """Handle incoming chat messages and commands"""
        if not message.author:
            return

        logging.info(f"Chat: {message.author.name}: {message.content}")
        
        parts = message.content.split()
        if not parts[0].startswith("!"):
            return
            
        command = parts[0][1:].lower()  # Remove ! prefix
        args = parts[1:] if len(parts) > 1 else []

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
            "back": lambda: self.send_movement(GameKeys.BACK, args),
            "forward": lambda: self.send_movement(GameKeys.FORWARD, args),
            "left": lambda: self.send_movement(GameKeys.LEFT, args),
            "right": lambda: self.send_movement(GameKeys.RIGHT, args),
            "up": lambda: self.send_movement(GameKeys.UP, args),
            "down": lambda: self.send_movement(GameKeys.DOWN, args),
            "jump": lambda: self.send_movement(GameKeys.JUMP),
            "stop": lambda: self.send_movement(GameKeys.BACK, repeat=1),
            "map": self.toggle_map,
            "save": self.save_game,
            "load": lambda: self.admin_command(message, self.load_game),
            "modlist": self.modlist,
            "help": self.help,
            "exec": lambda: self.admin_command(message, lambda: self.exec_command(args)),
            "esc": lambda: self.send_movement(GameKeys.ESC, args),
            "killall": self.killall,
            "info": self.game_info
        }

        if command in command_map:
            await command_map[command]()

    async def admin_command(self, message, cmd):
        """Execute admin-only commands"""
        if message.author.name.lower() in Config.AUTHORIZED_USERS:
            await cmd()

    async def send_movement(self, key: GameKeys, args=None, repeat=1):
        """Handle movement and action commands"""
        if args and args[0].isdigit():
            repeat = min(max(int(args[0]), 1), Config.MAX_INPUT_REPEATS)
        logging.info(f"Sending movement: {key.name} ({repeat} times)")
        send_game_input(key.value, repeat=repeat, delay=0.15)

    def validate_song_arg(self, args):
        """Validate song selection"""
        songs_tab_link = "Song List: https://kershner.org/daggerwalk?tab=songs"
        default_msg = f'Specify song number (-1 to 131), "category" or "random". {songs_tab_link}'
        
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

    async def start_vote(self, message, vote_type):
        if self.voting_active:
            await message.channel.send("A vote is already in progress!")
            return

        # Special handling for song category command
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

    async def killall(self):
        """Kill all enemies"""
        logging.info("Executing killall command")
        self.send_console_command("killall")

    def send_console_command(self, command: str):
        """Send command through game console"""
        logging.info(f"Sending console command: {command}")
        send_game_input(GameKeys.CONSOLE.value)  # Open console
        time.sleep(0.5)
        send_game_input(command)  # Send command
        time.sleep(0.1)
        send_game_input("{ENTER}")  # Send ENTER separately
        time.sleep(1)
        send_game_input(GameKeys.CONSOLE.value)  # Close console

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

    async def game_info(self):
        """Display game state information"""
        try:
            # Load map data
            data = await self.get_map_json_data()
            
            # Cache music tracks and track map if not already done
            if not hasattr(self, '_music_tracks'):
                music_data_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 
                                            'list_music_tracks.json')
                self._music_tracks = await self.load_json_async(music_data_path)
                self._track_map = {track['TrackName']: track['TrackID'] for track in self._music_tracks}

            # Convert time
            date_parts = data['date'].split(',')
            time = datetime.strptime(date_parts[-1].strip(), '%H:%M:%S')
            time_12hr = time.strftime('%I:%M %p').lstrip('0')
            date = f"{','.join(date_parts[:-1]).strip()}, {time_12hr}"

            # Season lookup
            month = date_parts[1].strip().split(" ", 1)[-1]  # Extract month
            season = {
                "Morning Star": "Winter", 
                "Sun's Dawn": "Winter", 
                "Evening Star": "Winter",
                "First Seed": "Spring", 
                "Rain's Hand": "Spring",
                "Second Seed": "Summer", 
                "Midyear": "Summer", 
                "Last Seed": "Summer", 
                "Hearthfire": "Autumn", 
                "Sun's Dusk": "Autumn", 
                "Frostfall": "Autumn"
            }.get(month, "Unknown")

            # Emoji mappings
            weather_emoji = {
                "Sunny": "☀️", "Clear": "🌙", "Cloudy": "☁️", "Foggy": "🌫️",
                "Rainy": "🌧️", "Snowy": "🌨️", "Thunderstorm": "⛈️", "Blizzard": "❄️"
            }.get(data['weather'], "🌈")

            season_emoji = {
                "Winter": "☃️", "Spring": "🌸", "Summer": "🌻", "Autumn": "🍂"
            }.get(season, "❓")

            # Get current song info
            current_song = data.get('currentSong', '')
            track_id = self._track_map.get(current_song, 'Unknown')
            music_info = f"🎵 {current_song} (Track {track_id})" if current_song else ""

            # Build status message efficiently
            map_link = f"🗺️ Map: https://kershner.org/daggerwalk?region={data['region'].replace(' ', '+')}"
            status = " • ".join(filter(None, [
                f"🌍 {data['region']}", f"📍 {data['location']}", f"📅 {date}",
                f"{season_emoji} {season}", f"{weather_emoji} {data['weather']}", music_info, map_link
            ]))
            
            # Async API request
            post_to_django(data)

            logging.info(f"Game status: {status}")

            # Send message asynchronously
            if self.connected_channels:
                channel = self.connected_channels[0]
                await channel.send(status)

        except Exception as e:
            logging.error(f"Info error: {e}")

    async def help(self):
        """Display available commands"""
        logging.info("Executing help command")
        channel = self.connected_channels[0]
        
        combined_message = (
            "💀🌲Daggerwalk Commands: "
            "!walk • !stop • !jump • !esc • !left [num] • "
            "!right [num] • !up [num] • !down [num] • !forward [num] • "
            "!back [num] • !map • !modlist • !song • !reset"
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

if __name__ == "__main__":
    bot = DaggerfallBot()
    bot.run()