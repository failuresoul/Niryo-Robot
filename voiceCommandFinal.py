"""
Voice-controlled Niryo Ned — USB/GPIO audio + Google/faster-whisper STT.
========================================================================

Config flags at the top let you switch between:
  AUDIO_BACKEND  → "usb" (plug-and-play) or "gpio" (I2S on Pi GPIO)
  STT_ENGINE     → "google" (cloud, needs internet) or "faster_whisper" (local, offline)
  WHISPER_MODEL  → model size when using faster-whisper ("tiny", "base", "small", etc.)
"""

import sys
import abc
import os
import platform
import time

import sounddevice as sd
from scipy.io.wavfile import write
import speech_recognition as sr
from pyniryo2 import NiryoRobot, ObjectColor, ObjectShape
from faster_whisper import WhisperModel

try:
    import win32com.client
    HAS_SAPI = True
except ImportError:
    HAS_SAPI = False

try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    HAS_PYTTSX3 = False

try:
    import RPi.GPIO as GPIO
    HAS_RPI_GPIO = True
except ImportError:
    HAS_RPI_GPIO = False

# =========================================
# CONFIG
# =========================================
ROBOT_IP = "192.168.0.103"
WORKSPACE_NAME = "work_2k22"

AUDIO_BACKEND = "usb"                        # "usb" or "gpio"
STT_ENGINE = "google"                        # "google" or "faster_whisper"
WHISPER_MODEL = "tiny"                       # "tiny" | "base" | "small" | "medium" | "large"

RECORD_SECONDS = 4
SAMPLE_RATE = 44100

OBSERVATION_POSE = [0.208,-0.005,0.407,-1.541,1.435,-1.505]

DROP_POSES = {
    ObjectColor.RED:   [-0.079,0.293,0.185,-0.093,1.493,1.60],
    ObjectColor.BLUE:  [-0.001,0.299,0.185,-0.384,1.503,1.230],
    ObjectColor.GREEN: [0.071,0.295,0.178,-0.732,1.409,0.904],
}

# =========================================
# AUDIO ABSTRACTION
# =========================================
_whisper_model = None

class AudioBackend(abc.ABC):
    """Swap USB ↔ GPIO by switching AUDIO_BACKEND at the top."""

    @abc.abstractmethod
    def speak(self, text: str): ...

    @abc.abstractmethod
    def listen(self) -> str: ...

    # ---- shared transcription ----
    def _transcribe(self, wav_path: str) -> str:
        if STT_ENGINE == "faster_whisper":
            return self._transcribe_whisper(wav_path)
        return self._transcribe_google(wav_path)

    def _transcribe_google(self, wav_path: str) -> str:
        recognizer = sr.Recognizer()
        try:
            with sr.AudioFile(wav_path) as source:
                audio = recognizer.record(source)
            return recognizer.recognize_google(audio).lower()
        except sr.UnknownValueError:
            print("[STT] Could not understand audio")
        except sr.RequestError as e:
            print(f"[STT] Google API error: {e}")
        except Exception as e:
            print(f"[STT] Error: {e}")
        return ""

    def _transcribe_whisper(self, wav_path: str) -> str:
        global _whisper_model
        if _whisper_model is None:
            print(f"[STT] Loading faster-whisper {WHISPER_MODEL}...")
            _whisper_model = WhisperModel(
                WHISPER_MODEL,
                device="auto",
                compute_type="int8",
                download_root=os.getenv("WHISPER_CACHE_DIR", None),
            )
        try:
            segments, info = _whisper_model.transcribe(wav_path, language="en")
            text = "".join(seg.text for seg in segments).strip().lower()
            print(f"[STT] (whisper) {text}")
            return text
        except Exception as e:
            print(f"[STT] Whisper error: {e}")
            return ""


