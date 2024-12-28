import os
import sys
import requests
import logging
import shutil
from bs4 import BeautifulSoup
import zipfile

logger = logging.getLogger(__name__)

class FFmpegManager:
    FFMPEG_RELEASES_URL = "https://github.com/GyanD/codexffmpeg/releases/latest"
    
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
        self.install_marker = os.path.join(self.data_path, '.ffmpeg_installed')
        self.version_file = os.path.join(self.ffmpeg_path, '.version')

    def is_installed(self):
        """Check if FFmpeg is installed and working"""
        return os.path.exists(self.ffmpeg_exe) and os.path.exists(self.install_marker)

    def get_latest_version(self):
        """Get latest FFmpeg version and download URL"""
        try:
            response = requests.get(self.FFMPEG_RELEASES_URL, allow_redirects=True)
            latest_url = response.url
            version = latest_url.split('/')[-1]
            download_url = f"https://github.com/GyanD/codexffmpeg/releases/download/{version}/ffmpeg-{version}-full_build.zip"
            return version, download_url
        except Exception as e:
            logger.error(f"Error getting latest version: {e}")
            raise

    def check_for_updates(self):
        """Check if a newer version is available"""
        if not os.path.exists(self.version_file):
            return True
            
        try:
            with open(self.version_file, 'r') as f:
                current_version = f.read().strip()
            
            latest_version, _ = self.get_latest_version()
            
            if current_version != latest_version:
                print(f"\nNew FFmpeg version available!")
                print(f"Current: {current_version}")
                print(f"Latest: {latest_version}")
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            return False

    def mark_as_installed(self, version):
        """Mark FFmpeg as installed and save version"""
        os.makedirs(os.path.dirname(self.install_marker), exist_ok=True)
        
        # Save installation marker
        with open(self.install_marker, 'w') as f:
            f.write('installed')
            
        # Save version info
        with open(self.version_file, 'w') as f:
            f.write(version)

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

    def extract_ffmpeg(self, archive_path):
        """Extract FFmpeg from zip file"""
        print("\nExtracting FFmpeg...")
        
        try:
            # Ensure extraction directory exists and is empty
            if os.path.exists(self.ffmpeg_path):
                shutil.rmtree(self.ffmpeg_path)
            os.makedirs(self.ffmpeg_path, exist_ok=True)
            
            # Extract archive
            with zipfile.ZipFile(archive_path, 'r') as archive:
                archive.extractall(self.ffmpeg_path)
            
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
                    print("\nUpdating FFmpeg...")
                else:
                    print("FFmpeg is already installed and up to date!")
                    return True
            else:
                print("\nFFmpeg is required to run the bot.")
                print("This will download and install FFmpeg (~150MB)")
                
                response = input("\nDo you want to continue? (y/n): ").lower().strip()
                if response != 'y':
                    print("\nFFmpeg installation cancelled. The bot cannot run without FFmpeg.")
                    sys.exit(0)
            
            print("\nSetting up FFmpeg...")
            
            # Get latest version and download URL
            version, download_url = self.get_latest_version()
            
            # Create necessary directories
            os.makedirs(self.data_path, exist_ok=True)
            os.makedirs(self.ffmpeg_path, exist_ok=True)
            
            # Download FFmpeg
            archive_path = os.path.join(self.data_path, f'ffmpeg-{version}.zip')
            archive_path = self.download_file(
                download_url,
                archive_path,
                "FFmpeg"
            )
            
            # Extract it
            self.extract_ffmpeg(archive_path)
            
            # Clean up unnecessary files
            self.cleanup_ffmpeg()
            
            # Mark as installed with version
            self.mark_as_installed(version)
            
            print("\nFFmpeg setup complete!")
            return True
            
        except Exception as e:
            logger.error(f"Error setting up FFmpeg: {e}")
            raise

    def cleanup_ffmpeg(self):
        """Clean up unnecessary FFmpeg files"""
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