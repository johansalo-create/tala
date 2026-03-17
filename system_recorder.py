"""
System audio recorder using BlackHole virtual audio device.
Records both system audio and microphone input.
"""
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime
from config import INPUT_DIR, FFMPEG_CMD


def check_blackhole_installed():
    """Check if BlackHole audio device is available."""
    result = subprocess.run(
        ["system_profiler", "SPAudioDataType"],
        capture_output=True, text=True
    )
    return "BlackHole" in result.stdout


def get_blackhole_device():
    """Get the BlackHole device name."""
    result = subprocess.run(
        ["system_profiler", "SPAudioDataType"],
        capture_output=True, text=True
    )
    # Look for BlackHole 2ch or BlackHole 16ch
    if "BlackHole 2ch" in result.stdout:
        return "BlackHole 2ch"
    elif "BlackHole 16ch" in result.stdout:
        return "BlackHole 16ch"
    elif "BlackHole" in result.stdout:
        return "BlackHole"
    return None


def check_multi_output_exists():
    """Check if a Multi-Output Device is configured."""
    result = subprocess.run(
        ["system_profiler", "SPAudioDataType"],
        capture_output=True, text=True
    )
    return "Multi-Output Device" in result.stdout


def get_audio_device_index(device_name):
    """Get the ffmpeg device index for an audio device."""
    result = subprocess.run(
        [FFMPEG_CMD, "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        capture_output=True, text=True
    )
    # Parse stderr for device list (ffmpeg outputs to stderr)
    lines = result.stderr.split('\n')
    audio_section = False
    for line in lines:
        if "AVFoundation audio devices:" in line:
            audio_section = True
            continue
        if audio_section and device_name in line:
            # Extract index from line like "[AVFoundation ...] [0] BlackHole 2ch"
            import re
            match = re.search(r'\[(\d+)\]', line)
            if match:
                return match.group(1)
    return None


class SystemRecorder:
    """Records system audio + microphone using ffmpeg and BlackHole."""

    def __init__(self):
        self.process = None
        self.is_recording = False
        self.output_file = None
        self.start_time = None

    def start_recording(self, filename=None, include_mic=True):
        """Start recording system audio (and optionally microphone)."""
        if self.is_recording:
            return False, "Already recording"

        blackhole_device = get_blackhole_device()
        if not blackhole_device:
            return False, "BlackHole not installed"

        # Generate filename
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d %H%M%S")
            filename = f"{timestamp}-system.m4a"

        self.output_file = INPUT_DIR / filename
        INPUT_DIR.mkdir(parents=True, exist_ok=True)

        # Get device indices
        blackhole_idx = get_audio_device_index(blackhole_device)

        if include_mic:
            # Record both microphone (device 0) and BlackHole, mix them together
            # This captures both what you say AND what others say
            self.process = subprocess.Popen([
                FFMPEG_CMD,
                "-f", "avfoundation",
                "-i", ":0",  # Default microphone
                "-f", "avfoundation",
                "-i", f":{blackhole_idx or blackhole_device}",  # System audio via BlackHole
                "-filter_complex", "amix=inputs=2:duration=longest",  # Mix both inputs
                "-c:a", "aac",
                "-b:a", "128k",
                "-y",
                str(self.output_file)
            ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            # Record only system audio (BlackHole)
            self.process = subprocess.Popen([
                FFMPEG_CMD,
                "-f", "avfoundation",
                "-i", f":{blackhole_idx or blackhole_device}",
                "-c:a", "aac",
                "-b:a", "128k",
                "-y",
                str(self.output_file)
            ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        self.is_recording = True
        self.start_time = time.time()
        return True, str(self.output_file)
    
    def stop_recording(self):
        """Stop recording and return the output file path."""
        if not self.is_recording or not self.process:
            return None, "Not recording"
        
        # Send 'q' to ffmpeg to stop gracefully
        try:
            self.process.stdin.write(b'q')
            self.process.stdin.flush()
        except:
            pass
        
        # Wait for process to finish
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
        
        self.is_recording = False
        duration = time.time() - self.start_time
        output = self.output_file
        
        self.process = None
        self.output_file = None
        self.start_time = None
        
        return output, f"Recorded {duration:.1f} seconds"
    
    def get_duration(self):
        """Get current recording duration in seconds."""
        if self.is_recording and self.start_time:
            return time.time() - self.start_time
        return 0


def show_blackhole_setup_instructions():
    """Return instructions for setting up BlackHole."""
    return """To record system audio, you need to set up BlackHole:

1. Install BlackHole:
   brew install blackhole-2ch

2. Create a Multi-Output Device:
   - Open "Audio MIDI Setup" (search in Spotlight)
   - Click "+" at bottom left → "Create Multi-Output Device"
   - Check both your speakers AND "BlackHole 2ch"
   - Right-click the Multi-Output Device → "Use This Device For Sound Output"

3. Now your system audio will go to both speakers AND BlackHole (for recording)

After setup, restart this app and try recording again."""


if __name__ == "__main__":
    # Test
    print(f"BlackHole installed: {check_blackhole_installed()}")
    print(f"BlackHole device: {get_blackhole_device()}")
    print(f"Multi-Output exists: {check_multi_output_exists()}")
