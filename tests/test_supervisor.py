import unittest
from unittest.mock import Mock, patch

from daggerwalk import supervisor


class StartupTimingTests(unittest.TestCase):
    def test_dev_save_load_wait_is_half_of_production(self):
        self.assertEqual(supervisor.save_load_wait_seconds("twitch"), 45)
        self.assertEqual(supervisor.save_load_wait_seconds("dev"), 22.5)

    def test_controls_launch_before_game_readiness_gate(self):
        events = []
        ready_flag = Mock()
        ready_flag.unlink.side_effect = lambda **kwargs: events.append("clear readiness")
        process = Mock()

        def launch(*args, **kwargs):
            events.append("launch controls")
            return process

        def stage_game(*args, **kwargs):
            events.append("stage game")
            return True

        def wait(*args, **kwargs):
            events.append("wait for controls")
            raise KeyboardInterrupt

        process.wait.side_effect = wait

        with (
            patch.object(supervisor, "READY_FLAG", ready_flag),
            patch.object(supervisor.subprocess, "Popen", side_effect=launch),
            patch.object(supervisor, "ensure_dfu_ready", side_effect=stage_game),
        ):
            with self.assertRaises(KeyboardInterrupt):
                supervisor.run_control_supervised("twitch")

        self.assertEqual(
            events,
            ["clear readiness", "launch controls", "stage game", "wait for controls"],
        )


if __name__ == "__main__":
    unittest.main()
