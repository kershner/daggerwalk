import asyncio
import json
import math
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from daggerwalk import twitch_bot as bot_module


class AsyncFileStub:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def write(self, value):
        return len(value)


class RecordingChannel:
    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(message)


class Message:
    def __init__(self, content, channel):
        self.content = content
        self.channel = channel
        self.author = type("Author", (), {"name": "viewer"})()


class MovementControllerTests(unittest.TestCase):
    def make_controller(self):
        self.mouse_events = []
        self.key_events = []
        return bot_module.MovementController(
            mouse_move=lambda dx, dy: self.mouse_events.append((dx, dy)),
            key_state=lambda key, pressed: self.key_events.append((key, pressed)),
        )

    def test_opposite_view_commands_combine_and_move_smoothly(self):
        controller = self.make_controller()
        controller.add_view(yaw_steps=-3)
        controller.add_view(yaw_steps=1)

        controller.tick()
        controller.tick()

        self.assertEqual(self.mouse_events, [(-20, 0), (-20, 0)])

    def test_opposite_translation_commands_reduce_one_held_direction(self):
        controller = self.make_controller()
        controller.add_translation(10)
        controller.add_translation(-4)

        remaining_seconds = 6 * bot_module.Config.TRANSLATION_SECONDS_PER_STEP
        ticks = math.ceil(remaining_seconds / bot_module.Config.CONTROL_TICK_SECONDS) + 1
        for _ in range(ticks):
            controller.tick()

        self.assertEqual(self.key_events, [("w", True), ("w", False)])
        self.assertFalse(controller.translation_active)

    def test_stop_clears_pending_motion_releases_key_and_changes_generation(self):
        controller = self.make_controller()
        generation = controller.add_translation(10)
        controller.add_view(yaw_steps=10)
        controller.tick()

        controller.cancel_all()
        controller.tick()

        self.assertGreater(controller.generation, generation)
        self.assertEqual(self.key_events, [("w", True), ("w", False)])
        self.assertEqual(self.mouse_events, [(20, 0)])
        self.assertFalse(controller.translation_active)

    def test_ui_pause_releases_key_but_keeps_pending_movement(self):
        controller = self.make_controller()
        controller.add_translation(10)
        controller.tick()

        controller.pause()

        self.assertEqual(self.key_events, [("w", True), ("w", False)])
        self.assertTrue(controller.translation_active)
        controller.tick()
        self.assertEqual(self.key_events[-1], ("w", True))

    def test_movement_amount_has_default_and_clamps(self):
        self.assertEqual(
            bot_module.DaggerfallBot._movement_amount([]),
            bot_module.Config.DEFAULT_MOVEMENT_AMOUNT,
        )
        self.assertEqual(bot_module.DaggerfallBot._movement_amount(["0"]), 1)
        self.assertEqual(
            bot_module.DaggerfallBot._movement_amount(["999"]),
            bot_module.Config.MAX_INPUT_REPEATS,
        )


