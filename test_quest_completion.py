import asyncio
import sys
import types
import unittest
from unittest.mock import patch


# The production module imports the optional Bluesky client at module load time. It is
# unrelated to quest handling and is not installed in the lightweight bot test venv.
bluesky_stub = types.ModuleType("bluesky_live")
bluesky_stub.login = lambda *args: None
bluesky_stub.clear_live = lambda *args: None
bluesky_stub.ensure_live = lambda *args: None
bluesky_stub.post_quest_completion = lambda *args: None
sys.modules.setdefault("bluesky_live", bluesky_stub)

import daggerwalk_twitch_bot as bot_module


class FakeResponse:
    status_code = 201

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class RecordingChannel:
    def __init__(self, failures=0):
        self.failures = failures
        self.messages = []

    async def send(self, message):
        if self.failures:
            self.failures -= 1
            raise RuntimeError("temporary Twitch failure")
        self.messages.append(message)


class SecondSendFailsOnceChannel(RecordingChannel):
    def __init__(self):
        super().__init__()
        self.calls = 0

    async def send(self, message):
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("temporary failure sending new quest")
        self.messages.append(message)


class TestDaggerfallBot(bot_module.DaggerfallBot):
    @property
    def connected_channels(self):
        return self._test_channels


def make_bot(channel=None):
    bot = object.__new__(TestDaggerfallBot)
    bot._refresh_lock = asyncio.Lock()
    bot._latest_response_data = None
    bot._latest_response_at = None
    bot._announced_quest_completion_keys = set()
    bot._pending_quest_completions = {}
    bot._save_quest_completion_state = lambda: None
    bot.bluesky_client = None
    bot._test_channels = [] if channel is None else [channel]

    async def get_map_json_data():
        return {"mapPixelX": 1, "mapPixelY": 2}

    bot.get_map_json_data = get_map_json_data
    return bot


class QuestCompletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_on_demand_refresh_announces_completion(self):
        channel = RecordingChannel()
        bot = make_bot(channel)
        payload = {
            "active_quests": [
                {
                    "id": 43,
                    "slot": 2,
                    "quest_name": "Travel to Wayrest",
                    "quest_giver_name": "Lady Brisienna",
                    "xp": 30,
                    "poi": {"map_pixel_x": 12, "map_pixel_y": 34},
                }
            ],
            "completed_quests": [
                {"id": 42, "slot": 2, "quest_name": "Reach Daggerfall", "xp": 250}
            ],
        }

        with patch.object(bot_module, "post_to_django", return_value=FakeResponse(payload)):
            self.assertTrue(await bot.refresh_now())

        self.assertEqual(
            channel.messages,
            [
                "✅Quest 2: Reach Daggerfall completed!  250 XP awarded!",
                "🆕New Quest 2: Travel to Wayrest — Lady Brisienna — 30 XP "
                "🗺️Map: https://kershner.org/daggerwalk?map_focus_x=12&map_focus_y=34",
            ],
        )
        self.assertEqual(bot._pending_quest_completions, {})

    async def test_failed_send_stays_queued_and_retries_without_duplicate(self):
        channel = RecordingChannel(failures=1)
        bot = make_bot(channel)
        payload = {
            "active_quests": [
                {"id": 100, "slot": 1, "quest_name": "Travel to Daggerfall", "xp": 15}
            ],
            "completed_quests": [{"id": 99, "slot": 1, "poi_name": "Wayrest"}],
        }

        await bot._check_and_announce_quest_completion(payload)
        self.assertIn("id:99", bot._pending_quest_completions)
        self.assertEqual(channel.messages, [])

        await bot._check_and_announce_quest_completion({"active_quests": [], "completed_quests": []})
        await bot._check_and_announce_quest_completion(payload)

        self.assertEqual(
            channel.messages,
            [
                "✅Quest 1: Wayrest completed!",
                "🆕New Quest 1: Travel to Daggerfall — 15 XP "
                "🗺️Map: https://kershner.org/daggerwalk",
            ],
        )
        self.assertEqual(bot._pending_quest_completions, {})

    async def test_legacy_completion_without_id_is_not_silently_dropped(self):
        channel = RecordingChannel()
        bot = make_bot(channel)
        payload = {
            "quest_completed": True,
            "completed_quest": {
                "slot": 3,
                "poi_name": "Sentinel",
                "completed_at": "2026-09-01T12:00:00Z",
            },
            "current_quest": {
                "slot": 3,
                "quest_name": "Travel to Wayrest",
                "xp": 20,
            },
        }

        await bot._check_and_announce_quest_completion(payload)

        self.assertEqual(
            channel.messages,
            [
                "✅Quest 3: Sentinel completed!",
                "🆕New Quest 3: Travel to Wayrest — 20 XP "
                "🗺️Map: https://kershner.org/daggerwalk",
            ],
        )
        self.assertEqual(bot._pending_quest_completions, {})

    async def test_new_quest_retry_does_not_repeat_completion(self):
        channel = SecondSendFailsOnceChannel()
        bot = make_bot(channel)
        payload = {
            "active_quests": [
                {"id": 8, "slot": 2, "quest_name": "Travel to Sentinel", "xp": 35}
            ],
            "completed_quests": [
                {"id": 7, "slot": 2, "quest_name": "Travel to Wayrest", "xp": 25}
            ],
        }

        await bot._check_and_announce_quest_completion(payload)
        self.assertEqual(
            channel.messages,
            ["✅Quest 2: Travel to Wayrest completed!  25 XP awarded!"],
        )
        self.assertTrue(bot._pending_quest_completions["id:7"]["completion_sent"])

        await bot._check_and_announce_quest_completion(
            {"active_quests": payload["active_quests"], "completed_quests": []}
        )

        self.assertEqual(
            channel.messages,
            [
                "✅Quest 2: Travel to Wayrest completed!  25 XP awarded!",
                "🆕New Quest 2: Travel to Sentinel — 35 XP "
                "🗺️Map: https://kershner.org/daggerwalk",
            ],
        )
        self.assertEqual(bot._pending_quest_completions, {})

    async def test_bluesky_retry_does_not_repeat_twitch_messages(self):
        channel = RecordingChannel()
        bot = make_bot(channel)
        bot.bluesky_client = object()
        payload = {
            "active_quests": [
                {"id": 8, "slot": 2, "quest_name": "Travel to Sentinel", "xp": 35}
            ],
            "completed_quests": [{
                "id": 7,
                "slot": 2,
                "quest_name": "Travel to Wayrest",
                "quest_giver_name": "Lady Brisienna",
                "quest_giver_img_url": "https://example.com/brisienna.png",
                "xp": 30,
            }],
        }

        with patch.object(
            bot_module.bluesky_live,
            "post_quest_completion",
            side_effect=RuntimeError("temporary Bluesky failure"),
        ):
            await bot._check_and_announce_quest_completion(payload)

        self.assertEqual(len(channel.messages), 2)
        event = bot._pending_quest_completions["id:7"]
        self.assertTrue(event["completion_sent"])
        self.assertTrue(event["new_quest_sent"])
        self.assertFalse(event["bluesky_sent"])

        with patch.object(bot_module.bluesky_live, "post_quest_completion") as post:
            await bot._check_and_announce_quest_completion({
                "active_quests": payload["active_quests"],
                "completed_quests": [],
            })

        post.assert_called_once()
        self.assertEqual(len(channel.messages), 2)
        self.assertEqual(bot._pending_quest_completions, {})


if __name__ == "__main__":
    unittest.main()
