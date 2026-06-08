"""Speak Thai text via gTTS + mpg123."""
import subprocess
import tempfile
import logging
from gtts import gTTS

log = logging.getLogger(__name__)

def speak_th(text: str):
    """Block until speech finishes. Falls back silently on error."""
    try:
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
            gTTS(text=text, lang='th').save(f.name)
            subprocess.run(['mpg123', '-q', f.name], check=False)
    except Exception as e:
        log.warning(f"TTS failed: {e}")