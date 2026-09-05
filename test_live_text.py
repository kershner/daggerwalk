import sys
import types
import unittest


bluesky_stub = types.ModuleType("bluesky_live")
bluesky_stub.login = lambda *args: None
bluesky_stub.clear_live = lambda *args: None
bluesky_stub.ensure_live = lambda *args: None
sys.modules.setdefault("bluesky_live", bluesky_stub)

import daggerwalk_twitch_bot as bot_module


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


if __name__ == "__main__":
    unittest.main()
