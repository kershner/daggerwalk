"""Shared repository paths used by Daggerwalk's runtime components."""

from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent
RUNTIME_DIR = REPO_ROOT / "runtime"
DATA_DIR = REPO_ROOT / "data"


def _local_file(directory: Path, filename: str) -> Path:
    """Move a legacy root file when possible, otherwise keep using it."""
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / filename
    legacy = REPO_ROOT / filename
    if legacy.is_file() and not destination.exists():
        try:
            legacy.replace(destination)
        except OSError:
            return legacy
    return destination


PARAMETERS_FILE = REPO_ROOT / "parameters.json"
MUSIC_TRACKS_FILE = _local_file(DATA_DIR, "list_music_tracks.json")
LOG_FILE = _local_file(RUNTIME_DIR, "daggerwalk.log")
SUPERVISOR_LOG_FILE = _local_file(RUNTIME_DIR, "supervisor.log")
CHAT_COMMANDS_FILE = _local_file(RUNTIME_DIR, "chat_commands_log.txt")
DEV_CHAT_COMMANDS_FILE = _local_file(RUNTIME_DIR, "dev_chat_commands_log.txt")
LOCAL_STATE_FILE = _local_file(RUNTIME_DIR, "daggerwalk_state.json")
QUEST_COMPLETION_STATE_FILE = _local_file(RUNTIME_DIR, "quest_completion_state.json")
DEV_QUEST_COMPLETION_STATE_FILE = _local_file(
    RUNTIME_DIR, "dev_quest_completion_state.json"
)
PROGRESSION_CACHE_FILE = _local_file(RUNTIME_DIR, "progression_cache.json")
DEV_PROGRESSION_CACHE_FILE = _local_file(RUNTIME_DIR, "dev_progression_cache.json")
READY_FLAG = RUNTIME_DIR / "dfu_ready.flag"


def ensure_runtime_dir() -> None:
    """Create the ignored runtime directory before a component writes to it."""
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
