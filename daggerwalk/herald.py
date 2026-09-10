"""Shared formatting for progression milestone announcements."""


def format_herald(events, limit=3):
    notices = []
    for event in (events or [])[:limit]:
        if event.get("type") == "unlock":
            notices.append(f"{event['username']} became a Wayfarer and unlocked guilds")
        elif event.get("type") == "renown":
            notices.append(f"{event['username']} reached {event['title']}")
        elif event.get("type") == "guild_rank":
            notices.append(f"{event['username']} became {event['title']} of the {event['guild']}")
    if len(events or []) > limit:
        notices.append(f"and {len(events) - limit} more milestones")
    return f"📯 Herald: {'; '.join(notices)}." if notices else ""
