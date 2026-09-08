import sys
import types
import unittest
import re
from unittest.mock import Mock, patch


atproto_stub = types.ModuleType("atproto")
atproto_stub.Client = object
sys.modules.setdefault("atproto", atproto_stub)

from daggerwalk import bluesky


class QuestCompletionPostTests(unittest.TestCase):
    def test_new_tid_is_a_valid_feed_post_record_key(self):
        rkey = bluesky.new_tid()

        self.assertRegex(rkey, re.compile(r"^[234567abcdefghij][234567abcdefghijklmnopqrstuvwxyz]{12}$"))

    def test_post_text_and_portrait_alt_match_requested_format(self):
        text, alt = bluesky.build_quest_completion_post({
            "id": 42,
            "quest_name": "Travel to Wayrest",
            "quest_giver_name": "Lady Brisienna",
            "xp": 30,
            "participant_count": 3,
            "duration_minutes": 1500,
            "distance_km": 42.5,
        })

        self.assertEqual(
            text,
            "✅ Quest complete: Travel to Wayrest!\n\n"
            "Quest given by Lady Brisienna\n"
            "⚔️ 30 XP awarded to 3 walkers\n"
            "🕒 Quest length: 1 day 1 hour\n"
            "🥾 Distance traveled: 42.5 km\n\n"
            "https://kershner.org/daggerwalk/quests/42/",
        )
        self.assertEqual(
            alt,
            "Portrait of Lady Brisienna, who gave The Walker the completed "
            "quest “Travel to Wayrest.”",
        )

    def test_missing_optional_fields_produces_text_only_fallback(self):
        text, alt = bluesky.build_quest_completion_post({
            "poi_name": "Wayrest",
        })

        self.assertEqual(
            text,
            "✅ Quest complete: Wayrest!\n\n"
            "https://kershner.org/daggerwalk",
        )
        self.assertEqual(alt, "")

    def test_one_participant_uses_singular_walker(self):
        text, _ = bluesky.build_quest_completion_post({
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

        with patch.object(bluesky.requests, "get", return_value=response):
            bluesky.post_quest_completion(client, quest, "3jzfcijpj2z2a")

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


class MonumentPostTests(unittest.TestCase):
    def test_post_text_is_compact_and_uses_existing_description(self):
        text = bluesky.build_monument_post({
            "id": 42,
            "description": (
                "On a rainy afternoon in mid-autumn, this Cairn was raised in "
                "Daggerfall by Walker, Pathfinder. 1 Frostfall, 3E 405."
            ),
        }, "Walker", "🪨")

        self.assertEqual(
            text,
            "🪨 Monument raised by Walker!\n\n"
            "On a rainy afternoon in mid-autumn, this Cairn was raised in "
            "Daggerfall by Walker, Pathfinder. 1 Frostfall, 3E 405.\n\n"
            "📜 Eligible for future quests.\n\n"
            "🗺️ View on Map",
        )
        self.assertLessEqual(len(text), bluesky.POST_TEXT_LIMIT)

    def test_post_links_username_and_view_on_map(self):
        repo = Mock()
        client = types.SimpleNamespace(
            me=types.SimpleNamespace(did="did:example:daggerwalk"),
            com=types.SimpleNamespace(atproto=types.SimpleNamespace(repo=repo)),
        )
        monument = {"id": 42, "description": "A cairn in Daggerfall."}

        bluesky.post_monument(client, monument, "Walker", "🪨", "3jzfcijpj2z2a")

        put_data = repo.put_record.call_args.kwargs["data"]
        record = put_data["record"]
        self.assertEqual(put_data["rkey"], "3jzfcijpj2z2a")
        linked_text = []
        for facet in record["facets"]:
            start = facet["index"]["byteStart"]
            end = facet["index"]["byteEnd"]
            linked_text.append(record["text"].encode("utf-8")[start:end].decode("utf-8"))
        self.assertEqual(linked_text, ["Walker", "View on Map"])
        self.assertEqual(
            record["facets"][0]["features"][0]["uri"],
            "https://www.twitch.tv/Walker",
        )
        self.assertEqual(
            record["facets"][1]["features"][0]["uri"],
            "https://kershner.org/daggerwalk/?monument=42",
        )


if __name__ == "__main__":
    unittest.main()