# ---------- USB BACKEND ----------
class USBAudioBackend(AudioBackend):
    """
    Works on Windows (for testing) and Linux/Pi (for deployment).

    Mic:   Any USB microphone or webcam mic.
    Speaker: Any USB speaker, USB headset, or 3.5mm speaker via USB adapter.
    """

    def __init__(self):
        is_win = platform.system() == "Windows"
        if is_win and HAS_SAPI:
            self._engine = win32com.client.Dispatch("SAPI.SpVoice")
            self._tts = lambda t: self._engine.Speak(t)
        elif HAS_PYTTSX3:
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", 175)
            self._tts = lambda t: (self._engine.say(t), self._engine.runAndWait())
        else:
            self._tts = lambda t: None

    def speak(self, text: str):
        print(f"[Robot] {text}")
        self._tts(text)

    def listen(self) -> str:
        print("\n[Voice] Listening...")
        recording = sd.rec(
            int(RECORD_SECONDS * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
        )
        sd.wait()
        write("command.wav", SAMPLE_RATE, recording)
        return self._transcribe("command.wav")


# ---------- GPIO I2S BACKEND ----------
class GPIOAudioBackend(AudioBackend):
    """
    I2S MEMS microphone + I2S DAC/amplifier on Pi GPIO pins.

    HARDWARE WIRING  (BCM pin numbering)

    INMP441 / SPH0645 MEMS Mic:
      - L/R Select → GND (left channel) or 3.3V (right)
      - DOUT       → GPIO 21 (BCM)  ←  I2S data in
      - BCLK       → GPIO 18 (BCM)  ←  I2S bit clock
      - LRCLK/WS   → GPIO 19 (BCM)  ←  I2S word select
      - VDD        → 3.3V
      - GND        → GND

    MAX98357 I2S DAC + Amp (speaker):
      - DIN        → GPIO 21 (BCM)  ←  share with mic DOUT
      - BCLK       → GPIO 18 (BCM)  ←  share with mic BCLK
      - LRCLK/WS   → GPIO 19 (BCM)  ←  share with mic LRCLK
      - VIN        → 5V
      - GND        → GND
      - SD/GAIN    → GND  (or resistor divider for gain)

    I2S is a shared bus — mic DOUT and amp DIN can both connect to GPIO 21.
    The devices share BCLK/LRCLK, and the codec handles half-duplex automatically.

    SOFTWARE SETUP  (/boot/config.txt)

    Add to /boot/config.txt and reboot:
      dtparam=i2s=on
      dtoverlay=googlevoicehat-codec   # for INMP441 / SPH0645
      # Or for the MAX98357 add:
      dtoverlay=max98357a

    After reboot, check with:
      arecord -l       # list capture devices
      aplay -l         # list playback devices
    """

    def __init__(self):
        if HAS_RPI_GPIO:
            GPIO.setmode(GPIO.BCM)

        if HAS_PYTTSX3:
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", 175)

        self._device = self._find_i2s_device()

    @staticmethod
    def _find_i2s_device():
        """Return the ALSA device index of the I2S audio device."""
        try:
            devices = sd.query_devices()
            for idx, dev in enumerate(devices):
                name = dev["name"].lower()
                if "snd_rpi" in name or "googlevoicehat" in name or "max98357" in name:
                    print(f"[GPIO] Found I2S device {idx}: {dev['name']}")
                    return idx
        except Exception as e:
            print(f"[GPIO] Device scan failed: {e}")
        print("[GPIO] No I2S device found — falling back to default")
        return None

    def speak(self, text: str):
        print(f"[Robot] {text}")
        if HAS_PYTTSX3:
            self._engine.say(text)
            self._engine.runAndWait()

    def listen(self) -> str:
        print("\n[Voice] Listening...")
        recording = sd.rec(
            int(RECORD_SECONDS * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            device=self._device,
        )
        sd.wait()
        write("command.wav", SAMPLE_RATE, recording)
        return self._transcribe("command.wav")


# =========================================
# SELECT BACKEND
# =========================================
def make_audio_backend() -> AudioBackend:
    name = AUDIO_BACKEND.lower().strip()
    if name == "gpio":
        return GPIOAudioBackend()
    return USBAudioBackend()

audio = make_audio_backend()


# =========================================
# ROBOT HELPERS
# =========================================
def go_to_observation():
    robot.arm.move_pose(OBSERVATION_POSE)
    robot.tool.open_gripper()


# =========================================
# COMMAND HANDLERS
# =========================================
def cmd_check_object():
    audio.speak("Checking for objects")
    obj_found, rel_pose, shape_ret, color_ret = robot.vision.detect_object(
        workspace_name=WORKSPACE_NAME,
        shape=ObjectShape.ANY,
        color=ObjectColor.ANY,
    )
    if obj_found:
        audio.speak(f"I see a {color_ret} {shape_ret}")
    else:
        audio.speak("No object found")


def cmd_check_color():
    audio.speak("Checking color")
    obj_found, rel_pose, shape_ret, color_ret = robot.vision.detect_object(
        workspace_name=WORKSPACE_NAME,
        shape=ObjectShape.ANY,
        color=ObjectColor.ANY,
    )
    if obj_found:
        audio.speak(f"The color is {color_ret}")
    else:
        audio.speak("No object detected")


def cmd_check_shape():
    audio.speak("Checking shape")
    obj_found, rel_pose, shape_ret, color_ret = robot.vision.detect_object(
        workspace_name=WORKSPACE_NAME,
        shape=ObjectShape.ANY,
        color=ObjectColor.ANY,
    )
    if obj_found:
        audio.speak(f"The shape is {shape_ret}")
    else:
        audio.speak("No object detected")


def cmd_pick():
    audio.speak("Picking object")
    obj_found, shape_ret, color_ret = robot.vision.vision_pick(
        workspace_name=WORKSPACE_NAME,
        height_offset=0.0,
        shape=ObjectShape.ANY,
        color=ObjectColor.ANY,
    )
    if obj_found:
        audio.speak(f"Picked {color_ret} {shape_ret}")
    else:
        audio.speak("Pick failed")


def cmd_drop():
    audio.speak("Going to drop point")
    robot.arm.move_pose(DROP_POSES[ObjectColor.RED])
    robot.tool.open_gripper()
    audio.speak("Dropped")
    go_to_observation()


def cmd_drop_color(color: str):
    color_map = {
        "red": ObjectColor.RED,
        "blue": ObjectColor.BLUE,
        "green": ObjectColor.GREEN,
    }
    mapped = color_map.get(color)
    if not mapped:
        audio.speak(f"I don't know where to drop {color}")
        return
    audio.speak(f"Dropping at {color} bin")
    robot.arm.move_pose(DROP_POSES[mapped])
    robot.tool.open_gripper()
    audio.speak("Dropped")
    go_to_observation()


def cmd_sort():
    audio.speak("Starting sort")
    obj_found, shape_ret, color_ret = robot.vision.vision_pick(
        workspace_name=WORKSPACE_NAME,
        height_offset=0.0,
        shape=ObjectShape.ANY,
        color=ObjectColor.ANY,
    )
    if not obj_found:
        audio.speak("No object to sort")
        return
    audio.speak(f"Found {color_ret} {shape_ret}, sorting")
    robot.arm.move_pose(DROP_POSES[color_ret])
    robot.tool.open_gripper()
    audio.speak("Sorted")
    go_to_observation()


def cmd_observe():
    audio.speak("Going to observation position")
    go_to_observation()
    audio.speak("Ready")

# =========================================
# CONNECT
# =========================================
try:
    print("Connecting...")
    robot = NiryoRobot(ROBOT_IP)
except Exception as e:
    print("Connection failed:", e)
    sys.exit(1)


# =========================================
# MAIN
# =========================================
try:
    audio.speak("Initializing robot")
    print("Calibrating...")
    robot.arm.calibrate_auto()
    robot.tool.update_tool()
    time.sleep(1.5)
    go_to_observation()
    audio.speak("Ready. Say a command.")
 
    while True:
        command = audio.listen().strip().lower()
        if not command:
            print("[Voice] (nothing understood, listening again)")
            continue
        print(f"[Voice] Heard: \"{command}\"")
 
        if any(w in command for w in ["exit", "stop", "shutdown", "quit"]):
            audio.speak("Shutting down")
            break
 
        elif "check" in command or "what" in command or "see" in command or "detect" in command:
            cmd_check_object()
 
        elif "colour" in command or "color" in command:
            cmd_check_color()
 
        elif "shape" in command:
            cmd_check_shape()
 
        elif "sort" in command or "short" in command:
            cmd_sort()
 
        elif "observ" in command or "home" in command:
            cmd_observe()
 
        elif "pick" in command or "grab" in command or "take" in command or "pic" in command:
            cmd_pick()
 
        elif any(w in command for w in ["drop red", "drop blue", "drop green"]):
            for c in ["red", "blue", "green"]:
                if f"drop {c}" in command:
                    cmd_drop_color(c)
                    break
 
        elif "drop" in command or "place" in command or "release" in command:
            cmd_drop()
 
        else:
            audio.speak("Command not recognized")

except KeyboardInterrupt:
    audio.speak("Stopping")
except Exception as e:
    print(f"Error: {e}")
    audio.speak("Something went wrong")

finally:
    print("Returning to safe position...")
    try:
        go_to_observation()
    except Exception:
        pass
    audio.speak("Disconnected")
    robot.end()
    print("Done")