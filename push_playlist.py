"""
Spotify CSV → Mega Playlist Push
==================================
Reads spotify_library.csv and pushes all track IDs to your
mega playlist on Spotify. Only adds tracks not already there.

Run sync_csv.py first to refresh the CSV, then run this.
Or just run this on its own if the CSV is already up to date —
it makes very few API requests (just playlist read + write).

SETUP: See README.md
RUN:   python push_playlist.py
"""

import csv
import os
import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth
import time
from collections import deque

load_dotenv()

# ─── YOUR CREDENTIALS ──────────────────────────────────────────────────────────
CLIENT_ID     = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI  = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
USERNAME      = os.getenv("SPOTIFY_USERNAME")
PLAYLIST_NAME = "🎵 Mega Library"
CSV_FILE      = "spotify_library.csv"
# ───────────────────────────────────────────────────────────────────────────────

SCOPE = "playlist-read-private playlist-modify-private playlist-modify-public"


# ─── RATE LIMITER ──────────────────────────────────────────────────────────────
class RateLimiter:
    """Keeps requests under 90 per 30-second rolling window."""
    def __init__(self, max_requests=90, window_seconds=30):
        self.max_requests = max_requests
        self.window = window_seconds
        self.timestamps = deque()

    def wait(self):
        now = time.time()
        while self.timestamps and self.timestamps[0] < now - self.window:
            self.timestamps.popleft()
        if len(self.timestamps) >= self.max_requests:
            sleep_for = self.window - (now - self.timestamps[0]) + 0.1
            if sleep_for > 0:
                print(f"\n   ⏳ Rate limit approached — waiting {sleep_for:.1f}s...")
                time.sleep(sleep_for)
        self.timestamps.append(time.time())

limiter = RateLimiter()
# ───────────────────────────────────────────────────────────────────────────────


def get_all_pages(sp, sp_func, *args, **kwargs):
    limiter.wait()
    results = sp_func(*args, **kwargs)
    items = results["items"]
    while results["next"]:
        limiter.wait()
        results = sp.next(results)
        items.extend(results["items"])
    return items


def read_csv(filename):
    print(f"📄 Reading {filename}...")
    track_ids = []
    with open(filename, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("track_id"):
                track_ids.append(row["track_id"])
    print(f"   ✅ {len(track_ids)} tracks in CSV")
    return track_ids


def find_or_create_playlist(sp, name):
    user_id = sp.me()["id"]
    playlists = get_all_pages(sp, sp.current_user_playlists, limit=50)
    for p in playlists:
        if p["name"] == name and p["owner"]["id"] == user_id:
            print(f"🔍 Found existing playlist: '{name}'")
            return p["id"], True
    limiter.wait()
    playlist = sp.user_playlist_create(user_id, name, public=False,
                                       description="Every song in my library, no duplicates. Auto-generated.")
    print(f"🆕 Created new playlist: '{name}'")
    return playlist["id"], False


def get_existing_playlist_tracks(sp, playlist_id):
    items = get_all_pages(sp, sp.playlist_items, playlist_id, limit=100,
                          fields="items(track(id)),next")
    return {item["track"]["id"] for item in items if item.get("track") and item["track"].get("id")}


def add_tracks_to_playlist(sp, playlist_id, track_ids):
    total = len(track_ids)
    if total == 0:
        print("   ℹ️  No new tracks to add.")
        return
    print(f"➕ Adding {total} new tracks...")
    track_list = list(track_ids)
    for i in range(0, total, 100):
        limiter.wait()
        batch = ["spotify:track:" + tid for tid in track_list[i:i+100]]
        sp.playlist_add_items(playlist_id, batch)
        print(f"   Added {min(i+100, total)}/{total}...", end="\r")
    print(f"\n   ✅ Done!")


def main():
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        username=USERNAME,
    ))

    print(f"\n👤 Logged in as: {sp.me()['display_name']}\n")

    # Read track IDs from CSV — no heavy Spotify fetching needed
    all_track_ids = read_csv(CSV_FILE)

    # Find or create the mega playlist
    playlist_id, already_exists = find_or_create_playlist(sp, PLAYLIST_NAME)

    if already_exists:
        print("🔎 Checking what's already in the playlist...")
        existing = get_existing_playlist_tracks(sp, playlist_id)
        new_tracks = set(all_track_ids) - existing
        print(f"   {len(existing)} already there, {len(new_tracks)} to add")
    else:
        new_tracks = set(all_track_ids)

    add_tracks_to_playlist(sp, playlist_id, new_tracks)

    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ All done!
   Playlist : {PLAYLIST_NAME}
   Total    : {len(all_track_ids)} tracks
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")


if __name__ == "__main__":
    main()