import asyncio
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

from daggerwalk import cinematic
from daggerwalk import twitch_bot as bot_module


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    def status(self, directory, **changes):
        value = dict(protocol=1, running=True, session="session", enabled=False,
                     active=False, timestamp=time.time(), last_request_id="")
        value.update(changes)
        (Path(directory) / "cinematic_camera_status.json").write_text(json.dumps(value), encoding="utf-8")
        return value

    async def test_rejects_missing_stale_invalid_and_stopped_status(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(cinematic.read_status(directory))
            for changes in [dict(timestamp=time.time() - 20), dict(running=False), dict(enabled="on"), dict(session="")]:
                self.status(directory, **changes)
                self.assertIsNone(cinematic.read_status(directory))
            (Path(directory) / "cinematic_camera_status.json").write_text("broken", encoding="utf-8")
            self.assertIsNone(cinematic.read_status(directory))

    async def test_already_requested_state_does_not_write_a_request(self):
        with tempfile.TemporaryDirectory() as directory:
            self.status(directory, enabled=True)
            result = await cinematic.set_cinematic_enabled(True, directory=directory)
            self.assertTrue(result["enabled"])
            self.assertFalse((Path(directory) / "cinematic_camera_request.json").exists())

    async def test_explicit_request_waits_for_matching_acknowledgement(self):
        for enabled in (True, False):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as directory:
                self.status(directory, enabled=not enabled)
                async def mod():
                    path = Path(directory) / "cinematic_camera_request.json"
                    while not path.exists():
                        await asyncio.sleep(0.01)
                    request = json.loads(path.read_text())
                    self.assertEqual(request["action"], "on" if enabled else "off")
                    self.assertEqual(request["session"], "session")
                    # A state change alone is not acknowledgement of our request.
                    self.status(directory, enabled=enabled, last_request_id="other-request")
                    await asyncio.sleep(0.12)
                    self.assertFalse(task.done())
                    self.status(directory, enabled=enabled, last_request_id=request["id"])
                task = asyncio.create_task(cinematic.set_cinematic_enabled(enabled, directory=directory))
                await asyncio.wait_for(mod(), timeout=1)
                result = await task
                self.assertEqual(result["enabled"], enabled)

    async def test_unavailable_and_timeout_do_not_claim_success(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                await cinematic.set_cinematic_enabled(True, directory=directory)
            self.status(directory)
            with self.assertRaisesRegex(RuntimeError, "did not confirm"):
                await cinematic.set_cinematic_enabled(True, directory=directory, timeout=0.05)

    async def test_restart_invalidates_pending_request(self):
        with tempfile.TemporaryDirectory() as directory:
            self.status(directory)
            async def restart():
                while not (Path(directory) / "cinematic_camera_request.json").exists():
                    await asyncio.sleep(0.01)
                self.status(directory, session="new-session")
            worker = asyncio.create_task(restart())
            with self.assertRaisesRegex(RuntimeError, "restarted"):
                await cinematic.set_cinematic_enabled(True, directory=directory)
            await worker


class ChatTests(unittest.IsolatedAsyncioTestCase):
    def make_bot(self):
        bot = object.__new__(bot_module.DaggerfallBot)
        bot._dev_channel = Mock()
        bot._send_feedback = AsyncMock()
        bot._is_qualifying_invocation = Mock(return_value=False)
        bot.votable_commands = {"cinematic": "change cinematic mode"}
        bot.voting_active = False
        bot.state = {}
        return bot

    def message(self, text):
        message = Mock(content=text)
        message.author.name = "viewer"
        return message

    async def test_no_arguments_reports_live_state_even_during_another_vote(self):
        bot = self.make_bot()
        bot.voting_active = True
        bot.start_vote = AsyncMock()
        for status, label in [(True, "On"), (False, "Off"), (None, "Unavailable")]:
            with patch.object(bot_module, "get_cinematic_status", return_value=status):
                await bot.event_message(self.message("!cinematic"))
            text = bot._send_feedback.await_args.args[1]
            self.assertIn(f"Cinematic mode: {label}", text)
            self.assertIn("!cinematic on", text)
            self.assertIn("!cinematic off", text)
        bot.start_vote.assert_not_awaited()

    async def test_invalid_arguments_do_not_vote(self):
        bot = self.make_bot()
        bot.start_vote = AsyncMock()
        for text in ("!cinematic toggle", "!cinematic on off", "!cinematic 1"):
            await bot.event_message(self.message(text))
        bot.start_vote.assert_not_awaited()

    async def test_explicit_request_enters_existing_vote_flow(self):
        bot = self.make_bot()
        bot.start_vote = AsyncMock()
        message = self.message("!cinematic ON")
        await bot.event_message(message)
        bot.start_vote.assert_awaited_once_with(message, "cinematic")

    async def test_passed_vote_applies_explicit_state(self):
        bot = self.make_bot()
        bot.current_vote_type = "cinematic"
        bot.current_vote_message = self.message("!cinematic OFF")
        bot.cinematic = AsyncMock()
        with patch.object(bot_module.Config, "CHAT_DELAY", 0):
            await bot.execute_voted_command()
        bot.cinematic.assert_awaited_once_with("off")

    async def test_vote_announces_requested_state_and_counts_initiator(self):
        bot = self.make_bot()
        bot.end_vote_timer = AsyncMock()
        await bot.start_vote(self.message("!cinematic ON"), "cinematic")
        await bot.voting_task
        self.assertTrue(bot.voting_active)
        self.assertEqual(bot.votes, {"viewer": "yes"})
        self.assertIn("turn cinematic mode on", bot._send_feedback.await_args.args[1])

    async def test_help_includes_voting_status_usage_and_scope(self):
        bot = self.make_bot()
        await bot.help(["cinematic"])
        text = bot._send_feedback.await_args.args[1]
        for phrase in ("!cinematic on/off", "!yes", "!no", "status", "on foot", "Mod Options"):
            self.assertIn(phrase, text)
        self.assertIn("cinematic", bot_module.Config.HELP_COMMANDS)

    async def test_state_reads_live_camera_state(self):
        bot = self.make_bot()
        for status, label in [(True, "on"), (False, "off"), (None, "unavailable")]:
            with patch.object(bot_module, "get_cinematic_status", return_value=status):
                await bot.show_state()
            self.assertIn(f"Cinematic: {label}", bot._send_feedback.await_args.args[1])

    async def test_request_failure_is_reported_without_success(self):
        bot = self.make_bot()
        with patch.object(bot_module, "set_cinematic_enabled", AsyncMock(side_effect=RuntimeError("unavailable"))):
            await bot.cinematic("on")
        bot._send_feedback.assert_awaited_once_with(bot._dev_channel, "unavailable")


if __name__ == "__main__":
    unittest.main()
