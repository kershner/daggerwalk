# bluesky_live.py
from datetime import datetime, timedelta, timezone
from io import BytesIO
from atproto import Client
import requests
import secrets
import time

STATUS_COLL = "app.bsky.actor.status"
STATUS_RKEY = "self"
MAX_MINUTES = 240
REFRESH_EARLY = timedelta(minutes=5)

LIVE_URI = "https://www.twitch.tv/daggerwalk"
DAGGERWALK_URI = "https://kershner.org/daggerwalk"
TID_ALPHABET = "234567abcdefghijklmnopqrstuvwxyz"


def login(handle: str, app_password: str) -> Client | None:
    if not handle or not app_password:
        return None
    c = Client()
    c.login(handle, app_password)
    return c


def _now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_tid() -> str:
    """Return a valid AT Protocol timestamp identifier for a record key."""
    value = ((time.time_ns() // 1_000) << 10) | secrets.randbits(10)
    encoded = []
    for _ in range(13):
        encoded.append(TID_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(encoded))


def _clamp(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _record(title: str, desc: str) -> dict:
    # Keep it no-thumb. Title/desc are what you wanted dynamic.
    return {
        "$type": STATUS_COLL,
        "status": "app.bsky.actor.status#live",
        "createdAt": _now_z(),
        "durationMinutes": MAX_MINUTES,
        "embed": {
            "$type": "app.bsky.embed.external",
            "external": {
                "$type": "app.bsky.embed.external#external",
                "uri": LIVE_URI,
                "title": _clamp(title, 100),
                "description": _clamp(desc, 300),
            },
        },
    }


def set_live(c: Client, title: str, desc: str) -> None:
    c.com.atproto.repo.put_record(
        data={"repo": c.me.did, "collection": STATUS_COLL, "rkey": STATUS_RKEY, "record": _record(title, desc)}
    )


def clear_live(c: Client) -> None:
    c.com.atproto.repo.delete_record(
        data={"repo": c.me.did, "collection": STATUS_COLL, "rkey": STATUS_RKEY}
    )


def ensure_live(c: Client, title: str, desc: str) -> None:
    try:
        rec = c.com.atproto.repo.get_record(
            params={"repo": c.me.did, "collection": STATUS_COLL, "rkey": STATUS_RKEY}
        )
        val = rec.value.model_dump() if hasattr(rec.value, "model_dump") else rec.value

        created = datetime.fromisoformat(val["createdAt"].replace("Z", "+00:00"))
        mins = int(val.get("durationMinutes", 0))
        exp = created + timedelta(minutes=mins) if mins else None

        needs_refresh = (
            val.get("status") != "app.bsky.actor.status#live"
            or mins != MAX_MINUTES
            or not exp
            or exp - datetime.now(timezone.utc) <= REFRESH_EARLY
        )

        # Update if the text changed (so it stays in sync with Twitch title)
        cur = val.get("embed", {}).get("external", {}) if isinstance(val.get("embed"), dict) else {}
        text_changed = (cur.get("title") != title) or (cur.get("description") != desc)

        if needs_refresh or text_changed:
            set_live(c, title, desc)

    except Exception:
        set_live(c, title, desc)


def build_quest_completion_post(quest: dict) -> tuple[str, str]:
    """Build quest-completion post text and portrait alt text."""
    quest_name = quest.get("quest_name") or quest.get("poi_name") or "Quest"
    quest_giver = (quest.get("quest_giver_name") or "").strip()
    xp = quest.get("xp")
    participant_count = quest.get("participant_count")

    lines = [f"✅ Quest complete: {quest_name}!"]
    if quest_giver:
        lines.extend(["", f"Quest given by {quest_giver}"])
    if xp not in (None, ""):
        reward = f"⚔️ {xp} XP awarded"
        if participant_count is not None:
            walker_label = "walker" if participant_count == 1 else "walkers"
            reward += f" to {participant_count} {walker_label}"
        lines.append(reward)
    lines.extend(["", quest_completion_uri(quest)])

    alt = (
        f"Portrait of {quest_giver}, who gave The Walker the completed "
        f"quest “{quest_name}.”"
        if quest_giver
        else ""
    )

    return "\n".join(lines), alt


def quest_completion_uri(quest: dict) -> str:
    quest_id = quest.get("id")
    return f"{DAGGERWALK_URI}/quests/{quest_id}/" if quest_id else DAGGERWALK_URI


def post_quest_completion(c: Client, quest: dict, rkey: str) -> None:
    """Publish or replace one idempotent quest-completion post."""
    text, alt = build_quest_completion_post(quest)
    quest_uri = quest_completion_uri(quest)
    url_start = text.index(quest_uri)
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": _now_z(),
        "facets": [{
            "index": {
                "byteStart": len(text[:url_start].encode("utf-8")),
                "byteEnd": len(text[:url_start + len(quest_uri)].encode("utf-8")),
            },
            "features": [{
                "$type": "app.bsky.richtext.facet#link",
                "uri": quest_uri,
            }],
        }],
    }

    portrait_url = quest.get("quest_giver_img_url")
    if portrait_url and alt:
        response = requests.get(portrait_url, timeout=15)
        response.raise_for_status()
        blob = c.com.atproto.repo.upload_blob(BytesIO(response.content))
        record["embed"] = {
            "$type": "app.bsky.embed.images",
            "images": [{"image": blob.blob, "alt": _clamp(alt, 1000)}],
        }

    c.com.atproto.repo.put_record(data={
        "repo": c.me.did,
        "collection": "app.bsky.feed.post",
        "rkey": rkey,
        "record": record,
    })
