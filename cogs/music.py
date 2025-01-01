import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import logging
import re
from typing import Optional, Literal
import random
import os

# Configure logging
logger = logging.getLogger(__name__)
logging.getLogger('discord.player').setLevel(logging.WARNING)

# Simplified YDL options without browser cookies
YDL_OPTS = {
    'format': 'bestaudio/best',
    'noplaylist': False,
    'extract_flat': 'in_playlist',  # Better playlist handling
    'ignoreerrors': True,  # Skip unavailable videos
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'force-ipv4': True,
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
}

# Simplified FFmpeg options
FFMPEG_OPTIONS = {
    'options': '-vn -b:a 128k -loglevel error'
}

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ydl = yt_dlp.YoutubeDL(YDL_OPTS)
        self.active_players = {}
        self.current_position = {}  # Track current position in queue per guild
        self.stopped_position = {}  # Track where playback was stopped
        self.skip_next_progression = {}  # New flag to control auto-progression
        self.original_channels = {}  # Track original command channels per guild
        self.auto_clear = {}  # Track auto-clear setting per guild
        self.current_song = None  # Track current song after queue clear

    async def cleanup(self, guild_id):
        """Cleanup resources for a guild"""
        if guild_id in self.active_players:
            try:
                process = self.active_players[guild_id]
                process.kill()
            except:
                pass
            del self.active_players[guild_id]

    async def play_next(self, guild, force_position=None, interaction=None, command_channel=None):
        # Check if we have either a queue or a current_song
        if not guild.id in self.bot.music_queues and not self.current_song:
            return

        voice_client = guild.voice_client
        if not voice_client:
            return

        try:
            # Wait for any current playback to fully stop
            if voice_client.is_playing():
                voice_client.stop()
                await asyncio.sleep(0.5)

            # If we have a current_song from queue clear
            if self.current_song:
                track = self.current_song
                # Don't add to queue, just play it
            else:
                # Use forced position if provided, otherwise use current position
                position = force_position if force_position is not None else self.current_position.get(guild.id, 0)
                
                # Ensure position is valid
                if position >= len(self.bot.music_queues[guild.id]):
                    position = 0
                
                self.current_position[guild.id] = position
                track = self.bot.music_queues[guild.id][position]

            self.bot.now_playing[guild.id] = track

            try:
                # Get fresh track info
                info = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.ydl.extract_info(track['url'], download=False)
                )
                
                if not info:
                    logger.error(f"Failed to get track info: Info is None")
                    raise Exception("Track unavailable")

                # Get the best audio format URL
                formats = info.get('formats', [])
                if not formats:
                    logger.error(f"No formats available for track: {track['title']}")
                    raise Exception("No audio formats available")

                audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
                
                if not audio_formats:
                    audio_formats = formats
                    logger.warning(f"No audio-only formats found for {track['title']}, using mixed formats")
                
                best_format = sorted(
                    audio_formats,
                    key=lambda x: (x.get('abr', 0) or 0, x.get('asr', 0) or 0),
                    reverse=True
                )[0]
                
                url = best_format.get('url')
                if not url:
                    logger.error(f"No URL found in best format for track: {track['title']}")
                    raise Exception("No playable URL found")

            except Exception as e:
                logger.error(f"Error fetching track info: {str(e)}")
                logger.error(f"Track details: {track}")
                # Skip this track and try the next one
                logger.info(f"Skipping unavailable track: {track['title']}")
                next_pos = position + 1
                if next_pos < len(self.bot.music_queues[guild.id]):
                    self.current_position[guild.id] = next_pos
                    await self.play_next(guild, command_channel=command_channel)
                return

            # Create audio source
            try:
                audio_source = discord.FFmpegPCMAudio(
                    url,
                    before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                    options=FFMPEG_OPTIONS['options']
                )
            except Exception as e:
                logger.error(f"Error creating FFmpeg audio source: {str(e)}")
                logger.error(f"URL: {url}")
                raise

            transformed_source = discord.PCMVolumeTransformer(
                audio_source,
                volume=self.bot.volume_levels.get(guild.id, 1.0)
            )

            def after_callback(error):
                if error and str(error) != "Already playing audio.":
                    logger.error(f'Player error: {error}')
                else:
                    future = asyncio.run_coroutine_threadsafe(
                        self.song_finished(guild),
                        self.bot.loop
                    )
                    try:
                        future.result()
                    except Exception as e:
                        if "Already playing audio" not in str(e):
                            logger.error(f'Error in song_finished callback: {e}')

            # Ensure we're not already playing
            if not voice_client.is_playing():
                voice_client.play(
                    transformed_source,
                    after=after_callback
                )

                safe_title = track['title'].encode('ascii', 'ignore').decode('ascii')
                logger.info(f"Started playing: {safe_title}")
                
                # Only send message if not being called from a command
                if not interaction:
                    await self.send_playing_message(guild, track, command_channel=command_channel)

        except Exception as e:
            logger.error(f"Error playing track: {str(e)}", exc_info=True)
            # Try to recover by playing next song
            next_pos = self.current_position.get(guild.id, 0) + 1
            if next_pos < len(self.bot.music_queues[guild.id]):
                self.current_position[guild.id] = next_pos
                await self.play_next(guild, command_channel=command_channel)

    async def handle_playback_error(self, guild):
        """Handle playback errors by attempting to restart the track"""
        try:
            if guild.id in self.bot.music_queues and self.bot.music_queues[guild.id]:
                current_track = self.bot.music_queues[guild.id][0]
                logger.info(f"Attempting to restart track: {current_track['title']}")
                await self.play_next(guild)
        except Exception as e:
            logger.error(f"Error in handle_playback_error: {e}")
            if guild.id in self.bot.music_queues and self.bot.music_queues[guild.id]:
                self.bot.music_queues[guild.id].pop(0)
            await self.play_next(guild)

    async def send_playing_message(self, guild, track_info, interaction=None, command_channel=None):
        """Send a message indicating what's playing"""
        try:
            embed = discord.Embed(
                title="Now Playing",
                description=f"🎵 {track_info['title']}",
                color=discord.Color.blue()
            )
            
            # If interaction is provided, send as reply
            if interaction:
                await interaction.followup.send(embed=embed)
            # If command_channel is provided, use that
            elif command_channel:
                await command_channel.send(embed=embed)
            else:
                logger.debug("No channel provided to send playing message")
                    
        except Exception as e:
            logger.error(f"Error sending playing message: {e}")

    @app_commands.command(name="play", description="Play a song from YouTube or queue")
    async def play(self, interaction: discord.Interaction, query: Optional[str] = None, position: Optional[int] = None):
        # Store the original channel when starting playback
        if not interaction.guild.id in self.bot.music_queues:
            self.original_channels[interaction.guild.id] = interaction.channel
        
        await interaction.response.defer()

        if not interaction.user.voice:
            return await interaction.followup.send("You need to be in a voice channel!")

        # Connect to voice first if not connected
        if not interaction.guild.voice_client:
            try:
                await interaction.user.voice.channel.connect()
            except Exception as e:
                logger.error(f"Failed to connect to voice channel: {e}")
                return await interaction.followup.send("Failed to connect to voice channel!")

        # If position is provided, play from that position
        if position is not None:
            if not interaction.guild.id in self.bot.music_queues:
                return await interaction.followup.send("Queue is empty!")
            
            queue_length = len(self.bot.music_queues[interaction.guild.id])
            if position < 1 or position > queue_length:
                return await interaction.followup.send(f"Invalid position! Please choose between 1 and {queue_length}")
            
            # Calculate position index
            position_index = position - 1
            
            # Clear any queued position from /queue position command
            if hasattr(self.bot, 'next_position'):
                delattr(self.bot, 'next_position')
            
            # Ensure clean state before playing
            if interaction.guild.voice_client.is_playing():
                self.skip_next_progression[interaction.guild.id] = True  # Set flag before stopping
                self.current_song = None  # Clear any current_song
                interaction.guild.voice_client.stop()
                await asyncio.sleep(0.5)
            
            # Update position
            self.current_position[interaction.guild.id] = position_index
            
            # Play the selected song and send styled message as reply
            track = self.bot.music_queues[interaction.guild.id][position_index]
            await self.send_playing_message(interaction.guild, track, interaction)
            
            # Reset the skip flag before playing to allow auto-progression
            self.skip_next_progression[interaction.guild.id] = False
            await self.play_next(interaction.guild, interaction=interaction)
            return

        # If no query, resume from stopped position or continue playing
        if not query:
            if interaction.guild.voice_client.is_paused():
                interaction.guild.voice_client.resume()
                await interaction.followup.send("Resumed playback!")
                return
            elif not interaction.guild.voice_client.is_playing():
                if interaction.guild.id in self.bot.music_queues and self.bot.music_queues[interaction.guild.id]:
                    # Reset position to start of queue if previous song ended
                    if self.current_position.get(interaction.guild.id, 0) >= len(self.bot.music_queues[interaction.guild.id]):
                        self.current_position[interaction.guild.id] = 0
                    await self.play_next(interaction.guild)
                    await interaction.followup.send("Playing from queue!")
                else:
                    await interaction.followup.send("Queue is empty! Provide a song to play.")
            else:
                await interaction.followup.send("Already playing! Use /queue to see the current queue.")
            return

        # Check if the query is a URL
        is_url = re.match(r'https?://(?:www\.)?.+', query) is not None
        if not is_url:
            query = f"ytsearch:{query}"

        # Get track info
        info = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self.ydl.extract_info(query, download=False)
        )
        
        tracks_to_add = []
        
        if 'entries' in info:  # Playlist or search results
            if 'playlist' in query or 'list=' in query:  # It's a playlist
                await interaction.followup.send(f"Adding playlist: {info.get('title', 'Unknown playlist')}")
                for entry in info['entries']:
                    if entry:
                        tracks_to_add.append({
                            'url': entry.get('webpage_url', None) or f"https://www.youtube.com/watch?v={entry['id']}",
                            'title': entry.get('title', 'Unknown'),
                            'duration': entry.get('duration', 0)
                        })
            else:  # Search result
                entry = info['entries'][0]
                tracks_to_add.append({
                    'url': entry.get('webpage_url', None) or f"https://www.youtube.com/watch?v={entry['id']}",
                    'title': entry.get('title', 'Unknown'),
                    'duration': entry.get('duration', 0)
                })
        else:  # Single track
            tracks_to_add.append({
                'url': info.get('webpage_url', None) or f"https://www.youtube.com/watch?v={info['id']}",
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0)
            })
        
        # Add all tracks to queue
        for track in tracks_to_add:
            self.bot.music_queues.setdefault(interaction.guild.id, []).append(track)
        
        if len(tracks_to_add) > 1:
            await interaction.followup.send(f"Added {len(tracks_to_add)} tracks to queue")
        else:
            await interaction.followup.send(f"Added to queue: {tracks_to_add[0]['title']}")
        
        # Start playing if not already playing
        if not interaction.guild.voice_client.is_playing():
            await self.play_next(guild=interaction.guild, command_channel=interaction.channel)
            
    @app_commands.command(name="next", description="Play the next song")
    async def next(self, interaction: discord.Interaction):
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("I'm not playing anything!")
        
        if not interaction.guild.id in self.bot.music_queues:
            return await interaction.response.send_message("Queue is empty!")
        
        current_pos = self.current_position.get(interaction.guild.id, 0)
        next_pos = current_pos + 1
        
        # Check if we can go to next song
        if next_pos >= len(self.bot.music_queues[interaction.guild.id]):
            if self.bot.repeat_modes.get(interaction.guild.id) == 'all':
                next_pos = 0
            else:
                return await interaction.response.send_message("No more songs in queue!")
        
        # Update position
        self.current_position[interaction.guild.id] = next_pos
        
        # Stop current playback
        if interaction.guild.voice_client.is_playing():
            self.skip_next_progression[interaction.guild.id] = True  # Prevent auto-progression
            interaction.guild.voice_client.stop()
            await asyncio.sleep(0.5)
        
        # Play next song
        next_song = self.bot.music_queues[interaction.guild.id][next_pos]['title']
        await interaction.response.send_message(f"Playing next song: {next_song}")
        await self.play_next(interaction.guild, force_position=next_pos, command_channel=interaction.channel)

    @app_commands.command(name="previous", description="Play the previous song")
    async def previous(self, interaction: discord.Interaction):
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("I'm not playing anything!")
        
        if not interaction.guild.id in self.bot.music_queues:
            return await interaction.response.send_message("Queue is empty!")
        
        current_pos = self.current_position.get(interaction.guild.id, 0)
        if current_pos > 0:
            # Set position to previous song
            prev_pos = current_pos - 1
            
            # Stop current playback
            if interaction.guild.voice_client.is_playing():
                self.skip_next_progression[interaction.guild.id] = True  # Set flag before stopping
                interaction.guild.voice_client.stop()
                await asyncio.sleep(0.5)
            
            # Update position and ensure no auto-progression
            self.current_position[interaction.guild.id] = prev_pos
            self.skip_next_progression[interaction.guild.id] = True
            
            # Play the previous song
            prev_song = self.bot.music_queues[interaction.guild.id][prev_pos]['title']
            await interaction.response.send_message(f"Playing previous song: {prev_song}")
            await self.play_next(interaction.guild, force_position=prev_pos, command_channel=interaction.channel)
        else:
            # If at the start of queue, go to the end if repeat mode is on
            if self.bot.repeat_modes.get(interaction.guild.id) == 'all':
                prev_pos = len(self.bot.music_queues[interaction.guild.id]) - 1
                
                if interaction.guild.voice_client.is_playing():
                    self.skip_next_progression[interaction.guild.id] = True  # Set flag before stopping
                    interaction.guild.voice_client.stop()
                    await asyncio.sleep(0.5)
                
                # Update position and ensure no auto-progression
                self.current_position[interaction.guild.id] = prev_pos
                self.skip_next_progression[interaction.guild.id] = True
                
                prev_song = self.bot.music_queues[interaction.guild.id][prev_pos]['title']
                await interaction.response.send_message(f"Playing previous song: {prev_song}")
                await self.play_next(interaction.guild, force_position=prev_pos, command_channel=interaction.channel)
            else:
                await interaction.response.send_message("No previous songs in queue!")

    @app_commands.command(name="stop", description="Stop the current song")
    async def stop(self, interaction: discord.Interaction):
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("I'm not playing anything!")
        
        # Store current position
        self.stopped_position[interaction.guild.id] = self.current_position.get(interaction.guild.id, 0)
        
        # Set flag to prevent auto-progression
        self.skip_next_progression[interaction.guild.id] = True
        
        # Clear queue if auto-clear is enabled
        if self.auto_clear.get(interaction.guild.id, False):
            self.bot.music_queues[interaction.guild.id] = []
            await interaction.response.send_message("Stopped playing and cleared queue!")
        else:
            # Only show resume message if there are songs in queue
            if self.bot.music_queues.get(interaction.guild.id):
                await interaction.response.send_message("Stopped playing! Use `/play` to resume from where you left off.")
            else:
                await interaction.response.send_message("Stopped playing!")
        
        # Stop playback
        interaction.guild.voice_client.stop()

    @app_commands.command(name="repeat", description="Set repeat mode")
    async def repeat(self, interaction: discord.Interaction, mode: Literal['off', 'all', 'single']):
        self.bot.repeat_modes[interaction.guild.id] = mode
        queue_length = len(self.bot.music_queues.get(interaction.guild.id, []))
        
        messages = {
            'off': "Repeat mode disabled",
            'all': "Repeating entire queue until turned off",
            'single': f"Will repeat the queue one more time ({queue_length} songs)"
        }
        
        await interaction.response.send_message(messages[mode])

    @app_commands.command(name="loop", description="Loop current song")
    async def loop(self, interaction: discord.Interaction, mode: Literal['off', 'on', 'single']):
        self.bot.loop_modes[interaction.guild.id] = mode
        current_track = self.bot.now_playing.get(interaction.guild.id, {}).get('title', 'Nothing')
        
        messages = {
            'off': "Loop mode disabled",
            'on': f"Now looping: {current_track} until turned off",
            'single': f"Will play {current_track} one more time"
        }
            
        await interaction.response.send_message(messages[mode])

    @app_commands.command(name="disconnect", description="Disconnect the bot from voice channel")
    async def disconnect(self, interaction: discord.Interaction):
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("I'm not in a voice channel!")
        
        await interaction.guild.voice_client.disconnect()
        self.bot.music_queues[interaction.guild.id] = []
        await interaction.response.send_message("Disconnected from voice channel!")

    @app_commands.command(name="queue", description="Show, add to, or manage queue")
    @app_commands.describe(
        query="Song name or URL to add",
        position="Position in queue to play next",
        action="Queue management actions"
    )
    async def queue(self, interaction: discord.Interaction, 
                   query: Optional[str] = None, 
                   position: Optional[int] = None, 
                   action: Optional[Literal['clear', 'autoclear on', 'autoclear off']] = None):
        await interaction.response.defer()

        # Store the original channel when using queue command
        if not interaction.guild.id in self.original_channels:
            self.original_channels[interaction.guild.id] = interaction.channel

        # Handle actions
        if action:
            if action == 'clear':
                if not interaction.guild.id in self.bot.music_queues:
                    return await interaction.followup.send("Queue is already empty!")
                
                # Store current playing song if any
                if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
                    current_pos = self.current_position.get(interaction.guild.id, 0)
                    self.current_song = self.bot.music_queues[interaction.guild.id][current_pos]
                    await interaction.followup.send("Queue cleared! Current song will finish playing.")
                else:
                    self.current_song = None
                    await interaction.followup.send("Queue cleared!")
                
                # Clear the queue
                self.bot.music_queues[interaction.guild.id] = []
                return
            
            elif action == 'autoclear on':
                self.auto_clear[interaction.guild.id] = True
                await interaction.followup.send("Auto-clear on stop has been enabled.")
                return
            
            elif action == 'autoclear off':
                self.auto_clear[interaction.guild.id] = False
                await interaction.followup.send("Auto-clear on stop has been disabled.")
                return

        # Show queue if no query and no position
        if not query and position is None:
            if not interaction.guild.id in self.bot.music_queues or not self.bot.music_queues[interaction.guild.id]:
                return await interaction.followup.send("Queue is empty!")
            
            queue_list = ""
            current_pos = self.current_position.get(interaction.guild.id, 0)
            
            for i, track in enumerate(self.bot.music_queues[interaction.guild.id], 1):
                prefix = "▶️ " if i-1 == current_pos else f"{i}. "
                queue_list += f"{prefix}{track['title']}\n"
            
            if hasattr(self.bot, 'next_position') and self.bot.next_position.get('guild_id') == interaction.guild.id:
                next_pos = self.bot.next_position['position']
                next_song = self.bot.music_queues[interaction.guild.id][next_pos]['title']
                queue_list += f"\nNext up: {next_song}"
            
            embed = discord.Embed(
                title="Current Queue",
                description=queue_list,
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed)
            return

        # If position is provided, queue from that position
        if position is not None:
            if not interaction.guild.id in self.bot.music_queues:
                return await interaction.followup.send("Queue is empty!")
            
            queue_length = len(self.bot.music_queues[interaction.guild.id])
            if position < 1 or position > queue_length:
                return await interaction.followup.send(f"Invalid position! Please choose between 1 and {queue_length}")
            
            # Calculate position index
            position_index = position - 1
            
            # Clear any current_song when using position command
            self.current_song = None
            
            # Store the position to play next with channel info
            self.bot.next_position = {
                'guild_id': interaction.guild.id,
                'position': position_index,
                'suppress_message': True,
                'channel': interaction.channel
            }
            
            selected_song = self.bot.music_queues[interaction.guild.id][position_index]['title']
            await interaction.followup.send(f"Next up: {selected_song} (will play after current song ends)")
            return

        if not interaction.user.voice:
            return await interaction.followup.send("You need to be in a voice channel!")

        try:
            # Connect to voice if not already connected
            if not interaction.guild.voice_client:
                await interaction.user.voice.channel.connect()

            # Add to queue without playing
            is_url = re.match(r'https?://(?:www\.)?.+', query) is not None
            if not is_url:
                query = f"ytsearch:{query}"

            info = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.ydl.extract_info(query, download=False)
            )
            
            tracks_to_add = []
            
            if 'entries' in info:  # Playlist or search results
                if 'playlist' in query or 'list=' in query:  # It's a playlist
                    await interaction.followup.send(f"Adding playlist: {info.get('title', 'Unknown playlist')}")
                    for entry in info['entries']:
                        if entry:
                            tracks_to_add.append({
                                'url': entry.get('webpage_url', None) or f"https://www.youtube.com/watch?v={entry['id']}",
                                'title': entry.get('title', 'Unknown'),
                                'duration': entry.get('duration', 0)
                            })
                else:  # Search result
                    entry = info['entries'][0]
                    tracks_to_add.append({
                        'url': entry.get('webpage_url', None) or f"https://www.youtube.com/watch?v={entry['id']}",
                        'title': entry.get('title', 'Unknown'),
                        'duration': entry.get('duration', 0)
                    })
            else:  # Single track
                tracks_to_add.append({
                    'url': info.get('webpage_url', None) or f"https://www.youtube.com/watch?v={info['id']}",
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0)
                })
            
            # Add all tracks to queue
            for track in tracks_to_add:
                self.bot.music_queues.setdefault(interaction.guild.id, []).append(track)
            
            if len(tracks_to_add) > 1:
                await interaction.followup.send(f"Added {len(tracks_to_add)} tracks to queue")
            else:
                await interaction.followup.send(f"Added to queue: {tracks_to_add[0]['title']}")
            
        except Exception as e:
            logger.error(f"Error in queue command: {e}")
            await interaction.followup.send(f"An error occurred: {str(e)}")

    @app_commands.command(name="shuffle", description="Shuffle the current queue")
    async def shuffle(self, interaction: discord.Interaction):
        if not interaction.guild.id in self.bot.music_queues or not self.bot.music_queues[interaction.guild.id]:
            return await interaction.response.send_message("Queue is empty!")
        
        # Keep current playing song in its position
        current_pos = self.current_position.get(interaction.guild.id, 0)
        current = self.bot.music_queues[interaction.guild.id][current_pos]
        
        # Get all songs except current one
        remaining = self.bot.music_queues[interaction.guild.id][:current_pos] + self.bot.music_queues[interaction.guild.id][current_pos + 1:]
        random.shuffle(remaining)
        
        # Reconstruct queue with current song in its original position
        self.bot.music_queues[interaction.guild.id] = (
            remaining[:current_pos] + 
            [current] + 
            remaining[current_pos:]
        )
        
        await interaction.response.send_message("Queue shuffled!")

    @app_commands.command(name="setstatus", description="Set bot status (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def setstatus(self, interaction: discord.Interaction, status: str):
        await self.bot.change_presence(activity=discord.Game(name=status))
        await interaction.response.send_message(f"Status updated to: {status}")

    async def song_finished(self, guild):
        """Handle song finish with proper repeat/loop logic"""
        # If we were playing a current_song after queue clear
        if self.current_song:
            self.current_song = None  # Clear it
            # If we have a new queue, start playing it
            if guild.id in self.bot.music_queues and self.bot.music_queues[guild.id]:
                self.current_position[guild.id] = 0
                # Get the original channel for the message
                original_channel = self.original_channels.get(guild.id)
                # Send "Now Playing" message for the first song in new queue
                if original_channel:
                    first_song = self.bot.music_queues[guild.id][0]
                    await self.send_playing_message(guild, first_song, command_channel=original_channel)
                await self.play_next(guild)
            return

        if not guild.id in self.bot.music_queues:
            return

        # Check if we should skip progression
        if self.skip_next_progression.get(guild.id, False):
            self.skip_next_progression[guild.id] = False
            return

        # Check if there's a queued position to play next
        if hasattr(self.bot, 'next_position') and self.bot.next_position.get('guild_id') == guild.id:
            next_pos = self.bot.next_position['position']
            channel = self.bot.next_position.get('channel')  # Get stored channel
            self.current_position[guild.id] = next_pos
            delattr(self.bot, 'next_position')  # Clear the queued position
            await self.play_next(guild, command_channel=channel)  # Use stored channel
            return

        # Handle normal progression
        current_pos = self.current_position.get(guild.id, 0)
        next_pos = current_pos + 1

        # Check if we've reached the end of the queue
        if next_pos >= len(self.bot.music_queues[guild.id]):
            if self.bot.repeat_modes.get(guild.id) == 'all':
                next_pos = 0  # Start from beginning
            else:
                # If we have a current_song from queue clear, clear it
                if hasattr(self, 'current_song') and self.current_song:
                    self.current_song = None
                # Mark the song as finished
                self.current_position[guild.id] = len(self.bot.music_queues[guild.id])
                return  # End of queue reached

        # Update position and play next
        self.current_position[guild.id] = next_pos
        self.skip_next_progression[guild.id] = False
        
        # Use the original channel for messages
        original_channel = self.original_channels.get(guild.id)
        await self.play_next(guild, command_channel=original_channel)

    @app_commands.command(name="help", description="Shows all available commands")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="XNull Music Bot Commands",
            description="Here are all available commands:",
            color=discord.Color.blue()
        )
        
        commands = {
            "/help": "Shows this help message",
            "/play": "Plays music from YouTube or queue. Usage: /play [optional: song name/URL] [optional: position]",
            "/pause": "Pauses the current song",
            "/next": "Plays the next song",
            "/previous": "Plays the previous song",
            "/stop": "Stops the current song (clears queue if auto-clear is on)",
            "/repeat": "Repeats the queue. Usage: /repeat off/all/single",
            "/loop": "Loops current song. Usage: /loop off/on/single",
            "/disconnect": "Disconnects the bot from the channel",
            "/queue": "Manage queue. Usage: /queue [optional: song/URL] [optional: position] [action: clear/autoclear on/off]",
            "/shuffle": "Shuffles songs in the queue",
            "/setstatus": "Sets the bot status (Admin only)"
        }

        for cmd, desc in commands.items():
            embed.add_field(name=cmd, value=desc, inline=False)

        embed.set_footer(text="XNull Music Bot | xnull.eu")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="pause", description="Pause the current song")
    async def pause(self, interaction: discord.Interaction):
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("I'm not playing anything!")
        
        if interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.pause()
            await interaction.response.send_message("Paused the current song! Use `/play` to resume.")
        else:
            await interaction.response.send_message("Nothing is playing!")

async def setup(bot):
    await bot.add_cog(Music(bot)) 
