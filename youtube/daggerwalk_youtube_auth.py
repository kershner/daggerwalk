# youtube_auth.py
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import pickle, os

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

def main():
    if os.path.exists("token.pickle"):
        print("✅ Token already exists, no need to re-authenticate.")
        return
    flow = InstalledAppFlow.from_client_secrets_file("daggerwalk_youtube_client_secret.json", SCOPES)
    creds = flow.run_local_server(port=0)
    with open("token.pickle", "wb") as f:
        pickle.dump(creds, f)
    print("✅ YouTube token saved successfully.")

if __name__ == "__main__":
    main()
