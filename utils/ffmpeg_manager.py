import os
import sys
import requests
import logging
import shutil
import subprocess
from pathlib import Path
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class FFmpegManager:
    FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-git-full.7z"
    SEVENZIP_URL = "https://www.7-zip.org/a/7zr.exe"  # 7-Zip standalone console version
    
    def __init__(self):
        # Get the executable's directory path
        if getattr(sys, 'frozen', False):
            # If running as exe (PyInstaller)
            self.base_path = os.path.dirname(sys.executable)
        else:
            # If running as script
            self.base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        self.data_path = os.path.join(self.base_path, 'data')
        self.ffmpeg_path = os.path.join(self.data_path, 'ffmpeg')
        self.ffmpeg_exe = os.path.join(self.ffmpeg_path, 'bin', 'ffmpeg.exe')
        self.sevenzip_path = os.path.join(self.data_path, '7zr.exe')
        self.install_marker = os.path.join(self.data_path, '.ffmpeg_installed')

    def is_installed(self):
        """Check if FFmpeg is installed and working"""
        return os.path.exists(self.ffmpeg_exe) and os.path.exists(self.install_marker)

    def mark_as_installed(self):
        """Mark FFmpeg as installed and save version info"""
        os.makedirs(os.path.dirname(self.install_marker), exist_ok=True)
        
        # Save installation marker
        with open(self.install_marker, 'w') as f:
            f.write('installed')
        
        # Save version info
        try:
            response = requests.get("https://www.gyan.dev/ffmpeg/builds/")
            soup = BeautifulSoup(response.text, 'html.parser')
            latest_date = soup.find('em', id='last-git-build-date').text.strip()
            
            with open(os.path.join(self.ffmpeg_path, '.version'), 'w') as f:
                f.write(latest_date)
        except:
            pass

    def download_file(self, url, path, desc):
        """Download a file with progress bar"""
        print(f"\nDownloading {desc}...")
        
        response = requests.get(url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024
        
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        with open(path, 'wb') as f:
            downloaded = 0
            for data in response.iter_content(block_size):
                downloaded += len(data)
                f.write(data)
                done = int(50 * downloaded / total_size)
                sys.stdout.write(f'\rDownloading: [{"█" * done}{"." * (50-done)}] {downloaded}/{total_size} bytes')
                sys.stdout.flush()
        
        print(f"\n{desc} download complete!")
        return path

    def setup_7zip(self):
        """Download and setup 7-Zip if needed"""
        if not os.path.exists(self.sevenzip_path):
            self.download_file(self.SEVENZIP_URL, self.sevenzip_path, "7-Zip")

    def extract_ffmpeg(self, archive_path):
        """Extract FFmpeg using 7-Zip"""
        print("\nExtracting FFmpeg...")
        print(f"Archive path: {archive_path}")
        print(f"Extraction path: {self.ffmpeg_path}")
        
        try:
            # Ensure extraction directory exists and is empty
            if os.path.exists(self.ffmpeg_path):
                shutil.rmtree(self.ffmpeg_path)
            os.makedirs(self.ffmpeg_path, exist_ok=True)
            
            # Verify 7zip exists
            if not os.path.exists(self.sevenzip_path):
                raise Exception("7-Zip executable not found")
            
            # Use 7-Zip to extract
            result = subprocess.run([
                self.sevenzip_path,
                'x',               # extract with full paths
                archive_path,      # source archive
                f'-o{self.ffmpeg_path}',  # output directory
                '-y'              # yes to all queries
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"7-Zip extraction failed:\n{result.stderr}")
            
            # Find the extracted ffmpeg directory
            extracted_dirs = [d for d in os.listdir(self.ffmpeg_path) if d.startswith('ffmpeg-')]
            if not extracted_dirs:
                raise Exception("FFmpeg directory not found in archive")
            
            extracted_dir = os.path.join(self.ffmpeg_path, extracted_dirs[0])
            
            # Move contents up one level
            for item in os.listdir(extracted_dir):
                src = os.path.join(extracted_dir, item)
                dst = os.path.join(self.ffmpeg_path, item)
                if os.path.exists(dst):
                    if os.path.isdir(dst):
                        shutil.rmtree(dst)
                    else:
                        os.remove(dst)
                shutil.move(src, dst)
            
            # Cleanup
            os.rmdir(extracted_dir)
            os.remove(archive_path)
            
            return True
            
        except Exception as e:
            logger.error(f"Error extracting FFmpeg: {e}")
            raise

    def setup_ffmpeg(self, force_confirm=False):
        """Setup FFmpeg by downloading and extracting it"""
        try:
            if self.is_installed():
                # Check for updates if already installed
                if self.check_for_updates():
                    print("\nUpdating FFmpeg to latest version...")
                else:
                    print("FFmpeg is already installed and up to date!")
                    return True
            else:
                print("\nFFmpeg is required to run the bot.")
                print("This will download and install:")
                print("1. FFmpeg (~120MB)")
                print("2. 7-Zip standalone extractor (~1MB)")
                print("\nTotal download size: ~121MB")
                
                response = input("\nDo you want to continue? (y/n): ").lower().strip()
                if response != 'y':
                    print("\nFFmpeg installation cancelled. The bot cannot run without FFmpeg.")
                    sys.exit(0)
            
            print("\nSetting up FFmpeg...")
            
            # Create necessary directories first
            os.makedirs(self.data_path, exist_ok=True)
            os.makedirs(self.ffmpeg_path, exist_ok=True)
            
            # Setup 7-Zip first
            self.setup_7zip()
            
            # Download FFmpeg
            archive_path = os.path.join(self.data_path, 'ffmpeg.7z')  # Changed path
            archive_path = self.download_file(
                self.FFMPEG_URL,
                archive_path,
                "FFmpeg"
            )
            
            # Verify the file exists before extraction
            if not os.path.exists(archive_path):
                raise Exception("FFmpeg download failed - archive not found")
            
            # Extract it
            self.extract_ffmpeg(archive_path)
            
            # Clean up unnecessary files
            self.cleanup_ffmpeg()
            
            # Mark as installed
            self.mark_as_installed()
            
            print("\nFFmpeg setup complete!")
            return True
            
        except Exception as e:
            logger.error(f"Error setting up FFmpeg: {e}")
            if os.path.exists(self.sevenzip_path):
                logger.error(f"7-Zip path: {self.sevenzip_path} (exists)")
            else:
                logger.error(f"7-Zip path: {self.sevenzip_path} (missing)")
            raise

    def check_for_updates(self):
        """Check for FFmpeg updates"""
        try:
            response = requests.get("https://www.gyan.dev/ffmpeg/builds/")
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Get latest build date from website
            latest_date_elem = soup.find('em', id='last-git-build-date')
            if not latest_date_elem:
                return False
                
            latest_date = latest_date_elem.text.strip()
            
            # Read current version date
            version_file = os.path.join(self.ffmpeg_path, '.version')
            if os.path.exists(version_file):
                with open(version_file, 'r') as f:
                    current_date = f.read().strip()
                
                if current_date != latest_date:
                    print(f"\nNew FFmpeg version available!")
                    print(f"Current: {current_date}")
                    print(f"Latest: {latest_date}")
                    return True
            else:
                # No version file, force update
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            return False

    def cleanup_ffmpeg(self):
        """Clean up unnecessary FFmpeg files, keeping only essential files"""
        try:
            # Keep only bin directory and .version file
            for item in os.listdir(self.ffmpeg_path):
                path = os.path.join(self.ffmpeg_path, item)
                if item != 'bin' and item != '.version':
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
            
            # In bin directory, keep only ffmpeg.exe
            bin_path = os.path.join(self.ffmpeg_path, 'bin')
            if os.path.exists(bin_path):
                for item in os.listdir(bin_path):
                    if item.lower() != 'ffmpeg.exe':
                        path = os.path.join(bin_path, item)
                        os.remove(path)
            
        except Exception as e:
            logger.error(f"Error cleaning up FFmpeg: {e}")

def setup_ffmpeg(force_confirm=False):
    manager = FFmpegManager()
    return manager.setup_ffmpeg(force_confirm=force_confirm) 