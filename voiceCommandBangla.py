"""
voiceCommandBangla.py -- Bangla Voice Control for Niryo Ned
===========================================================

Standalone Bangla-language voice controller using the Sherpa-ONNX
Online Zipformer Transducer model for real-time, fully offline
Bangla (Bengali) speech recognition.

Bangla Commands:
  tulun  (তুলুন)           -> Pick object
  rakun  (রাখুন)           -> Drop / place object
  dekun  (দেখুন)           -> Detect object in workspace
  shajan (সাজান)           -> Sort object by color
  chodun (ছাড়ুন)          -> Release / open gripper
  lal bine rakun           -> Drop in RED bin
  nil bine rakun           -> Drop in BLUE bin
  shobuj bine rakun        -> Drop in GREEN bin
  rang ki  (রং কী)         -> Report object color
  akiti ki (আকৃতি কী)     -> Report object shape
  bari jao (বাড়ি যাও)    -> Return to observation pose
  bondho koro (বন্ধ করো)  -> Shutdown

Setup:
  pip install sherpa-onnx pyniryo2 sounddevice scipy pyttsx3
  Download Bangla Zipformer model from:
  https://k2-fsa.github.io/sherpa/onnx/pretrained_models/online-transducer/zipformer-transducer-models.html
"""

import sys
import os
import time
import sounddevice as sd
from scipy.io.wavfile import write
from pyniryo2 import NiryoRobot, ObjectColor, ObjectShape

try:
    import sherpa_onnx
    HAS_SHERPA = True
except ImportError:
    HAS_SHERPA = False
    print("[WARNING] sherpa-onnx not installed. Run: pip install sherpa-onnx")

try:
    import pyttsx3
    HAS_TTS = True
except ImportError:
    HAS_TTS = False

# =========================================
# CONFIG
# =========================================
ROBOT_IP       = "10.10.10.10"
WORKSPACE_NAME = "work_2k22"

RECORD_SECONDS = 4
SAMPLE_RATE    = 16000   # Zipformer expects 16 kHz

# Sherpa-ONNX Zipformer Bangla model paths
# Download: https://k2-fsa.github.io/sherpa/onnx/pretrained_models/
#           online-transducer/zipformer-transducer-models.html
SHERPA_ENCODER = "models/bangla-zipformer/encoder-epoch-99-avg-1.onnx"
SHERPA_DECODER = "models/bangla-zipformer/decoder-epoch-99-avg-1.onnx"
SHERPA_JOINER  = "models/bangla-zipformer/joiner-epoch-99-avg-1.onnx"
SHERPA_TOKENS  = "models/bangla-zipformer/tokens.txt"

OBSERVATION_POSE = [0.208, -0.005, 0.407, -1.541, 1.435, -1.505]

DROP_POSES = {
    ObjectColor.RED:   [-0.079, 0.293, 0.185, -0.093, 1.493, 1.60],
    ObjectColor.BLUE:  [-0.001, 0.299, 0.185, -0.384, 1.503, 1.230],
    ObjectColor.GREEN: [0.071,  0.295, 0.178, -0.732, 1.409, 0.904],
}

# =========================================
# BANGLA COMMAND KEYWORD MAP
# Phonetic romanizations the Zipformer
# model typically outputs for each command.
# Priority: longer / more specific strings listed first.
# =========================================
BANGLA_COMMANDS = {
    "pick"       : ["tulun", "tolo", "dharo", "nao", "tul"],
    "drop"       : ["rakun", "rakho", "rakhun", "rak"],
    "release"    : ["chodun", "charo", "charun", "chod", "charao"],
    "detect"     : ["dekun", "dekhun", "dekho", "dek", "dekh"],
    "color"      : ["rang ki", "rang", "rong"],
    "shape"      : ["akiti ki", "akiti", "aakriti", "akr"],
    "sort"       : ["shajan", "sajan", "shaj", "guchano", "sajao"],
    "observe"    : ["bari jao", "bari", "ghore", "upore", "poryobek"],
    "drop_red"   : ["lal bine", "lal bin", "lal"],
    "drop_blue"  : ["nil bine", "nil bin", "neel bine", "neel bin", "neel", "nil"],
    "drop_green" : ["shobuj bine", "shobuj bin", "sobuj bine", "sobuj bin", "shobuj", "sobuj"],
    "shutdown"   : ["bondho koro", "bandho koro", "bondho", "bandho", "shesh", "band koro"],
}

