# bluesky_live.py
from datetime import datetime, timedelta, timezone
from atproto import Client

STATUS_COLL = "app.bsky.actor.status"
STATUS_RKEY = "self"
MAX_MINUTES = 240
REFRESH_EARLY = timedelta(minutes=5)

LIVE_URI = "https://www.twitch.tv/daggerwalk"


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
