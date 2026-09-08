import sys
import types
import unittest
from unittest.mock import AsyncMock, patch


bluesky_stub = types.ModuleType("daggerwalk.bluesky")
bluesky_stub.login = lambda *args: None
bluesky_stub.clear_live = lambda *args: None
bluesky_stub.ensure_live = lambda *args: None
sys.modules.setdefault("daggerwalk.bluesky", bluesky_stub)

from daggerwalk import twitch_bot as bot_module


class LiveTextTests(unittest.TestCase):
    def setUp(self):
        self.bot = object.__new__(bot_module.DaggerfallBot)

    def test_title_includes_qualified_season(self):
        title = self.bot.build_live_text(
            "Wayrest",
            "Rainy",
            "21:00:00",
            "Tirdas, 12 Sun's Height, 3E 405, 21:00:00",
        )

        self.assertEqual(
            title,
            "Walking through Wayrest on a rainy mid Summer night (9 pm)",
        )

    def test_each_month_maps_to_its_bluesky_season_phase(self):
        expected = {
            "Evening Star": "early Winter",
            "Morning Star": "mid Winter",
            "Sun's Dawn": "late Winter",
            "First Seed": "early Spring",
            "Rain's Hand": "mid Spring",
            "Second Seed": "late Spring",
            "Mid Year": "early Summer",
            "Sun's Height": "mid Summer",
            "Last Seed": "late Summer",
            "Hearthfire": "early Autumn",
            "Frostfall": "mid Autumn",
            "Sun's Dusk": "late Autumn",
        }

        for month, qualified_season in expected.items():
            with self.subTest(month=month):
                date_str = f"Tirdas, 12 {month}, 3E 405, 21:00:00"
                self.assertEqual(
                    self.bot.get_qualified_season(date_str), qualified_season
                )

    def test_missing_date_preserves_previous_title_format(self):
        title = self.bot.build_live_text("Wayrest", "Rainy", "21:00:00")

        self.assertEqual(title, "Walking through Wayrest on a rainy night (9 pm)")

    def test_title_keeps_minutes_when_not_on_the_hour(self):
        title = self.bot.build_live_text(
            "Wayrest",
            "Rainy",
            "18:30:00",
            "Tirdas, 12 Sun's Height, 3E 405, 18:30:00",
        )

        self.assertEqual(
            title,
            "Walking through Wayrest on a rainy mid Summer evening (6:30 pm)",
        )

    def test_ocean_title_uses_nearest_region(self):
        title = self.bot.build_live_text(
            "Ocean", "Rainy", "18:30:00", "", "Wayrest"
        )

        self.assertEqual(
            title,
            "Walking through the ocean near Wayrest on a rainy evening (6:30 pm)",
        )

    def test_thunderstorm_uses_present_participle_in_title(self):
        title = self.bot.build_live_text(
            "Wayrest",
            "Thunderstorm",
            "21:00:00",
            "Tirdas, 12 Sun's Height, 3E 405, 21:00:00",
        )

        self.assertEqual(
            title,
            "Walking through Wayrest on a thunderstorming mid Summer night (9 pm)",
        )


class LiveTitleUpdateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = object.__new__(bot_module.DaggerfallBot)
        self.bot._latest_response_data = None
        self.bot._last_stream_title = None
        self.bot._last_stream_title_update_at = 0.0
        self.bot._twitch_title_retry_at = 0.0
        self.bot._dev_mode = False
        self.bot.state = {"bluesky_live_text": ""}
        self.bot.update_stream_title = AsyncMock(return_value=True)

    @staticmethod
    def local_data(time_str):
        return {
            "region": "Wayrest",
            "location": "Wayrest",
            "weather": "Rainy",
            "date": f"Tirdas, 12 Sun's Height, 3E 405, {time_str}",
        }

    async def test_title_updates_are_coalesced_to_one_per_minute(self):
        with patch.object(bot_module.time, "monotonic", side_effect=[100.0, 130.0, 161.0]):
            self.assertTrue(await self.bot._maybe_update_stream_title(self.local_data("18:00:00")))
            self.assertFalse(await self.bot._maybe_update_stream_title(self.local_data("18:30:00")))
            self.assertTrue(await self.bot._maybe_update_stream_title(self.local_data("19:00:00")))

        self.assertEqual(self.bot.update_stream_title.await_count, 2)

    async def test_identical_title_does_not_call_twitch_again(self):
        data = self.local_data("18:30:00")
        with patch.object(bot_module.time, "monotonic", side_effect=[100.0, 200.0]):
            self.assertTrue(await self.bot._maybe_update_stream_title(data))
            self.assertFalse(await self.bot._maybe_update_stream_title(data))

        self.bot.update_stream_title.assert_awaited_once()

    async def test_shutdown_presence_is_not_overwritten_by_local_state(self):
        self.bot._stream_presence_override = bot_module.Config.SHUTDOWN_STATUS

        with patch.object(bot_module.time, "monotonic", return_value=100.0):
            self.assertTrue(
                await self.bot._maybe_update_stream_title(self.local_data("23:55:00"))
            )

        self.assertEqual(
            self.bot.update_stream_title.await_args.args[0],
            bot_module.Config.SHUTDOWN_STATUS,
        )
        self.assertEqual(self.bot._last_stream_title, bot_module.Config.SHUTDOWN_STATUS)


if __name__ == "__main__":
    unittest.main()