class VoteDispatchTests(unittest.IsolatedAsyncioTestCase):
    def make_bot(self):
        bot = object.__new__(bot_module.DaggerfallBot)
        bot.votable_commands = {"song": "change the song", "weather": "change weather"}
        bot.voting_active = True
        return bot

    async def test_busy_vote_rejects_another_votable_before_argument_validation(self):
        bot = self.make_bot()
        channel = RecordingChannel()
        bot.validate_song_arg = lambda args: self.fail("busy votes should be rejected first")

        with patch.object(bot_module.aiofiles, "open", return_value=AsyncFileStub()):
            await bot.event_message(Message("!song", channel))

        self.assertEqual(channel.messages, ["A vote is already in progress!"])

    async def test_busy_vote_does_not_block_an_ordinary_command(self):
        bot = self.make_bot()
        channel = RecordingChannel()
        dispatched = []
        bot._start_command_task = lambda name, factory: dispatched.append(name)

        with patch.object(bot_module.aiofiles, "open", return_value=AsyncFileStub()):
            await bot.event_message(Message("!help", channel))

        self.assertEqual(dispatched, ["help"])
        self.assertEqual(channel.messages, [])

    async def test_new_commands_dispatch_and_esc_is_removed(self):
        bot = self.make_bot()
        channel = RecordingChannel()
        dispatched = []
        bot._start_command_task = lambda name, factory: dispatched.append(name)

        with patch.object(bot_module.aiofiles, "open", return_value=AsyncFileStub()):
            for command in ("!w", "!cursor", "!click", "!doubleclick", "!torch", "!center", "!left_click", "!right_click", "!esc"):
                await bot.event_message(Message(command, channel))

        self.assertEqual(dispatched, ["walk", "cursor", "click", "doubleclick", "torch", "center"])

    async def test_movement_alias_preserves_parameters(self):
        bot = self.make_bot()
        bot._dev_mode = True
        bot.send_movement = AsyncMock()
        pending = []
        bot._start_command_task = lambda name, factory: pending.append((name, factory()))

        await bot.event_message(Message("!l 25", RecordingChannel()))
        name, command = pending.pop()
        await command

        self.assertEqual(name, "left")
        bot.send_movement.assert_awaited_once_with(bot_module.GameKeys.LEFT, ["25"])

    async def test_dev_qualifying_commands_enter_the_local_upload_log(self):
        bot = self.make_bot()
        bot._dev_mode = True
        bot._start_command_task = lambda name, factory: None
        channel = RecordingChannel()

        with patch.object(
            bot_module.aiofiles, "open", return_value=AsyncFileStub()
        ) as open_log:
            await bot.event_message(Message("!walk", channel))

        open_log.assert_called_once_with(bot_module.Config.CHAT_COMMANDS_FILE, mode="a")


class ConcurrentCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_starting_a_command_does_not_wait_for_it_to_finish(self):
        bot = object.__new__(bot_module.DaggerfallBot)
        bot._active_command_tasks = set()
        started = asyncio.Event()
        finish = asyncio.Event()

        async def slow_command():
            started.set()
            await finish.wait()

        bot._start_command_task("slow", slow_command)
        await asyncio.wait_for(started.wait(), timeout=0.1)
        self.assertEqual(len(bot._active_command_tasks), 1)

        finish.set()
        await asyncio.gather(*list(bot._active_command_tasks))
        await asyncio.sleep(0)
        self.assertEqual(bot._active_command_tasks, set())


class DevModeTests(unittest.IsolatedAsyncioTestCase):
    def test_local_configuration_routes_every_django_endpoint_to_loopback(self):
        config = bot_module.Config
        with (
            patch.dict(os.environ, {"DAGGERWALK_DEV_SERVER": "http://localhost:8123"}),
            patch.multiple(
                config,
                DJANGO_BASE_API_URL="production", DJANGO_LOG_URL="production",
                DJANGO_PROGRESSION_URL="production", DJANGO_GUILD_URL="production",
                DJANGO_MONUMENT_URL="production", CHAT_COMMANDS_FILE="production",
                DAGGERWALK_WEB_URL="production",
                QUEST_COMPLETION_STATE_FILE="production", PROGRESSION_CACHE_FILE="production",
            ),
        ):
            config.use_local_django_server()

            for url in (
                config.DJANGO_BASE_API_URL,
                config.DJANGO_LOG_URL,
                config.DJANGO_PROGRESSION_URL,
                config.DJANGO_GUILD_URL,
                config.DJANGO_MONUMENT_URL,
            ):
                self.assertTrue(url.startswith("http://localhost:8123/"), url)

    def test_local_configuration_rejects_non_loopback_servers(self):
        with patch.dict(
            os.environ, {"DAGGERWALK_DEV_SERVER": "https://kershner.org"}
        ):
            with self.assertRaisesRegex(ValueError, "loopback URL"):
                bot_module.Config.use_local_django_server()

    async def test_dev_runtime_starts_the_production_refresh_loop(self):
        bot = object.__new__(bot_module.DaggerfallBot)
        bot._dev_mode = True
        bot._startup_tasks_started = False
        bot._state_ready = asyncio.Event()
        bot.data_refresh_loop = AsyncMock()
        for name in (
            "autosave_loop",
            "message_scheduler",
            "crash_monitor",
            "side_effects_loop",
            "local_state_refresh_loop",
            "movement_control_loop",
        ):
            setattr(bot, name, AsyncMock())

        await bot._start_runtime()
        await asyncio.sleep(0)

        bot.data_refresh_loop.assert_awaited_once()

    async def test_dev_refresh_posts_game_data_through_the_normal_pipeline(self):
        bot = object.__new__(bot_module.DaggerfallBot)
        bot._dev_mode = True
        bot._refresh_lock = asyncio.Lock()
        bot._recent_world_positions = []
        bot.get_map_json_data = AsyncMock(return_value={"worldX": 1})
        bot._update_progression_cache = Mock()
        bot._check_and_announce_quest_completion = AsyncMock()
        response = Mock(status_code=201)
        response.json.return_value = {
            "progression": {"walkers": {}},
            "command_state": {},
            "log": {"world_x": 10, "world_z": 20},
        }

        with patch.object(bot_module, "post_to_django", return_value=response) as post:
            result = await bot.refresh_now()

        self.assertTrue(result)
        bot.get_map_json_data.assert_awaited_once()
        post.assert_called_once_with({"worldX": 1})


class MovementFeedbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_walk_and_stop_send_feedback(self):
        bot = object.__new__(bot_module.DaggerfallBot)
        bot._ui_lock = asyncio.Lock()
        bot._movement = Mock()
        bot.send_movement = AsyncMock()
        channel = RecordingChannel()

        await bot.start_walking(channel)
        with patch.object(bot_module.asyncio, "to_thread", AsyncMock()):
            await bot.stop_movement(channel)

        bot.send_movement.assert_awaited_once_with(bot_module.GameKeys.WALK)
        bot._movement.cancel_all.assert_called_once()
        self.assertEqual(
            channel.messages,
            ["Autowalk started.", "All movement stopped."],
        )

    async def test_cursor_click_and_doubleclick_send_expected_input(self):
        bot = object.__new__(bot_module.DaggerfallBot)
        bot._ui_lock = asyncio.Lock()
        bot._movement = Mock()

        with (
            patch.object(bot_module, "send_game_input") as send_key,
            patch.object(bot_module, "focus_game_window", return_value=True),
            patch.object(bot_module, "left_click") as click,
            patch.object(bot_module, "double_click") as doubleclick,
        ):
            await bot.toggle_cursor()
            await bot.send_click()
            await bot.send_double_click()

        send_key.assert_called_once_with(bot_module.GameKeys.CURSOR.value)
        click.assert_called_once_with()
        doubleclick.assert_called_once_with()

    async def test_center_sends_home_key(self):
        bot = object.__new__(bot_module.DaggerfallBot)

        with patch.object(bot_module.asyncio, "to_thread", AsyncMock()) as to_thread:
            await bot.send_movement(bot_module.GameKeys.CENTER)

        to_thread.assert_awaited_once_with(
            bot_module.send_game_input,
            bot_module.GameKeys.CENTER.value,
            1,
            0.15,
        )


