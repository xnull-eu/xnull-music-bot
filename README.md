# XNull Music Bot

A feature-rich Discord music bot that can play music from YouTube, handle playlists, and manage queues.

Visit [xnull.eu](https://www.xnull.eu) for more projects and tools!

## Features

- Play music from YouTube links or search queries
- Queue management with position control
- Playlist support
- Previous/Next song navigation
- Loop and repeat modes
- Auto-updating FFmpeg
- Queue shuffling
- Clean and intuitive commands
- Responsive error handling

## Commands

- `/help` - Shows all available commands
- `/play [song/URL] [position]` - Play music from YouTube or queue
- `/pause` - Pause the current song
- `/next` - Play the next song
- `/previous` - Play the previous song
- `/stop` - Stop the current song (clears queue if auto-clear is on)
- `/clearqueue` - Clear all songs from queue except current
- `/repeat off/all/single` - Set repeat mode for queue
- `/loop off/on/single` - Loop current song
- `/disconnect` - Disconnect bot from voice channel
- `/queue [song/URL] [position] [action]` - Manage queue
    - Show current queue
    - Add songs to queue
    - Clear queue (keeps current song playing)
    - Enable/disable auto-clear on stop
- `/shuffle` - Shuffle the current queue
- `/setstatus` - Set bot status (Admin only)

## Requirements

- Python 3.8 or higher
- discord.py >= 2.3.2
- yt-dlp >= 2024.12.23
- PyNaCl >= 1.5.0
- requests >= 2.31.0
- beautifulsoup4 >= 4.12.0

## Setup

1. Create a Discord Bot:
   - Go to [Discord Developer Portal](https://discord.com/developers/applications)
   - Create a new application
   - Go to the Bot section
   - Create a bot and copy the token

2. Clone the repository:
    ```
    git clone https://github.com/xnull-eu/xnull-music-bot.git
    cd xnull-music-bot
    ```

3. Install requirements:
    ```
    pip install -r requirements.txt
    ```

4. Run the bot:
    ```
    python main.py
    ```
    
5. Enter your bot token when prompted
6. Use the generated invite link to add the bot to your server

## Building Executable

To create a standalone executable:

1. Install requirements
2. Run the build script:
    ```
    python build.py
    ```

3. Find the executable in the `dist` folder

## Features in Detail

### Auto-updating FFmpeg
- Automatically downloads and installs FFmpeg (~150MB)
- Checks for updates on startup
- Keeps only necessary files
- Auto-updates when new version is available
- Version tracking to ensure latest build

### Queue Management
- Add songs anywhere in the queue
- Skip to any position
- Previous/Next navigation
- Clear queue while keeping current song
- Shuffle functionality
- Show current playing song with ▶️ indicator

### Playback Control
- Pause/Resume
- Next/Previous
- Stop with position memory
- Volume control
- Loop modes (single, all, off)
- Repeat modes (single, all, off)

### YouTube Support
- Direct links
- Search queries
- Playlist support
- Best audio quality selection
- Auto-skip unavailable tracks

## Support

For issues, suggestions, or contributions, please visit [xnull.eu](https://www.xnull.eu)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [discord.py](https://github.com/Rapptz/discord.py) - Discord API wrapper
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - YouTube downloader
- [GyanD/codexffmpeg](https://github.com/GyanD/codexffmpeg) - FFmpeg Windows builds