# =========================================
# TTS
# =========================================
_tts_engine = None
if HAS_TTS:
    _tts_engine = pyttsx3.init()
    _tts_engine.setProperty("rate", 160)

def speak(text: str):
    print(f"[Robot] {text}")
    if _tts_engine:
        _tts_engine.say(text)
        _tts_engine.runAndWait()

# =========================================
# SHERPA-ONNX STT
# =========================================
def load_sherpa_recognizer():
    if not HAS_SHERPA:
        raise RuntimeError("sherpa-onnx is not installed.")
    for path in [SHERPA_ENCODER, SHERPA_DECODER, SHERPA_JOINER, SHERPA_TOKENS]:
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Model file not found: {path}\n"
                "Download from: https://k2-fsa.github.io/sherpa/onnx/"
                "pretrained_models/online-transducer/zipformer-transducer-models.html"
            )
    recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
        encoder         = SHERPA_ENCODER,
        decoder         = SHERPA_DECODER,
        joiner          = SHERPA_JOINER,
        tokens          = SHERPA_TOKENS,
        num_threads     = 2,
        sample_rate     = SAMPLE_RATE,
        feature_dim     = 80,
        decoding_method = "greedy_search",
        provider        = "cpu",
    )
    print("[STT] Sherpa-ONNX Bangla Zipformer loaded.")
    return recognizer

def transcribe_bangla(recognizer, wav_path: str) -> str:
    import wave
    import numpy as np
    try:
        with wave.open(wav_path, "rb") as wf:
            frames  = wf.readframes(wf.getnframes())
            samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        stream = recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, samples)
        recognizer.decode_stream(stream)
        text = stream.result.text.strip().lower()
        print(f"[STT] Bangla heard: \"{text}\"")
        return text
    except Exception as e:
        print(f"[STT] Error: {e}")
        return ""

def listen() -> str:
    print("\n[Voice] Listening... (বলুন)")
    recording = sd.rec(
        int(RECORD_SECONDS * SAMPLE_RATE),
        samplerate=SAMPLE_RATE, channels=1, dtype="int16"
    )
    sd.wait()
    path = "bangla_command.wav"
    write(path, SAMPLE_RATE, recording)
    return path

# =========================================
# COMMAND MATCHER
# =========================================
def match_command(text: str) -> str:
    for action, keywords in BANGLA_COMMANDS.items():
        for kw in keywords:
            if kw in text:
                return action
    return ""

# =========================================
# ROBOT HELPERS
# =========================================
def go_to_observation():
    robot.arm.move_pose(OBSERVATION_POSE)
    robot.tool.open_gripper()

# =========================================
# COMMAND HANDLERS
# =========================================
def cmd_pick():
    speak("bosto tulchi")           # Picking object
    found, shape_ret, color_ret = robot.vision.vision_pick(
        workspace_name=WORKSPACE_NAME,
        height_offset=0.0,
        shape=ObjectShape.ANY,
        color=ObjectColor.ANY,
    )
    speak("tola hoyeche" if found else "bosto paoa jaini")

def cmd_drop():
    speak("rakhchi")                # Placing
    robot.arm.move_pose(DROP_POSES[ObjectColor.RED])
    robot.tool.open_gripper()
    speak("rakha hoyeche")          # Placed
    go_to_observation()

def cmd_drop_color(color_key: ObjectColor, color_name: str):
    speak(f"{color_name} bine rakhchi")
    robot.arm.move_pose(DROP_POSES[color_key])
    robot.tool.open_gripper()
    speak("rakha hoyeche")
    go_to_observation()

