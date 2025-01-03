import discord
from discord.ext import commands
import asyncio
import logging
import os
import sys
import requests
import shutil
from datetime import datetime
from utils.ffmpeg_manager import setup_ffmpeg
import ctypes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
GITHUB_API_URL = "https://api.github.com/repos/xnull-eu/xnull-music-bot/releases/latest"
CURRENT_VERSION = "v1.0.4"  # Update this with each release

def check_for_updates():
    """Check GitHub for new bot version"""
    if not getattr(sys, 'frozen', False):
        return False, None  # Skip update check if not running as exe
        
    try:
        response = requests.get(GITHUB_API_URL)
        if response.status_code != 200:
            return False, None
            
        latest = response.json()
        latest_version = latest['tag_name']
        
        if latest_version > CURRENT_VERSION:
            download_url = f"https://github.com/xnull-eu/xnull-music-bot/releases/download/{latest_version}/XNull.Music.Bot.exe"
            return True, (latest_version, download_url)
            
        return False, None
            
    except Exception as e:
        logger.error(f"Error checking for updates: {e}")
        return False, None

def is_admin():
    """Check if running with admin privileges"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """Restart the script with admin privileges for update only"""
    try:
        if sys.argv[-1] != '--auto-update':
            args = [sys.executable] + sys.argv + ['--auto-update']
        else:
            args = [sys.executable] + sys.argv
            
        ctypes.windll.shell32.ShellExecuteW(
            None, 
            "runas", 
            sys.executable,
            " ".join(['"{}"'.format(arg) for arg in args[1:]]),
            None, 
            1
        )
        sys.exit()
    except Exception as e:
        logger.error(f"Error running as admin: {e}")
        return False

def update_bot(new_version, download_url):
    """Download and prepare new version"""
    try:
        print(f"\nDownloading new version {new_version}...")
        
        # Download new version
        response = requests.get(download_url, stream=True)
        temp_exe = "XNull.Music.Bot.temp"
        
        with open(temp_exe, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        # Create update batch script
        current_exe = sys.executable
        batch_content = f'''@echo off
:wait
taskkill /F /IM "{os.path.basename(current_exe)}" >nul 2>&1
if exist "{current_exe}" (
    del /F "{current_exe}" >nul 2>&1
    if exist "{current_exe}" (
        timeout /t 1 /nobreak >nul
        goto wait
    )
)
move /Y "{temp_exe}" "{current_exe}" >nul 2>&1
del "%~f0"
exit
'''
        
        with open("update.bat", 'w') as f:
            f.write(batch_content)
        
        print("\nUpdate downloaded. Closing bot and installing update...")
        # Run update script and exit
        os.system('start /min cmd /c update.bat')
        sys.exit()
        
    except Exception as e:
        logger.error(f"Error updating bot: {e}")
        if os.path.exists(temp_exe):
            os.remove(temp_exe)
        if os.path.exists("update.bat"):
            os.remove("update.bat")
        return False

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

def run_bot():
    # Create data directory if it doesn't exist
    os.makedirs('data', exist_ok=True)
    
    # Initialize the bot
    bot = MusicBot()
    
    print("=== XNull Music Bot ===")
    print(f"\nCurrent Version: {CURRENT_VERSION}")
    print("\nVisit https://www.xnull.eu for more projects and tools!")
    
    # Check for updates if running as exe
    if getattr(sys, 'frozen', False):
        print("\nChecking for updates...")
        update_available, update_info = check_for_updates()
        
        if update_available:
            print(f"\nNew version available: {update_info[0]}")
            
            # If auto-update flag is set, proceed with update
            if '--auto-update' in sys.argv:
                print("\nStarting update process...")
                update_bot(update_info[0], update_info[1])
                return
            
            # Otherwise, ask for confirmation
            print("\nNote: The update process requires administrator privileges.")
            print("The bot will run normally after the update.")
            response = input("Do you want to update now? (y/n): ").lower().strip()
            
            if response == 'y':
                if not is_admin():
                    print("\nRestarting with administrator privileges for update...")
                    run_as_admin()
                    return
                else:
                    print("\nStarting update process...")
                    update_bot(update_info[0], update_info[1])
                    return
            else:
                print("\nUpdate skipped. Continuing with current version.")
    
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
