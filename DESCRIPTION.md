# Niryo Robot — Gesture, Voice & Vision Control

A collection of Python scripts for controlling a **Niryo NED** robotic arm through multiple input modes:

- **Hand Gesture Control** (`gestureControl.py`, `gesture_control_final.py`) — Uses MediaPipe hand tracking to map real-time hand gestures (pinch, point, open hand) to robot pick-and-place actions.
- **Voice Command Control** (`voiceCommandFinal.py`) — Speech-to-text interface supporting commands like "pick", "drop", "sort", and color-specific actions via USB or GPIO audio backends.
- **Vision Pick Loop** (`visionPickLoop.py`) — Autonomous color-sorting loop using the robot's built-in vision system to detect, pick, and place objects by color.

All scripts connect to the robot in **hotspot mode** at `10.10.10.10`.