def cmd_release():
    speak("chhere dichhi")          # Releasing
    robot.tool.open_gripper()
    speak("chhara hoyeche")         # Released

def cmd_detect():
    speak("dekhchi")                # Looking
    found, _, shape_ret, color_ret = robot.vision.detect_object(
        workspace_name=WORKSPACE_NAME,
        shape=ObjectShape.ANY, color=ObjectColor.ANY,
    )
    speak(f"ami dekhchi {color_ret} {shape_ret}" if found else "kono bosto nei")

def cmd_color():
    speak("rong dekhchi")
    found, _, shape_ret, color_ret = robot.vision.detect_object(
        workspace_name=WORKSPACE_NAME,
        shape=ObjectShape.ANY, color=ObjectColor.ANY,
    )
    speak(f"rong holo {color_ret}" if found else "kono bosto nei")

def cmd_shape():
    speak("akiti dekhchi")
    found, _, shape_ret, color_ret = robot.vision.detect_object(
        workspace_name=WORKSPACE_NAME,
        shape=ObjectShape.ANY, color=ObjectColor.ANY,
    )
    speak(f"akiti holo {shape_ret}" if found else "kono bosto nei")

def cmd_sort():
    speak("sajano hochhe")          # Sorting
    found, shape_ret, color_ret = robot.vision.vision_pick(
        workspace_name=WORKSPACE_NAME,
        height_offset=0.0,
        shape=ObjectShape.ANY, color=ObjectColor.ANY,
    )
    if not found:
        speak("sajanor jonyo bosto nei")
        return
    robot.arm.move_pose(DROP_POSES[color_ret])
    robot.tool.open_gripper()
    speak("sajano hoyeche")         # Sorted
    go_to_observation()

def cmd_observe():
    speak("porjobekkhon obosthanay jachhi")  # Going to observation
    go_to_observation()
    speak("prostut")                # Ready

# =========================================
# CONNECT
# =========================================
try:
    print("Connecting to robot...")
    robot = NiryoRobot(ROBOT_IP)
except Exception as e:
    print(f"Connection failed: {e}")
    sys.exit(1)

# =========================================
# MAIN LOOP
# =========================================
try:
    recognizer = load_sherpa_recognizer()

    speak("robot chalu hochhe")     # Robot initializing
    print("Calibrating...")
    robot.arm.calibrate_auto()
    robot.tool.update_tool()
    time.sleep(1.5)
    go_to_observation()
    speak("prostut. bolun.")        # Ready. Speak.

    while True:
        wav_path = listen()
        command  = transcribe_bangla(recognizer, wav_path)

        if not command:
            print("[Voice] (kichhu bojha jaini, abar shunchhi)")
            continue

        action = match_command(command)
        print(f"[Voice] Matched: '{action}'  |  Text: '{command}'")

        if   action == "shutdown"   : speak("bondho hochhe"); break
        elif action == "detect"     : cmd_detect()
        elif action == "color"      : cmd_color()
        elif action == "shape"      : cmd_shape()
        elif action == "sort"       : cmd_sort()
        elif action == "observe"    : cmd_observe()
        elif action == "pick"       : cmd_pick()
        elif action == "drop_red"   : cmd_drop_color(ObjectColor.RED,   "lal")
        elif action == "drop_blue"  : cmd_drop_color(ObjectColor.BLUE,  "nil")
        elif action == "drop_green" : cmd_drop_color(ObjectColor.GREEN, "shobuj")
        elif action == "drop"       : cmd_drop()
        elif action == "release"    : cmd_release()
        else                        : speak("command bojha jaini")  # Not recognized

except KeyboardInterrupt:
    speak("thami")
except Exception as e:
    print(f"Error: {e}")
    speak("kichhu ekta vul hoyeche")
finally:
    try:
        go_to_observation()
    except Exception:
        pass
    speak("songjoug bichchhinna")   # Disconnected
    robot.end()
    print("Done")
