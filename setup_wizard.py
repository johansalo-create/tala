"""
First-launch setup wizard for Transcription app.
Checks dependencies and downloads the Whisper model.
"""
import os
import sys
import subprocess
import urllib.request
import rumps
from pathlib import Path
from config import MODEL_PATH, MODEL_URL, MODEL_DIR, WHISPER_CMD

VAD_MODEL_PATH = MODEL_DIR / "ggml-silero-vad.bin"
VAD_MODEL_URL = "https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin"


def check_homebrew():
    """Check if Homebrew is installed."""
    return subprocess.run(["which", "brew"], capture_output=True).returncode == 0


def check_ffmpeg():
    """Check if ffmpeg is installed (check Homebrew paths directly)."""
    for path in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]:
        if os.path.exists(path):
            return True
    return subprocess.run(["which", "ffmpeg"], capture_output=True).returncode == 0


def check_whisper():
    """Check if whisper-cli is installed (check Homebrew paths directly)."""
    if WHISPER_CMD is not None:
        return True
    for path in ["/opt/homebrew/bin/whisper-cli", "/usr/local/bin/whisper-cli"]:
        if os.path.exists(path):
            return True
    return False


def check_model():
    """Check if the Whisper model is downloaded."""
    return MODEL_PATH.exists() and MODEL_PATH.stat().st_size > 100_000_000


def check_vad_model():
    """Check if the VAD model is downloaded."""
    return VAD_MODEL_PATH.exists() and VAD_MODEL_PATH.stat().st_size > 100_000


def download_file(url, dest_path, progress_callback=None):
    """Download a file from URL to dest_path."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    def report_progress(block_num, block_size, total_size):
        if progress_callback and total_size > 0:
            percent = min(100, block_num * block_size * 100 // total_size)
            progress_callback(percent)

    urllib.request.urlretrieve(url, dest_path, reporthook=report_progress)


def download_model(progress_callback=None):
    """Download the Whisper model."""
    download_file(MODEL_URL, MODEL_PATH, progress_callback)


def download_vad_model(progress_callback=None):
    """Download the Silero VAD model."""
    download_file(VAD_MODEL_URL, VAD_MODEL_PATH, progress_callback)


def run_setup():
    """Run the setup wizard and return True if setup is complete."""
    issues = []
    
    if not check_ffmpeg():
        issues.append("ffmpeg")
    
    if not check_whisper():
        issues.append("whisper-cli")
    
    if issues:
        msg = f"Missing dependencies: {', '.join(issues)}\n\n"
        msg += "Install them with Homebrew:\n"
        msg += "brew install ffmpeg whisper-cpp"
        
        response = rumps.alert(
            title="Setup Required",
            message=msg,
            ok="Open Terminal",
            cancel="Quit"
        )
        
        if response == 1:  # OK clicked
            # Open Terminal with install command
            script = 'tell application "Terminal" to do script "brew install ffmpeg whisper-cpp"'
            subprocess.run(["osascript", "-e", script])
        return False
    
    models_needed = []
    if not check_model():
        models_needed.append(("Whisper speech recognition model (~547 MB)", download_model))
    if not check_vad_model():
        models_needed.append(("Silero VAD model (~885 KB)", download_vad_model))

    if models_needed:
        names = "\n".join(f"• {name}" for name, _ in models_needed)
        response = rumps.alert(
            title="Download Models",
            message=f"The following models need to be downloaded:\n\n{names}\n\nThis only happens once.",
            ok="Download",
            cancel="Quit"
        )

        if response == 1:  # OK clicked
            rumps.notification(
                "Transcription",
                "Downloading Models",
                "This may take a few minutes..."
            )

            try:
                for name, download_fn in models_needed:
                    download_fn()
                rumps.notification(
                    "Transcription",
                    "Download Complete",
                    "All models are ready!"
                )
            except Exception as e:
                rumps.alert(
                    title="Download Failed",
                    message=f"Error downloading model: {e}\n\nPlease check your internet connection and try again."
                )
                return False
        else:
            return False

    return True


if __name__ == "__main__":
    # Test the setup
    print(f"Homebrew: {check_homebrew()}")
    print(f"ffmpeg: {check_ffmpeg()}")
    print(f"whisper-cli: {check_whisper()} ({WHISPER_CMD})")
    print(f"Model: {check_model()} ({MODEL_PATH})")
    print(f"VAD Model: {check_vad_model()} ({VAD_MODEL_PATH})")
