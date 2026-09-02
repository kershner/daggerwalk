import sys
import types
import unittest
import re
from unittest.mock import Mock, patch


atproto_stub = types.ModuleType("atproto")
atproto_stub.Client = object
sys.modules.setdefault("atproto", atproto_stub)

import bluesky_live


class QuestCompletionPostTests(unittest.TestCase):
    def test_new_tid_is_a_valid_feed_post_record_key(self):
        rkey = bluesky_live.new_tid()

        self.assertRegex(rkey, re.compile(r"^[234567abcdefghij][234567abcdefghijklmnopqrstuvwxyz]{12}$"))

    def test_post_text_and_portrait_alt_match_requested_format(self):
        text, alt = bluesky_live.build_quest_completion_post({
            "id": 42,
            "quest_name": "Travel to Wayrest",
            "quest_giver_name": "Lady Brisienna",
            "xp": 30,
            "participant_count": 3,
        })

        self.assertEqual(
            text,
            "✅ Quest complete: Travel to Wayrest!\n\n"
            "Quest given by Lady Brisienna\n"
            "⚔️ 30 XP awarded to 3 walkers\n\n"
            "https://kershner.org/daggerwalk/quests/42/",
        )
        self.assertEqual(
            alt,
            "Portrait of Lady Brisienna, who gave The Walker the completed "
            "quest “Travel to Wayrest.”",
        )

    def test_missing_optional_fields_produces_text_only_fallback(self):
        text, alt = bluesky_live.build_quest_completion_post({
            "poi_name": "Wayrest",
        })

        self.assertEqual(
            text,
            "✅ Quest complete: Wayrest!\n\n"
            "https://kershner.org/daggerwalk",
        )
        self.assertEqual(alt, "")

    def test_one_participant_uses_singular_walker(self):
        text, _ = bluesky_live.build_quest_completion_post({
            "quest_name": "Travel to Wayrest",
            "xp": 30,
            "participant_count": 1,
        })

        self.assertIn("⚔️ 30 XP awarded to 1 walker", text)

    def test_post_uploads_portrait_and_uses_idempotent_record_key(self):
        repo = Mock()
        repo.upload_blob.return_value = types.SimpleNamespace(blob="portrait-blob")
        client = types.SimpleNamespace(
            me=types.SimpleNamespace(did="did:example:daggerwalk"),
            com=types.SimpleNamespace(
                atproto=types.SimpleNamespace(repo=repo),
            ),
        )
        response = Mock(content=b"portrait bytes")
        response.raise_for_status.return_value = None
        quest = {
            "id": 42,
            "quest_name": "Travel to Wayrest",
            "quest_giver_name": "Lady Brisienna",
            "quest_giver_img_url": "https://example.com/brisienna.png",
            "xp": 30,
            "participant_count": 3,
        }

        with patch.object(bluesky_live.requests, "get", return_value=response):
            bluesky_live.post_quest_completion(client, quest, "3jzfcijpj2z2a")

        put_data = repo.put_record.call_args.kwargs["data"]
        record = put_data["record"]
        self.assertEqual(put_data["collection"], "app.bsky.feed.post")
        self.assertEqual(put_data["rkey"], "3jzfcijpj2z2a")
        self.assertEqual(record["embed"]["images"][0]["image"], "portrait-blob")
        self.assertEqual(
            record["embed"]["images"][0]["alt"],
            "Portrait of Lady Brisienna, who gave The Walker the completed "
            "quest “Travel to Wayrest.”",
        )

        facet = record["facets"][0]["index"]
        encoded_text = record["text"].encode("utf-8")
        self.assertEqual(
            encoded_text[facet["byteStart"]:facet["byteEnd"]].decode("utf-8"),
            "https://kershner.org/daggerwalk/quests/42/",
        )


if __name__ == "__main__":
    unittest.main()
