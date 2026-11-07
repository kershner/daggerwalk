"""Live status and explicit state requests for the DFU Cinematic Camera mod."""
import asyncio
import json
import math
import os
from pathlib import Path
import tempfile
import time
import uuid


CONTROL_DIR = (
    Path.home() / "AppData/LocalLow/Daggerfall Workshop/Daggerfall Unity/Mods/GameData"
    / "6b5c493e-179d-4f7c-8076-b59ed93cd650/Data"
)
UNAVAILABLE = "Cinematic camera is unavailable; enable the updated Cinematic Camera mod and load DFU."


def read_status(directory=None):
    try:
        status = json.loads((Path(directory or CONTROL_DIR) / "cinematic_camera_status.json").read_text(encoding="utf-8-sig"))
        age = time.time() - float(status["timestamp"])
        if (
            status.get("protocol") == 1 and status.get("running") is True
            and isinstance(status.get("enabled"), bool)
            and isinstance(status.get("session"), str) and status["session"]
            and math.isfinite(age) and 0 <= age <= 5
        ):
            return status
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return None


def get_cinematic_status():
    status = read_status()
    return None if status is None else status["enabled"]


def _write_request(directory, request):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, suffix=".tmp", delete=False) as file:
            temporary = file.name
            json.dump(request, file)
        os.replace(temporary, Path(directory) / "cinematic_camera_request.json")
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


async def set_cinematic_enabled(enabled, *, directory=None, timeout=3):
    """Return confirmed status; never synthesize a key or guess a toggle state."""
    directory = Path(directory or CONTROL_DIR)
    current = await asyncio.to_thread(read_status, directory)
    if current is None:
        raise RuntimeError(UNAVAILABLE)
    if current["enabled"] == enabled:
        return current
    request = {
        "protocol": 1, "id": uuid.uuid4().hex, "session": current["session"],
        "timestamp": time.time(), "action": "on" if enabled else "off",
    }
    try:
        await asyncio.to_thread(_write_request, directory, request)
    except OSError as error:
        raise RuntimeError("Could not send the cinematic camera request; try again.") from error
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = await asyncio.to_thread(read_status, directory)
        if status is not None:
            if status["session"] != request["session"]:
                raise RuntimeError("Cinematic camera restarted; try again.")
            if status.get("last_request_id") == request["id"] and status["enabled"] == enabled:
                return status
        await asyncio.sleep(0.1)
    raise RuntimeError("Cinematic camera did not confirm the request; try again.")
