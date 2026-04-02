"""
Spotify Library → CSV Sync
===========================
Fetches all your liked songs, saved albums, and playlist tracks
and writes them to spotify_library.csv. No playlist writes.

Run this whenever you want to refresh your library snapshot.
Then run push_playlist.py to push changes to Spotify.

SETUP: See README.md
RUN:   python sync_csv.py
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
CSV_FILE      = "spotify_library.csv"
# ───────────────────────────────────────────────────────────────────────────────

SCOPE = "user-library-read playlist-read-private"


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


def track_to_dict(track, album_name=None):
    return {
        "id":     track["id"],
        "title":  track["name"],
        "artist": ", ".join(a["name"] for a in track["artists"]),
        "album":  album_name or (track["album"]["name"] if "album" in track else ""),
    }


def get_liked_songs(sp):
    print("📥 Fetching liked songs...")
    items = get_all_pages(sp, sp.current_user_saved_tracks, limit=50)
    tracks = {}
    for item in items:
        t = item.get("track")
        if t and t.get("id"):
            tracks[t["id"]] = track_to_dict(t)
    print(f"   ✅ {len(tracks)} liked songs")
    return tracks


def get_saved_album_tracks(sp):
    print("💿 Fetching saved albums...")
    albums = get_all_pages(sp, sp.current_user_saved_albums, limit=50)
    tracks = {}
    for item in albums:
        album = item["album"]
        album_tracks = get_all_pages(sp, sp.album_tracks, album["id"], limit=50)
        for t in album_tracks:
            if t.get("id"):
                tracks[t["id"]] = track_to_dict(t, album_name=album["name"])
    print(f"   ✅ {len(tracks)} tracks from {len(albums)} saved albums")
    return tracks


def get_playlist_tracks(sp):
    print("📋 Fetching your playlists...")
    user_id = sp.me()["id"]
    playlists = get_all_pages(sp, sp.current_user_playlists, limit=50)
    own_playlists = [p for p in playlists if p["owner"]["id"] == user_id]
    tracks = {}
    for playlist in own_playlists:
        items = get_all_pages(sp, sp.playlist_items, playlist["id"], limit=100,
                              fields="items(track(id,name,artists,album)),next")
        for item in items:
            t = item.get("track")
            if t and t.get("id"):
                tracks[t["id"]] = track_to_dict(t)
    print(f"   ✅ {len(tracks)} tracks from {len(own_playlists)} playlists")
    return tracks


def write_csv(liked, album_tracks, playlist_tracks):
    all_ids  = set(liked) | set(album_tracks) | set(playlist_tracks)
    all_meta = {**playlist_tracks, **album_tracks, **liked}

    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["track_id", "title", "artist", "album", "liked", "saved_album", "in_playlist"])
        writer.writeheader()
        for tid in sorted(all_ids, key=lambda x: all_meta[x]["title"].lower()):
            m = all_meta[tid]
            writer.writerow({
                "track_id":    tid,
                "title":       m["title"],
                "artist":      m["artist"],
                "album":       m["album"],
                "liked":       "Yes" if tid in liked else "No",
                "saved_album": "Yes" if tid in album_tracks else "No",
                "in_playlist": "Yes" if tid in playlist_tracks else "No",
            })
    print(f"   ✅ {CSV_FILE} written ({len(all_ids)} tracks)")


def main():
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        username=USERNAME,
    ))

    print(f"\n👤 Logged in as: {sp.me()['display_name']}\n")

    liked           = get_liked_songs(sp)
    album_tracks    = get_saved_album_tracks(sp)
    playlist_tracks = get_playlist_tracks(sp)

    all_ids = set(liked) | set(album_tracks) | set(playlist_tracks)
    print(f"\n🎵 Total unique tracks: {len(all_ids)}")

    print("\n📄 Writing CSV...")
    write_csv(liked, album_tracks, playlist_tracks)

    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Sync complete!
   Total tracks : {len(all_ids)}
   CSV          : {CSV_FILE}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run push_playlist.py to push to Spotify.
""")


if __name__ == "__main__":
    main()