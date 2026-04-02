"""
Spotify Mega Playlist Creator
==============================
Combines ALL songs from your library (saved albums + playlists) and Liked Songs
into one mega playlist, with no duplicates.

SETUP: See README.md
RUN:   python megaplaylist.py
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
PLAYLIST_NAME = "🎵 Mega Library"   # Change this to whatever you like
# ───────────────────────────────────────────────────────────────────────────────


# ─── RATE LIMITER ──────────────────────────────────────────────────────────────
class RateLimiter:
    """Keeps requests under 90 per 30-second rolling window."""
    def __init__(self, max_requests=90, window_seconds=30):
        self.max_requests = max_requests
        self.window = window_seconds
        self.timestamps = deque()

    def wait(self):
        now = time.time()
        # Drop timestamps older than the window
        while self.timestamps and self.timestamps[0] < now - self.window:
            self.timestamps.popleft()
        # If at the limit, sleep until the oldest request falls outside the window
        if len(self.timestamps) >= self.max_requests:
            sleep_for = self.window - (now - self.timestamps[0]) + 0.1
            if sleep_for > 0:
                print(f"\n   ⏳ Rate limit approached — waiting {sleep_for:.1f}s...")
                time.sleep(sleep_for)
        self.timestamps.append(time.time())

limiter = RateLimiter()
# ───────────────────────────────────────────────────────────────────────────────

SCOPE = (
    "user-library-read "
    "playlist-read-private "
    "playlist-modify-private "
    "playlist-modify-public"
)

def get_all_pages(sp, sp_func, *args, **kwargs):
    """Fetch all pages from a paginated Spotify endpoint."""
    limiter.wait()
    results = sp_func(*args, **kwargs)
    items = results["items"]
    while results["next"]:
        limiter.wait()
        results = sp.next(results)
        items.extend(results["items"])
    return items


def track_to_dict(track):
    """Extract metadata from a track object."""
    return {
        "id":     track["id"],
        "title":  track["name"],
        "artist": ", ".join(a["name"] for a in track["artists"]),
        "album":  track["album"]["name"] if "album" in track else "",
    }


def get_liked_songs(sp):
    print("📥 Fetching liked songs...")
    items = get_all_pages(sp, sp.current_user_saved_tracks, limit=50)
    tracks = {}
    for item in items:
        t = item.get("track")
        if t and t.get("id"):
            tracks[t["id"]] = track_to_dict(t)
    print(f"   ✅ {len(tracks)} liked songs found")
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
                tracks[t["id"]] = {
                    "id":     t["id"],
                    "title":  t["name"],
                    "artist": ", ".join(a["name"] for a in t["artists"]),
                    "album":  album["name"],
                }
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

    print(f"   ✅ {len(tracks)} tracks from {len(own_playlists)} of your playlists")
    return tracks


def find_or_create_playlist(sp, name):
    """Find existing mega playlist or create a new one."""
    user_id = sp.me()["id"]
    playlists = get_all_pages(sp, sp.current_user_playlists, limit=50)
    for p in playlists:
        if p["name"] == name and p["owner"]["id"] == user_id:
            print(f"🔍 Found existing playlist: '{name}' — will update it")
            return p["id"], True
    playlist = sp.user_playlist_create(user_id, name, public=False,
                                       description="Every song in my library, no duplicates. Auto-generated.")
    print(f"🆕 Created new playlist: '{name}'")
    return playlist["id"], False


def get_existing_playlist_tracks(sp, playlist_id):
    """Get tracks already in the mega playlist (for re-runs)."""
    items = get_all_pages(sp, sp.playlist_items, playlist_id, limit=100,
                          fields="items(track(id)),next")
    return {item["track"]["id"] for item in items if item.get("track") and item["track"].get("id")}


def add_tracks_to_playlist(sp, playlist_id, track_ids):
    """Add tracks in batches of 100 (Spotify API limit)."""
    track_list = list(track_ids)
    total = len(track_list)
    if total == 0:
        print("   ℹ️  No new tracks to add.")
        return

    print(f"➕ Adding {total} tracks to playlist...")
    for i in range(0, total, 100):
        limiter.wait()
        batch = ["spotify:track:" + tid for tid in track_list[i:i+100]]
        sp.playlist_add_items(playlist_id, batch)
        print(f"   Added {min(i+100, total)}/{total}...", end="\r")
    print(f"\n   ✅ Done!")


def write_csv(liked, album_tracks, playlist_tracks):
    """Write all tracks to a CSV with source flags."""
    all_ids = set(liked) | set(album_tracks) | set(playlist_tracks)
    all_meta = {**playlist_tracks, **album_tracks, **liked}  # liked wins for metadata

    filename = "spotify_library.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
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
    print(f"   ✅ CSV saved to {filename} ({len(all_ids)} rows)")


def main():
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        username=USERNAME,
    ))

    print(f"\n👤 Logged in as: {sp.me()['display_name']}\n")

    # Gather all tracks with metadata from every source
    liked           = get_liked_songs(sp)
    album_tracks    = get_saved_album_tracks(sp)
    playlist_tracks = get_playlist_tracks(sp)

    all_ids = set(liked) | set(album_tracks) | set(playlist_tracks)
    print(f"\n🎵 Total unique tracks across everything: {len(all_ids)}")

    # Write CSV
    print("\n📄 Writing CSV...")
    write_csv(liked, album_tracks, playlist_tracks)

    # Find or create the mega playlist
    playlist_id, already_exists = find_or_create_playlist(sp, PLAYLIST_NAME)

    if already_exists:
        existing = get_existing_playlist_tracks(sp, playlist_id)
        new_tracks = all_ids - existing
        print(f"   {len(existing)} already in playlist, {len(new_tracks)} new to add")
    else:
        new_tracks = all_ids

    add_tracks_to_playlist(sp, playlist_id, new_tracks)

    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ All done!
   Playlist : {PLAYLIST_NAME}
   Total tracks : {len(all_ids)}
   CSV : spotify_library.csv
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")


if __name__ == "__main__":
    main()
