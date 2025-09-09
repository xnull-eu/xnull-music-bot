import PyInstaller.__main__
import os
import shutil

def build_exe():
    print("Building XNull Music Bot executable...")

    # Clean previous builds
    if os.path.exists('build'):
        shutil.rmtree('build')
    if os.path.exists('dist'):
        shutil.rmtree('dist')

    # Use os.pathsep to set the proper separator based on the operating system
    data_sep = os.pathsep

    # PyInstaller options
    PyInstaller.__main__.run([
        'main.py',                          # Your main script
        '--name=XNull Music Bot',           # Name of the executable
        '--onefile',                        # Create a single executable
        f'--add-data=cogs{data_sep}cogs',   # Include cogs directory
        f'--add-data=utils{data_sep}utils', # Include utils directory
        '--icon=logo.ico',                  # Add icon if you have one
        '--clean',                          # Clean cache
        # Discord.py related imports
        '--hidden-import=discord',
        '--hidden-import=discord.ui',
        '--hidden-import=discord.app_commands',
        '--hidden-import=discord.voice_client',
        '--hidden-import=discord.opus',
        '--hidden-import=discord.ext.commands',
        # yt-dlp related imports
        '--hidden-import=yt_dlp',
        '--hidden-import=yt_dlp.utils',
        '--hidden-import=yt_dlp.extractor',
        '--hidden-import=yt_dlp.downloader',
        # PyNaCl related imports
        '--hidden-import=PyNaCl',
        '--hidden-import=nacl',
        # System related imports
        '--hidden-import=ctypes',
        '--hidden-import=ctypes.wintypes',
        # Web/parsing related imports
        '--hidden-import=requests',
        '--hidden-import=bs4',
        '--hidden-import=beautifulsoup4',
        '--hidden-import=soupsieve',        # Required by beautifulsoup4
        # Collect all packages
        '--collect-all=yt_dlp',
        '--collect-all=discord',
        '--collect-all=nacl',
        '--collect-all=bs4',
        '--collect-all=requests',
    ])

    print("\nBuild complete! Check the 'dist' folder for your executable.")
    print("\nVisit https://www.xnull.eu for more projects and tools!")

if __name__ == "__main__":
    build_exe()
