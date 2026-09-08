from datetime import datetime, timedelta, timezone
import time
import unittest
from unittest.mock import Mock, patch

from daggerwalk import twitch_bot as bot_module


class Channel:
    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(message)


class Message:
    def __init__(self, channel):
        self.channel = channel
        self.author = type("Author", (), {"name": "Walker", "id": "123"})()


def make_bot():
    bot = object.__new__(bot_module.DaggerfallBot)
    bot._pending_progression_actions = {}
    bot._monument_type_samples = {}
    bot._read_rate_limits = {}
    bot._progression = {
        "profiles": {"walker": {
            "username": "Walker", "position": 12, "renown_title": "Pathfinder",
            "xp": 235, "quests": 8, "next_renown": {"xp": 400, "title": "Adventurer"},
            "guild": None, "tokens_available": 1, "tokens_used": 0,
            "tokens_earned": 1, "next_token_xp": 1250, "monuments_placed": 0,
        }},
        "guilds": {
            "fighters": {"name": "Fighters Guild", "emoji": "⚔️"},
            "mages": {"name": "Mages Guild", "emoji": "🔮"},
            "thieves": {"name": "Thieves Guild", "emoji": "🗝️"},
            "dark-brotherhood": {"name": "Dark Brotherhood", "emoji": "🗡️"},
        },
        "monument_types": {
            "cairn": {"label": "Cairn", "emoji": "🪨", "required_title": "Pathfinder", "required_xp": 200},
            "obelisk": {"label": "Obelisk", "emoji": "🗿", "required_title": "Hero of the Iliac Bay", "required_xp": 1000},
        },
        "monuments": [],
    }
    return bot


