import sys
import types
import unittest
from unittest.mock import Mock, patch


atproto_stub = types.ModuleType("atproto")
atproto_stub.Client = object
sys.modules.setdefault("atproto", atproto_stub)

import bluesky_live


class QuestCompletionPostTests(unittest.TestCase):
    def test_post_text_and_portrait_alt_match_requested_format(self):
        text, alt = bluesky_live.build_quest_completion_post({
            "quest_name": "Travel to Wayrest",
            "quest_giver_name": "Lady Brisienna",
            "xp": 30,
        })

        self.assertEqual(
            text,
            "✅ Quest complete: Travel to Wayrest!\n\n"
            "Quest given by Lady Brisienna\n"
            "⚔️ 30 XP awarded\n\n"
            "https://kershner.org/daggerwalk",
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
            "quest_name": "Travel to Wayrest",
            "quest_giver_name": "Lady Brisienna",
            "quest_giver_img_url": "https://example.com/brisienna.png",
            "xp": 30,
        }

        with patch.object(bluesky_live.requests, "get", return_value=response):
            bluesky_live.post_quest_completion(client, quest, "id:42")

        put_data = repo.put_record.call_args.kwargs["data"]
        record = put_data["record"]
        self.assertEqual(put_data["collection"], "app.bsky.feed.post")
        self.assertTrue(put_data["rkey"].startswith("quest-completion-"))
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
            bluesky_live.JOURNEY_URI,
        )


if __name__ == "__main__":
    unittest.main()