class TorchCommandTests(unittest.IsolatedAsyncioTestCase):
    def make_bot(self, channel=None):
        bot = object.__new__(bot_module.DaggerfallBot)
        bot._dev_channel = channel or RecordingChannel()
        bot._ui_lock = asyncio.Lock()
        bot._movement = Mock()
        bot.state = {"torch": False}
        bot._save_torch_state = Mock()
        return bot

    async def test_torch_toggles_game_command_state_and_feedback(self):
        channel = RecordingChannel()
        bot = self.make_bot(channel)

        with patch.object(bot_module.asyncio, "to_thread", AsyncMock()) as to_thread:
            await bot.toggle_torch()
            await bot.toggle_torch()

        self.assertEqual(
            to_thread.call_args_list,
            [
                unittest.mock.call(bot_module.send_game_input, ";"),
                unittest.mock.call(bot_module.send_game_input, ";"),
            ],
        )
        self.assertFalse(bot.state["torch"])
        self.assertEqual(channel.messages, ["Torch: on", "Torch: off"])
        self.assertEqual(bot._save_torch_state.call_count, 2)

    async def test_state_output_always_includes_torch(self):
        channel = RecordingChannel()
        bot = self.make_bot(channel)
        bot.state["torch"] = True

        await bot.show_state()

        self.assertIn("Torch: on", channel.messages[0])

    async def test_torch_turns_off_automatically_during_morning(self):
        bot = self.make_bot()
        bot.state["torch"] = True
        data = {"date": "Tirdas, 12 Sun's Height, 3E 405, 06:00:00"}

        with patch.object(bot_module.asyncio, "to_thread", AsyncMock()) as to_thread:
            changed = await bot._maybe_turn_off_torch_at_morning(data)

        self.assertTrue(changed)
        self.assertFalse(bot.state["torch"])
        to_thread.assert_awaited_once_with(bot_module.send_game_input, ";")
        bot._save_torch_state.assert_called_once_with()

    async def test_torch_stays_on_before_morning(self):
        bot = self.make_bot()
        bot.state["torch"] = True
        data = {"date": "Tirdas, 12 Sun's Height, 3E 405, 05:59:59"}

        with patch.object(bot_module.asyncio, "to_thread", AsyncMock()) as to_thread:
            changed = await bot._maybe_turn_off_torch_at_morning(data)

        self.assertFalse(changed)
        self.assertTrue(bot.state["torch"])
        to_thread.assert_not_awaited()
        bot._save_torch_state.assert_not_called()

    def test_torch_state_round_trips_through_local_state_file(self):
        bot = object.__new__(bot_module.DaggerfallBot)
        bot.state = {"torch": True}

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = os.path.join(temp_dir, "daggerwalk_state.json")
            with patch.object(bot_module.Config, "LOCAL_STATE_FILE", state_path):
                bot._save_torch_state()
                loaded = bot._load_torch_state()

            with open(state_path, "r", encoding="utf-8") as state_file:
                on_disk = json.load(state_file)

        self.assertTrue(loaded)
        self.assertEqual(on_disk, {"torch": True})


class HelpCommandTests(unittest.IsolatedAsyncioTestCase):
    def make_bot(self, channel):
        bot = object.__new__(bot_module.DaggerfallBot)
        bot._dev_channel = channel
        return bot

    async def test_help_resolves_alias_and_lists_all_aliases(self):
        channel = RecordingChannel()
        await self.make_bot(channel).help(["l"])

        self.assertIn("!left:", channel.messages[0])
        self.assertIn(" • Usage: !left [amount]", channel.messages[0])
        self.assertIn(" • Aliases: !l", channel.messages[0])

        await self.make_bot(channel).help(["hail"])
        self.assertIn("!renown: Show walker progression", channel.messages[1])
        self.assertIn(" • Aliases: !hail", channel.messages[1])

    async def test_help_lists_commands_and_detail_syntax(self):
        channel = RecordingChannel()
        bot = self.make_bot(channel)

        await bot.help()
        await bot.more_commands()

        self.assertNotIn("Movement aliases:", channel.messages[0])
        self.assertIn("Details: !help <command>", channel.messages[0])
        self.assertIn("Details: !help <command>", channel.messages[1])
        self.assertTrue(all(len(message) <= 500 for message in channel.messages))

    def test_every_listed_command_has_details(self):
        listed = set(bot_module.Config.HELP_COMMANDS + bot_module.Config.MORE_COMMANDS)
        self.assertTrue(listed <= set(bot_module.Config.COMMAND_HELP))


if __name__ == "__main__":
    unittest.main()
