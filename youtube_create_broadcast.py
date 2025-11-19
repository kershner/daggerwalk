# youtube_create_broadcast.py
import pickle, os
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

CATEGORY_ID = "20"  # 20 = Gaming
GAME_TITLE = "The Elder Scrolls II: Daggerfall"
TAGS = [
    "daggerfall", "daggerfall unity", "elderscrolls", "bethesda", "elder scrolls", "rpg", "retro",
    "retrogaming", "adventure", "fantasy", "pcgaming", "pc gaming", "dos", "ms dos", "msdos",
    "oldschool", "automated", "interactive", "python", "javascript"
]

def get_service():
    with open("token.pickle", "rb") as f:
        creds = pickle.load(f)
    return build("youtube", "v3", credentials=creds)

def create_daily_broadcast(
    title="Everyday walkin'",
    description="An automated journey through the Iliac Bay. Type in the Twitch chat to control the game."
):
    yt = get_service()
    now = datetime.now(timezone.utc)
    start = now + timedelta(minutes=1)
    end = start + timedelta(hours=6)

    # Create the broadcast
    broadcast = yt.liveBroadcasts().insert(
        part="snippet,contentDetails,status",
        body={
            "snippet": {
                "title": f"{title} - {now.strftime('%Y/%m/%d')}",
                "description": description,
                "categoryId": CATEGORY_ID,
                "gameTitle": GAME_TITLE,
                "scheduledStartTime": start.isoformat(),
                "scheduledEndTime": end.isoformat(),
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False
            },
            "contentDetails": {"enableAutoStart": True, "enableAutoStop": True},
        },
    ).execute()

    # Bind it to your default stream key
    stream = yt.liveStreams().list(part="id", mine=True).execute()["items"][0]
    yt.liveBroadcasts().bind(
        part="id,contentDetails", id=broadcast["id"], streamId=stream["id"]
    ).execute()

    # Apply tags and confirm category on the video itself
    yt.videos().update(
        part="snippet",
        body={
            "id": broadcast["id"],
            "snippet": {
                "title": broadcast["snippet"]["title"],
                "description": broadcast["snippet"]["description"],
                "categoryId": CATEGORY_ID,
                "tags": TAGS,
            },
        },
    ).execute()

    print(f"✅ Created, bound, and tagged broadcast: {broadcast['snippet']['title']}")
    return broadcast["id"]

if __name__ == "__main__":
    create_daily_broadcast()
