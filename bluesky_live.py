# bluesky_live.py
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
from atproto import Client
import requests

STATUS_COLL = "app.bsky.actor.status"
STATUS_RKEY = "self"
MAX_MINUTES = 240
REFRESH_EARLY = timedelta(minutes=5)

LIVE_URI = "https://www.twitch.tv/daggerwalk"
JOURNEY_URI = "https://kershner.org/daggerwalk"


def login(handle: str, app_password: str) -> Client | None:
    if not handle or not app_password:
        return None
    c = Client()
    c.login(handle, app_password)
    return c


def _now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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

    lines = [f"✅ Quest complete: {quest_name}!"]
    if quest_giver:
        lines.extend(["", f"Quest given by {quest_giver}"])
    if xp not in (None, ""):
        lines.append(f"⚔️ {xp} XP awarded")
    lines.extend(["", JOURNEY_URI])

    alt = (
        f"Portrait of {quest_giver}, who gave The Walker the completed "
        f"quest “{quest_name}.”"
        if quest_giver
        else ""
    )

    return "\n".join(lines), alt


def post_quest_completion(c: Client, quest: dict, completion_key: str) -> None:
    """Publish or replace one idempotent quest-completion post."""
    text, alt = build_quest_completion_post(quest)
    url_start = text.index(JOURNEY_URI)
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": _now_z(),
        "facets": [{
            "index": {
                "byteStart": len(text[:url_start].encode("utf-8")),
                "byteEnd": len(text[:url_start + len(JOURNEY_URI)].encode("utf-8")),
            },
            "features": [{
                "$type": "app.bsky.richtext.facet#link",
                "uri": JOURNEY_URI,
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

    # A deterministic record key makes retries safe even if the process exits before
    # its local outbox state is saved.
    digest = sha256(completion_key.encode("utf-8")).hexdigest()[:24]
    c.com.atproto.repo.put_record(data={
        "repo": c.me.did,
        "collection": "app.bsky.feed.post",
        "rkey": f"quest-completion-{digest}",
        "record": record,
    })
