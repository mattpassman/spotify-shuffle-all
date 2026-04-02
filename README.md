# Spotify Mega Library

Spotify doesn't let you shuffle your entire library — only individual playlists. These scripts fix that by combining every song from your liked tracks, saved albums, and playlists into one big playlist you can shuffle freely.

## Scripts

| Script | What it does |
|--------|-------------|
| `megaplaylist.py` | All-in-one: fetches everything and pushes to Spotify in one run |
| `sync_csv.py` | Fetches your library and saves it to `spotify_library.csv` (no playlist writes) |
| `push_playlist.py` | Reads the CSV and pushes any new tracks to your mega playlist |

The two-script approach (`sync_csv.py` → `push_playlist.py`) is useful for incremental updates — it skips the heavy library fetch and just syncs changes.

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Create a Spotify app

1. Go to [https://developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) and log in
2. Click **Create app**
3. Fill in any name and description
4. Under **Redirect URIs**, add: `http://127.0.0.1:8888/callback`
5. Check **Web API** under APIs used
6. Save

### 3. Add yourself as an authorized user

New Spotify apps start in **Development Mode**, which means only explicitly allowlisted accounts can use them.

1. In your app's dashboard, go to **Settings → User Management**
2. Add the email address of your Spotify account
3. Save

(You can skip this step if you later request a quota extension to take the app out of Development Mode, but for personal use this is all you need.)

### 4. Copy your credentials

From your app's dashboard, grab the **Client ID** and **Client Secret**, then:

```bash
cp .env.example .env
```

Edit `.env`:
```
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
SPOTIFY_USERNAME=your_spotify_username
```

Your Spotify username can be found at [https://www.spotify.com/account/overview/](https://www.spotify.com/account/overview/) — it's the username field, not your display name.

### 5. Customize the playlist name (optional)

The playlist will be created as **🎵 Mega Library** by default. To change it, open the script you plan to run and edit the `PLAYLIST_NAME` variable near the top:

```python
PLAYLIST_NAME = "🎵 Mega Library"   # Change this to whatever you like
```

If you rename it after already running the script, a new playlist will be created rather than updating the old one.

### 6. Run

```bash
# All-in-one
python megaplaylist.py

# Or two-step (useful for incremental syncs)
python sync_csv.py
python push_playlist.py
```

On first run, a browser window will open asking you to authorize the app with your Spotify account. After approving, you'll be redirected to `localhost` — the page may show an error, but that's fine. Copy the full URL from your browser's address bar and paste it into the terminal when prompted.

A `.cache` file is saved locally so you stay logged in for future runs.

## Notes

- Duplicate tracks are automatically deduplicated across all sources
- Re-running is safe — only tracks not already in the playlist are added
- The playlist is created as private by default; you can make it public in Spotify afterward
- `spotify_library.csv` is a local snapshot of your library (title, artist, album, and which sources each track came from)
