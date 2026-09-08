import unittest

from daggerwalk import supervisor


class StartupTimingTests(unittest.TestCase):
    def test_dev_save_load_wait_is_half_of_production(self):
        self.assertEqual(supervisor.save_load_wait_seconds("twitch"), 45)
        self.assertEqual(supervisor.save_load_wait_seconds("dev"), 22.5)


if __name__ == "__main__":
    unittest.main()
