import sys, os, math, time, threading, queue, urllib.request
import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from pyniryo2 import NiryoRobot, ObjectColor, ObjectShape

# --- Model download ---
model_path = "hand_landmarker.task"
if not os.path.exists(model_path):
    print("Downloading hand_landmarker.task...")
    urllib.request.urlretrieve(
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task",
        model_path
    )

# --- MediaPipe setup ---
base_options = python.BaseOptions(model_asset_path=model_path)
options = vision.HandLandmarkerOptions(
    base_options=base_options,
    num_hands=2,
    min_hand_detection_confidence=0.7,
    min_hand_presence_confidence=0.7
)
detector = vision.HandLandmarker.create_from_options(options)

# --- Robot connection ---
try:
    robot = NiryoRobot("192.168.0.103")
    robot.arm.calibrate_auto()
except Exception as e:
    print(f"Connection failed: {e}")
    sys.exit(1)

DROP_POSE        = [-0.001,0.299,0.185,-0.384,1.503,1.230]   # fallback pose for unrecognized colors
OBSERVATION_POSE = [0.208,-0.005,0.407,-1.541,1.435,-1.505]
WORKSPACE_NAME   = "work_2k22"

# --- Color-sorted drop poses (from visionPickLoop.py) ---
DROP_POSES = {
    ObjectColor.RED:   [-0.079,0.293,0.185,-0.093,1.493,1.60],
    ObjectColor.BLUE:  [-0.001,0.299,0.185,-0.384,1.503,1.230],
    ObjectColor.GREEN: [0.071,0.295,0.178,-0.732,1.409,0.904],
}

# --- Robot background thread ---
# Queue size 2: allows one executing + one pending, prevents total blockage
robot_cmd_queue  = queue.Queue(maxsize=2)
robot_state      = "IDLE"
robot_state_lock = threading.Lock()
last_picked_color = None   # remembers which color/pose to drop at, set on successful pick

def robot_worker():
    global last_picked_color
    robot.arm.move_pose(OBSERVATION_POSE)
    robot.tool.open_gripper()
    set_state("OBSERVING")
    while True:
        cmd = robot_cmd_queue.get()
        if cmd is None:
            break
        action = cmd.get("action")
        try:
            if action == "observe":
                robot.arm.move_pose(OBSERVATION_POSE)
                robot.tool.open_gripper()
                set_state("OBSERVING")

            elif action == "pick":
                set_state("PICKING")           # transitional — blocks re-trigger
                found, shape, color = robot.vision.vision_pick(
                    workspace_name=WORKSPACE_NAME,
                    height_offset=0.0,
                    shape=ObjectShape.ANY,
                    color=ObjectColor.ANY
                )
                if found:
                    # FIX 1: convert enums to str before concatenating
                    print(f"Pick success: {str(color)} {str(shape)}")
                    last_picked_color = color      # remember for color-sorted drop
                    set_state("HOLDING")
                else:
                    print("Pick failed — no object detected, returning to observe")
                    last_picked_color = None
                    robot.arm.move_pose(OBSERVATION_POSE)
                    robot.tool.open_gripper()
                    set_state("OBSERVING")     # auto-recover, ready for next pinch

            elif action == "drop_pose":
                # Route to the pose matching the picked object's color,
                # falling back to the default DROP_POSE for unmapped colors.
                target_pose = DROP_POSES.get(last_picked_color, DROP_POSE)
                print(f"Moving to drop pose for color: {str(last_picked_color)}")
                robot.arm.move_pose(target_pose)
                set_state("READY_TO_DROP")

            elif action == "drop":
                print(f"Dropping {str(last_picked_color)} object")
                robot.tool.open_gripper()
                last_picked_color = None           # reset for next cycle
                set_state("IDLE")

        except Exception as e:
            print(f"Robot error: {e}")
            # Always recover to a safe known state on any exception
            try:
                robot.arm.move_pose(OBSERVATION_POSE)
                robot.tool.open_gripper()
            except Exception:
                pass
            last_picked_color = None
            set_state("OBSERVING")

        robot_cmd_queue.task_done()

def set_state(s):
    global robot_state
    with robot_state_lock:
        robot_state = s

def get_state():
    with robot_state_lock:
        return robot_state

def send_cmd(cmd):
    try:
        robot_cmd_queue.put_nowait(cmd)
    except queue.Full:
        pass

worker = threading.Thread(target=robot_worker, daemon=True)
worker.start()

# --- Helpers ---
def get_distance(p1, p2):
    return math.hypot(p1.x - p2.x, p1.y - p2.y)

def grab_latest_frame(cap):
    grabbed = False
    for _ in range(4):
        grabbed = cap.grab()
    if not grabbed:
        return None
    ret, frame = cap.retrieve()
    return frame if ret else None

