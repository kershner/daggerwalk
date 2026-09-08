import asyncio
import re
import sys
import time
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch


# Bluesky is optional and unrelated to these quest-handling tests, so use a stub.
bluesky_stub = types.ModuleType("daggerwalk.bluesky")
bluesky_stub.login = lambda *args: None
bluesky_stub.clear_live = lambda *args: None
bluesky_stub.ensure_live = lambda *args: None
bluesky_stub.post_quest_completion = lambda *args: None
bluesky_stub.new_tid = lambda: "3jzfcijpj2z2a"
sys.modules.setdefault("daggerwalk.bluesky", bluesky_stub)

from daggerwalk import twitch_bot as bot_module
bot_module.bluesky_live = bluesky_stub


class RecordingChannel:
    def __init__(self, failures=0):
        self.failures = failures
        self.messages = []

    async def send(self, message):
        if self.failures:
            self.failures -= 1
            raise RuntimeError("temporary Twitch failure")
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
    bot._recent_world_positions = []
    bot._latest_command_state = None
    bot._stuck_anchor_position = None
    bot._last_world_movement_at = None
    bot._autowalk_active = True
    bot._last_unstuck_command = None
    bot._bot_started_at_monotonic = time.monotonic()
    bot._announced_quest_completion_keys = set()
    bot._pending_quest_completions = {}
    bot._last_bluesky_quest_post_date = None
    bot._last_quest_arrival_key = None
    bot._save_quest_completion_state = lambda: None
    bot.bluesky_client = None
    bot._test_channels = [] if channel is None else [channel]

    async def get_map_json_data():
        return {"mapPixelX": 1, "mapPixelY": 2}

    bot.get_map_json_data = get_map_json_data
    return bot


class QuestCompletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_interactive_info_uses_local_state_without_server_refresh(self):
        channel = RecordingChannel()
        bot = make_bot(channel)
        bot.state = {"bluesky_live_text": ""}
        bot._music_tracks = []
        bot._track_map = {}
        bot._latest_response_data = {
            "log": {
                "region": "Old Region",
                "location": "Old Place",
                "weather": "Snowy",
                "season": "Winter",
                "current_song": "Old Song",
                "date": "Morndas, 1 Morning Star, 3E 405, 01:00:00",
                "region_fk": {"climate": "Desert", "emoji": "OLD"},
                "poi": {"emoji": "STALE"},
            }
        }
        bot._latest_response_at = datetime.now(timezone.utc)
        bot.refresh_now = AsyncMock(return_value=True)

        async def get_local_data():
            return {
                "region": "Wayrest",
                "location": "Wayrest",
                "weather": "Rainy",
                "season": "Summer",
                "currentSong": "New Song",
                "date": "Tirdas, 12 Sun's Height, 3E 405, 18:30:00",
            }

        bot.get_map_json_data = get_local_data

        await bot.game_info(use_local=True)

        bot.refresh_now.assert_not_awaited()
        self.assertEqual(len(channel.messages), 1)
        self.assertIn("Wayrest", channel.messages[0])
        self.assertIn("Rainy", channel.messages[0])
        self.assertIn("6:30 PM", channel.messages[0])
        self.assertNotIn("Old Region", channel.messages[0])
        self.assertNotIn("STALE", channel.messages[0])

    async def test_local_quest_arrival_triggers_one_immediate_refresh(self):
        bot = make_bot()
        bot._latest_response_data = {
            "active_quests": [{
                "id": 42,
                "slot": 1,
                "poi": {"name": "Wayrest", "region": {"name": "Wayrest"}},
            }],
            "completed_quests": [],
        }
        bot.refresh_now = AsyncMock(return_value=True)
        local_data = {"location": " Wayrest ", "region": "WAYREST"}

        self.assertTrue(await bot._maybe_submit_quest_arrival(local_data))
        self.assertFalse(await bot._maybe_submit_quest_arrival(local_data))

        bot.refresh_now.assert_awaited_once()

    async def test_failed_local_quest_arrival_is_retried(self):
        bot = make_bot()
        bot._latest_response_data = {
            "active_quests": [{
                "id": 42,
                "slot": 1,
                "poi": {"name": "Wayrest", "region": {"name": "Wayrest"}},
            }],
            "completed_quests": [],
        }
        bot.refresh_now = AsyncMock(side_effect=[False, True])
        local_data = {"location": "Wayrest", "region": "Wayrest"}

        self.assertFalse(await bot._maybe_submit_quest_arrival(local_data))
        self.assertTrue(await bot._maybe_submit_quest_arrival(local_data))

        self.assertEqual(bot.refresh_now.await_count, 2)

    async def test_quest_command_uses_fresh_cached_response(self):
        channel = RecordingChannel()
        bot = make_bot(channel)
        bot._latest_response_data = {
            "active_quests": [
                {"id": 1, "slot": 1, "quest_name": "Travel to Wayrest", "xp": 20}
            ],
            "completed_quests": [],
        }
        bot._latest_response_at = datetime.now(timezone.utc)
        bot.refresh_now = AsyncMock(return_value=True)

        await bot.quest()

        bot.refresh_now.assert_not_awaited()
        self.assertEqual(len(channel.messages), 1)

    def test_local_position_samples_reset_inactivity_only_after_real_movement(self):
        bot = make_bot()

        self.assertTrue(bot._record_local_world_position({"worldX": 100, "worldZ": 200}, 10))
        bot._record_local_world_position({"worldX": 105, "worldZ": 205}, 40)
        self.assertEqual(bot._last_world_movement_at, 10)

        bot._record_local_world_position({"worldX": 111, "worldZ": 200}, 50)
        self.assertEqual(bot._last_world_movement_at, 50)
        self.assertEqual(bot._stuck_anchor_position, (111.0, 200.0))

    async def test_stuck_check_recovers_after_one_minute_without_server_call(self):
        channel = RecordingChannel()
        bot = make_bot(channel)
        bot._bot_started_at_monotonic = 0
        bot._stuck_anchor_position = (100.0, 200.0)
        bot._last_world_movement_at = 100
        bot.log_chat_command = AsyncMock()
        bot.bighop = AsyncMock()

        class Noon(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 9, 7, 12, tzinfo=tz)

        with (
            patch.object(bot_module, "datetime", Noon),
            patch.object(bot_module.time, "monotonic", side_effect=[160, 160, 160]),
            patch.object(bot_module.requests, "get") as get,
        ):
            await bot.check_if_bot_is_stuck()

        get.assert_not_called()
        bot.bighop.assert_awaited_once()
        self.assertEqual(bot._last_unstuck_command, "bighop")
        self.assertEqual(len(channel.messages), 2)

    async def test_stuck_check_does_not_recover_after_intentional_stop(self):
        bot = make_bot(RecordingChannel())
        bot._bot_started_at_monotonic = 0
        bot._stuck_anchor_position = (100.0, 200.0)
        bot._last_world_movement_at = 100
        bot._autowalk_active = False
        bot.bighop = AsyncMock()

        with patch.object(bot_module.time, "monotonic", return_value=1000):
            await bot.check_if_bot_is_stuck()

        bot.bighop.assert_not_awaited()

    async def test_background_refresh_sends_info_only_after_success(self):
        bot = make_bot()
        bot._state_ready = asyncio.Event()
        bot.refresh_now = AsyncMock(return_value=True)
        bot.game_info = AsyncMock()
        bot.check_if_bot_is_stuck = AsyncMock()

        with patch.object(
            bot_module.asyncio,
            "sleep",
            AsyncMock(side_effect=asyncio.CancelledError),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await bot.data_refresh_loop()

        bot.game_info.assert_awaited_once()
        self.assertTrue(bot._state_ready.is_set())

    async def test_failed_background_refresh_does_not_send_info(self):
        bot = make_bot()
        bot._state_ready = asyncio.Event()
        bot.refresh_now = AsyncMock(return_value=False)
        bot.game_info = AsyncMock()
        bot.check_if_bot_is_stuck = AsyncMock()

        with patch.object(
            bot_module.asyncio,
            "sleep",
            AsyncMock(side_effect=asyncio.CancelledError),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await bot.data_refresh_loop()

        bot.game_info.assert_not_awaited()
        self.assertFalse(bot._state_ready.is_set())

    async def test_quest_summary_uses_one_compact_detail_command(self):
        bot = make_bot()
        summary = bot._format_quest_summary([
            {
                "slot": 1,
                "xp": 25,
                "poi": {"emoji": "⚓", "name": "Zagizar", "region": {"name": "Mournoth"}},
            },
            {
                "slot": 2,
                "xp": 45,
                "poi": {"emoji": "🏹", "name": "Nozim Orchard", "region": {"name": "Sentinel"}},
            },
            {
                "slot": 3,
                "xp": 50,
                "poi": {"emoji": "🗿", "name": "The Greenton Plantation", "region": {"name": "Ykalon"}},
            },
        ])

        self.assertEqual(
            summary,
            "🧭 3 active quests: [1] ⚓Zagizar, Mournoth • 25 XP • "
            "[2] 🏹Nozim Orchard, Sentinel • 45 XP • "
            "[3] 🗿The Greenton Plantation, Ykalon • 50 XP • "
            "Details: !quest [num] • "
            "🗺️Map: https://kershner.org/daggerwalk",
        )

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
        ) as first_post:
            await bot._check_and_announce_quest_completion(payload)

        self.assertEqual(len(channel.messages), 2)
        event = bot._pending_quest_completions["id:7"]
        self.assertTrue(event["completion_sent"])
        self.assertTrue(event["new_quest_sent"])
        self.assertFalse(event["bluesky_sent"])
        self.assertRegex(
            event["bluesky_rkey"],
            re.compile(r"^[234567abcdefghij][234567abcdefghijklmnopqrstuvwxyz]{12}$"),
        )
        first_rkey = first_post.call_args.args[2]

        with patch.object(bot_module.bluesky_live, "post_quest_completion") as post:
            await bot._check_and_announce_quest_completion({
                "active_quests": payload["active_quests"],
                "completed_quests": [],
            })

        post.assert_called_once()
        self.assertEqual(post.call_args.args[2], first_rkey)
        self.assertEqual(len(channel.messages), 2)
        self.assertEqual(bot._pending_quest_completions, {})

    async def test_only_one_bluesky_quest_completion_is_posted_per_eastern_day(self):
        channel = RecordingChannel()
        bot = make_bot(channel)
        bot.bluesky_client = object()
        payload = {
            "active_quests": [
                {"id": 12, "slot": 1, "quest_name": "Next quest", "xp": 10},
                {"id": 13, "slot": 2, "quest_name": "Another quest", "xp": 15},
            ],
            "completed_quests": [
                {"id": 10, "slot": 1, "quest_name": "First quest"},
                {"id": 11, "slot": 2, "quest_name": "Second quest"},
            ],
        }

        with patch.object(bot_module.bluesky_live, "post_quest_completion") as post:
            await bot._check_and_announce_quest_completion(payload)

        post.assert_called_once()
        self.assertEqual(bot._pending_quest_completions, {})


if __name__ == "__main__":
    unittest.main()
