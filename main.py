import discord
from discord.ext import commands
import asyncio
import logging
import os
import sys
from datetime import datetime
from utils.ffmpeg_manager import setup_ffmpeg

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Only keep console logging
    ]
)
logger = logging.getLogger(__name__)

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