def is_right_hand(handedness_list):
    if not handedness_list:
        return False
    return handedness_list[0].category_name == "Left"

# --- Camera ---
cap = cv2.VideoCapture("http://192.168.0.100:8080/video")
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

INFERENCE_EVERY  = 3
GESTURE_COOLDOWN = 1.5          # slightly longer — reduces accidental re-triggers

frame_count       = 0
last_gesture_time = 0.0
last_landmarks    = None

print("--- Control loop active (right hand only) ---")
print("Pinch: pick | Point right: drop pose | Open hand: drop | Hand up: observe")

try:
    while True:
        frame = grab_latest_frame(cap)
        if frame is None:
            print("Stream read failed, retrying...")
            continue

        frame   = cv2.flip(frame, 1)
        h, w, _ = frame.shape
        frame_count += 1

        # NEW — only replaces last_landmarks when a detection actually succeeds
        LANDMARK_TIMEOUT = 0.5          # seconds before stale landmarks are discarded
        last_landmark_time = 0.0        # add this near your other state variables at top

        if frame_count % INFERENCE_EVERY == 0:
            rgb      = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result   = detector.detect(mp_image)

            found_right = False
            for landmarks, handedness in zip(result.hand_landmarks, result.handedness):
                if is_right_hand(handedness):
                    last_landmarks     = landmarks   # only update on success
                    last_landmark_time = time.time()
                    found_right        = True
                    break

            # Only clear if hand has been genuinely absent for a while
            if not found_right and (time.time() - last_landmark_time) > LANDMARK_TIMEOUT:
                last_landmarks = None

        state       = get_state()
        now         = time.time()
        cooldown_ok = (now - last_gesture_time) > GESTURE_COOLDOWN

        if last_landmarks:
            lm = last_landmarks

            thumb_tip = lm[4]
            index_tip = lm[8]
            wrist     = lm[0]
            m_tip     = lm[12]
            r_tip     = lm[16]

            for point in lm:
                cv2.circle(frame, (int(point.x * w), int(point.y * h)), 5, (0, 255, 100), -1)

            pinch_dist = get_distance(thumb_tip, index_tip)

            # Wrist → middle fingertip vector angle
            vec_x     = m_tip.x - wrist.x
            vec_y     = m_tip.y - wrist.y
            angle_deg = math.degrees(math.atan2(vec_y, vec_x))

            # Direction arrow debug
            wx, wy = int(wrist.x * w), int(wrist.y * h)
            mx, my = int(m_tip.x * w), int(m_tip.y * h)
            cv2.arrowedLine(frame, (wx, wy), (mx, my), (255, 100, 0), 2)
            cv2.putText(frame, f"{angle_deg:.1f}deg", (mx + 8, my),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 100, 0), 1)

            pinching       = pinch_dist < 0.04
            open_hand      = pinch_dist > 0.08
            hand_up        = (m_tip.y < wrist.y - 0.2 and
                              r_tip.y < wrist.y - 0.2 and
                              open_hand)
            pointing_right = -40 < angle_deg < 40

            # --- State machine ---
            # FIX 2: PICKING is a busy state — no gestures accepted until done
            if state == "PICKING":
                pass  # robot worker will transition state when finished

            elif pinching and state in ("IDLE", "OBSERVING") and cooldown_ok:
                print("[Gesture] Pinch → vision pick")
                send_cmd({"action": "pick"})
                last_gesture_time = now

            elif pointing_right and state == "HOLDING" and cooldown_ok:
                print("[Gesture] Pointing right → drop pose")
                send_cmd({"action": "drop_pose"})
                last_gesture_time = now

            elif open_hand and state == "READY_TO_DROP" and cooldown_ok:
                print("[Gesture] Open hand → drop")
                send_cmd({"action": "drop"})
                last_gesture_time = now

            elif hand_up and state not in ("HOLDING", "PICKING") and cooldown_ok:
                print("[Gesture] Hand up → observe")
                send_cmd({"action": "observe"})
                last_gesture_time = now

            cv2.putText(frame, f"pinch:{pinch_dist:.2f}  angle:{angle_deg:.1f}", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 0), 1)

        else:
            cv2.putText(frame, "No right hand detected", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 100, 255), 1)

        cv2.putText(frame, f"State: {state}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.imshow("Hand Gesture Robot Control", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

finally:
    cap.release()
    cv2.destroyAllWindows()
    detector.close()
    robot_cmd_queue.put(None)
    try:
        robot.arm.move_pose(OBSERVATION_POSE)
        robot.tool.open_gripper()
        robot.end()
    except Exception as e:
        print(f"Cleanup error: {e}")