class ProgressionChatTests(unittest.IsolatedAsyncioTestCase):
    async def test_renown_reads_only_local_cache(self):
        bot, channel = make_bot(), Channel()
        with patch("daggerwalk.twitch_bot.requests.get") as get, patch("daggerwalk.twitch_bot.requests.post") as post:
            await bot.renown(Message(channel), [])
        self.assertIn("#12 • Pathfinder • 235 XP", channel.messages[0])
        get.assert_not_called()
        post.assert_not_called()

    def test_hail_is_a_renown_alias(self):
        self.assertEqual(bot_module.Config.COMMAND_ALIASES["hail"], "renown")

    async def test_guild_join_only_creates_local_confirmation(self):
        bot, channel = make_bot(), Channel()
        with patch("daggerwalk.twitch_bot.requests.post") as post:
            await bot.guild(Message(channel), ["join", "mages"])
        self.assertEqual(bot._pending_progression_actions["walker"]["guild"], "mages")
        self.assertGreater(bot._pending_progression_actions["walker"]["expires"], time.monotonic())
        post.assert_not_called()

    async def test_guild_join_without_choice_lists_available_guilds(self):
        bot, channel = make_bot(), Channel()

        await bot.guild(Message(channel), ["join"])

        self.assertIn("Choose a guild", channel.messages[0])
        self.assertIn("⚔️ fighters", channel.messages[0])
        self.assertIn("🗡️ dark-brotherhood", channel.messages[0])
        self.assertIn("Usage: !guild join <guild>", channel.messages[0])
        self.assertEqual(channel.messages[0].count("!guild join"), 1)
        self.assertNotIn("walker", bot._pending_progression_actions)

    async def test_guild_followup_is_not_silently_blocked_by_status_cooldown(self):
        bot, channel = make_bot(), Channel()

        await bot.guild(Message(channel), [])
        await bot.guild(Message(channel), ["join"])

        self.assertEqual(len(channel.messages), 2)
        self.assertIn("Choose a guild", channel.messages[1])

    async def test_unaffiliated_guild_status_points_to_join_without_relisting_guilds(self):
        bot, channel = make_bot(), Channel()

        await bot.guild(Message(channel), [])

        self.assertIn("Unaffiliated • Join: !guild join", channel.messages[0])
        self.assertNotIn("Fighters Guild", channel.messages[0])
        self.assertIn("https://kershner.org/daggerwalk/guilds/", channel.messages[0])

    async def test_monument_status_links_to_registry(self):
        bot, channel = make_bot(), Channel()

        await bot.monument(Message(channel), [])

        self.assertIn("!monument types → !monument <type>", channel.messages[0])
        self.assertIn("1 Monument Token", channel.messages[0])
        self.assertIn("https://kershner.org/daggerwalk/monuments/", channel.messages[0])

    async def test_monument_types_shows_three_random_choices_per_unlocked_tier(self):
        bot, channel = make_bot(), Channel()
        bot._progression["profiles"]["walker"]["xp"] = 1500
        bot._progression["monument_types"] = {
            **{
                f"path-{index}": {"label": f"Path {index}", "emoji": "🏛️", "required_title": "Pathfinder", "required_xp": 200}
                for index in range(5)
            },
            **{
                f"hero-{index}": {"label": f"Hero {index}", "emoji": "🏛️", "required_title": "Hero of the Iliac Bay", "required_xp": 1000}
                for index in range(4)
            },
        }

        with patch("daggerwalk.twitch_bot.random.sample", side_effect=lambda names, count: names[:count]):
            await bot.monument(Message(channel), ["types"])

        self.assertIn("Pathfinder: path-0 • path-1 • path-2", channel.messages[0])
        self.assertIn("Hero of the Iliac Bay: hero-0 • hero-1 • hero-2", channel.messages[0])
        self.assertIn("path-2 │ Hero of the Iliac Bay", channel.messages[0])
        self.assertNotIn("path-3", channel.messages[0])
        self.assertIn("!monument types more", channel.messages[0])
        self.assertIn("!monument <type>", channel.messages[0])

        await bot.monument(Message(channel), ["types", "more"])

        self.assertIn("Pathfinder: path-3 • path-4", channel.messages[1])
        self.assertIn("Hero of the Iliac Bay: hero-3", channel.messages[1])
        self.assertNotIn("path-0", channel.messages[1])

    async def test_long_monument_type_lists_are_split_for_twitch(self):
        bot, channel = make_bot(), Channel()
        bot._progression["monument_types"] = {
            f"monument-type-{index}": {
                "label": f"Monument Type {index}", "emoji": "🏛️",
                "required_title": "Pathfinder", "required_xp": 200,
            }
            for index in range(40)
        }

        with patch("daggerwalk.twitch_bot.random.sample", side_effect=lambda names, count: names[:count]):
            await bot.monument(Message(channel), ["types"])
        await bot.monument(Message(channel), ["types", "more"])

        self.assertGreater(len(channel.messages), 1)
        self.assertTrue(all(len(text) <= 500 for text in channel.messages))
        self.assertIn("monument-type-0", " ".join(channel.messages))
        self.assertIn("monument-type-39", " ".join(channel.messages))

    async def test_monument_types_only_accepts_more_as_a_second_level(self):
        bot, channel = make_bot(), Channel()

        await bot.monument(Message(channel), ["types", "hero"])

        self.assertIn("Usage: !monument types [more]", channel.messages[0])
        self.assertNotIn("obelisk", channel.messages[0])

    async def test_monument_place_subcommand_is_not_supported(self):
        bot, channel = make_bot(), Channel()

        await bot.monument(Message(channel), ["place", "cairn"])

        self.assertIn("!monument types", channel.messages[0])
        self.assertNotIn("walker", bot._pending_progression_actions)

    async def test_monument_status_subcommand_is_not_supported(self):
        bot, channel = make_bot(), Channel()

        await bot.monument(Message(channel), ["status"])

        self.assertIn("Unknown monument type", channel.messages[0])

    async def test_guild_join_reports_active_cooldown_before_creating_confirmation(self):
        bot, channel = make_bot(), Channel()
        bot._progression["profiles"]["walker"]["guild_cooldown_until"] = (
            datetime.now(timezone.utc) + timedelta(days=3, hours=2)
        ).isoformat()

        await bot.guild(Message(channel), ["join", "mages"])

        self.assertIn("on cooldown for another 3d 2h", channel.messages[0])
        self.assertIn("until", channel.messages[0])
        self.assertNotIn("walker", bot._pending_progression_actions)

    async def test_guild_join_preview_explains_confirmation_and_cooldown(self):
        bot, channel = make_bot(), Channel()

        await bot.guild(Message(channel), ["join", "mages"])

        self.assertIn("Join the Mages Guild?", channel.messages[0])
        self.assertIn("30-day cooldown", channel.messages[0])
        self.assertIn("!guild confirm • !guild cancel", channel.messages[0])

    async def test_guild_leave_preview_explains_retained_progress(self):
        bot, channel = make_bot(), Channel()
        bot._progression["profiles"]["walker"]["guild"] = {
            "key": "mages", "name": "Mages Guild", "emoji": "🔮", "title": "Apprentice", "xp": 40,
        }

        await bot.guild(Message(channel), ["leave"])

        self.assertIn("Leave the Mages Guild?", channel.messages[0])
        self.assertIn("rank stays saved", channel.messages[0])
        self.assertIn("no guild XP accrues", channel.messages[0])

    async def test_guild_leave_while_unaffiliated_explains_what_to_do(self):
        bot, channel = make_bot(), Channel()

        await bot.guild(Message(channel), ["leave"])

        self.assertIn("already unaffiliated", channel.messages[0])
        self.assertIn("!guild join", channel.messages[0])

    async def test_monument_preview_freezes_local_location_without_server_call(self):
        bot, channel = make_bot(), Channel()

        async def state():
            return {"worldX": "100000", "worldZ": "200000", "mapPixelX": "10", "mapPixelY": "20", "region": "Daggerfall", "locationType": "Wilderness", "date": "1 Frostfall"}

        bot.get_map_json_data = state
        with patch("daggerwalk.twitch_bot.requests.post") as post:
            await bot.monument(Message(channel), ["cairn"])
        pending = bot._pending_progression_actions["walker"]
        self.assertEqual(pending["state"]["worldX"], "100000")
        self.assertIn("capturedAt", pending["state"])
        post.assert_not_called()

    async def test_monument_type_can_be_placed_without_place_subcommand(self):
        bot, channel = make_bot(), Channel()

        async def state():
            return {"worldX": "100000", "worldZ": "200000", "mapPixelX": "10", "mapPixelY": "20", "region": "Daggerfall", "locationType": "Wilderness", "date": "1 Frostfall"}

        bot.get_map_json_data = state
        await bot.monument(Message(channel), ["cairn"])

        self.assertEqual(bot._pending_progression_actions["walker"]["monument_type"], "cairn")
        self.assertIn("!monument confirm", channel.messages[0])

    async def test_monument_confirmation_includes_description_and_direct_map_link(self):
        bot, channel = make_bot(), Channel()
        pending = {
            "kind": "monument", "monument_type": "cairn",
            "state": {"worldX": "100000", "worldZ": "200000"},
        }
        profile = bot._progression["profiles"]["walker"]
        response = Mock(status_code=201)
        response.json.return_value = {
            "status": "success", "profile": profile,
            "monument": {
                "id": 42, "name": "Walker's Cairn",
                "description": "This Cairn was raised by Walker, Pathfinder, in Daggerfall.",
                "region": "Daggerfall", "map_pixel_x": 10, "map_pixel_y": 20,
            },
        }

        with patch("daggerwalk.twitch_bot.requests.post", return_value=response), \
                patch.object(bot, "_save_progression_cache"):
            await bot._confirm_progression_action(Message(channel), pending)

        self.assertIn("This Cairn was raised by Walker", channel.messages[0])
        self.assertIn("https://kershner.org/daggerwalk/?monument=42", channel.messages[0])
