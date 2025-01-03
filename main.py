import discord
from discord.ext import commands
import asyncio
import logging
import os
import sys
from datetime import datetime
from utils.ffmpeg_manager import setup_ffmpeg
import requests
import subprocess
from packaging import version

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Only keep console logging
    ]
)
logger = logging.getLogger(__name__)

# Add these at the top with other imports
GITHUB_REPO = "xnull-eu/xnull-music-bot"
CURRENT_VERSION = "v1.0.4"  # Update this with each release

class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        
        # Initialize bot state
        self.music_queues = {}  # Guild ID -> List of tracks
        self.now_playing = {}   # Guild ID -> Current track
        self.repeat_modes = {}  # Guild ID -> Repeat mode (off/all/single)
        self.loop_modes = {}    # Guild ID -> Loop mode (True/False)
        self.volume_levels = {} # Guild ID -> Volume level (0-100)

    async def setup_hook(self):
        await self.load_extension('cogs.music')
        logger.info("Music cog loaded successfully")

    async def on_ready(self):
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        
        # Generate and display invite link
        permissions = discord.Permissions()
        permissions.connect = True  # Connect to voice channels
        permissions.speak = True    # Speak in voice channels
        permissions.send_messages = True  # Send messages
        permissions.embed_links = True    # Send embeds
        permissions.read_message_history = True  # Read message history
        permissions.use_voice_activation = True  # Voice activity

        invite_link = discord.utils.oauth_url(
            self.user.id,
            permissions=permissions,
            scopes=["bot", "applications.commands"]
        )
        
        print("\n=== Bot is ready! ===")
        print(f"\nInvite the bot to your server using this link:")
        print(f"\n{invite_link}\n")
        print("=" * 20)
        
        await self.change_presence(activity=discord.Game(name="/help | xnull.eu"))
        
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} command(s)")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

def check_for_updates():
    """Check GitHub for new bot version"""
    if not getattr(sys, 'frozen', False):
        return False, None  # Skip update check if not running as exe
        
    try:
        # Get latest release info
        response = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest")
        if response.status_code != 200:
            return False, None
            
        latest = response.json()
        latest_version = latest['tag_name']
        
        # Compare versions
        if version.parse(latest_version) > version.parse(CURRENT_VERSION):
            download_url = f"https://github.com/{GITHUB_REPO}/releases/download/{latest_version}/XNull.Music.Bot.exe"
            return True, download_url
            
        return False, None
        
    except Exception as e:
        logger.error(f"Error checking for updates: {e}")
        return False, None

def download_update(download_url):
    """Download new version of the bot"""
    try:
        # Get current exe path
        if getattr(sys, 'frozen', False):
            current_exe = sys.executable
        else:
            return False
            
        # Download new version
        print("\nDownloading update...")
        response = requests.get(download_url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        
        # Save as temporary file
        new_exe = current_exe + ".new"
        with open(new_exe, 'wb') as f:
            downloaded = 0
            for data in response.iter_content(1024):
                downloaded += len(data)
                f.write(data)
                done = int(50 * downloaded / total_size)
                sys.stdout.write(f'\rDownloading: [{"█" * done}{"." * (50-done)}] {downloaded}/{total_size} bytes')
                sys.stdout.flush()
                
        print("\nUpdate downloaded successfully!")
        return new_exe
        
    except Exception as e:
        logger.error(f"Error downloading update: {e}")
        return None

def apply_update(new_exe):
    """Apply the update by replacing the old exe"""
    if not getattr(sys, 'frozen', False):
        return
        
    try:
        current_exe = sys.executable
        
        # Create batch script to:
        # 1. Wait for current process to exit
        # 2. Replace old exe with new one
        # 3. Start new version
        # 4. Delete itself
        batch_path = "update.bat"
        with open(batch_path, 'w') as f:
            f.write('@echo off\n')
            f.write(f'timeout /t 1 /nobreak >nul\n')  # Wait a bit
            f.write(f'del "{current_exe}"\n')  # Delete old version
            f.write(f'move "{new_exe}" "{current_exe}"\n')  # Move new version
            f.write(f'start "" "{current_exe}"\n')  # Start new version
            f.write(f'del "%~f0"\n')  # Delete this batch file
            
        # Run the update script and exit
        subprocess.Popen(batch_path, shell=True)
        sys.exit()
        
    except Exception as e:
        logger.error(f"Error applying update: {e}")
        if os.path.exists(new_exe):
            os.remove(new_exe)

def run_bot():
    # Create data directory if it doesn't exist
    os.makedirs('data', exist_ok=True)
    
    # Check for updates before starting
    has_update, download_url = check_for_updates()
    if has_update:
        print("\nNew version available! Downloading update...")
        new_exe = download_update(download_url)
        if new_exe:
            print("\nRestarting to apply update...")
            apply_update(new_exe)
            return
    
    # Initialize the bot
    bot = MusicBot()
    
    print("=== XNull Music Bot ===")
    print("\nVisit https://www.xnull.eu for more projects and tools!")
    
    # Setup FFmpeg before starting the bot
    try:
        print("\nChecking FFmpeg installation...")
        setup_ffmpeg(force_confirm=True)
    except Exception as e:
        print(f"\nError setting up FFmpeg: {e}")
        print("Please make sure you have a working internet connection and try again.")
        input("Press Enter to exit...")
        sys.exit(1)
    
    print("========================")
    
    # Get bot token
    if len(sys.argv) > 1:
        bot_token = sys.argv[1]
    else:
        print("\nTo get your bot token:")
        print("1. Go to https://discord.com/developers/applications")
        print("2. Click on your application (or create a new one)")
        print("3. Go to the 'Bot' section")
        print("4. Click 'Reset Token' or 'Copy' under the token section")
        print("\nMake sure to keep your token secret and never share it with anyone!")
        print("------------------------")
        bot_token = input("Please enter your bot token: ").strip()
    
    if not bot_token:
        print("Error: Bot token is required!")
        sys.exit(1)
    
    # Run the bot
    try:
        print("\nStarting bot...")
        bot.run(bot_token)
    except discord.LoginFailure:
        print("Error: Invalid bot token!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_bot() 
