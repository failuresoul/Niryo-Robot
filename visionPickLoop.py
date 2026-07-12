import sys
import time
from pyniryo2 import NiryoRobot, ObjectColor, ObjectShape

# =========================
# CONNECT
# =========================
try:
    print("Connecting...")
    robot = NiryoRobot("10.10.10.10")
except Exception as e:
    print("Connection failed:", e)
    sys.exit(1)

# =========================
# CONFIG
# =========================
WORKSPACE = "work_2k22"

OBS_POSE = [0.208,-0.005,0.407,-1.541,1.435,-1.505]
home_pose=[0.135,0.000,0.213,-0.007,0.751,0.000]
DROP_POSES = {
    ObjectColor.RED:   [-0.079,0.293,0.185,-0.093,1.493,1.60],
    ObjectColor.BLUE:  [-0.001,0.299,0.185,-0.384,1.503,1.230],
    ObjectColor.GREEN: [0.071,0.295,0.178,-0.732,1.409,0.904],
}

# =========================
# CONVEYOR SETUP (IMPORTANT)
# =========================
# conveyor_id = robot.conveyor.set_conveyor()
robot.tool.close_gripper()
# def run_conveyor_step():
#     print("→ Conveyor moving...")
#     robot.conveyor.run_conveyor(conveyor_id, speed=50)
#     time.sleep(2)  # adjust for how far objects move
#     robot.conveyor.stop_conveyor(conveyor_id)

def go_obs():
    print("→ Observation pose")
    robot.arm.move_pose(OBS_POSE)
    # robot.update_tool()
    time.sleep(0.5)
    #robot.tool.open_gripper()

# =========================
# INIT
# =========================
print("Calibrating...")
robot.arm.calibrate_auto()
go_obs()

# =========================
# MAIN LOOP
# =========================
try:
    while True:
        print("\n--- Scanning ---")

        obj_found, shape, color = robot.vision.vision_pick(

            workspace_name=WORKSPACE,
            height_offset=0.0,
            shape=ObjectShape.ANY,
            color=ObjectColor.ANY
        )

        # =========================
        # OBJECT FOUND
        # =========================
        if obj_found:
            
            print(f"Detected: {color} | {shape}")
            print("Picking...")
            robot.tool.close_gripper()
            time.sleep(0.5)

            if color in DROP_POSES:
                print(f"Dropping {color}")
                robot.arm.move_pose(DROP_POSES[color])
                # robot.update_tool()
                time.sleep(0.5)
                robot.tool.open_gripper()
                time.sleep(2.0)
                robot.arm.move_pose(home_pose)
            go_obs()

        # =========================
        # OBJECT NOT FOUND
        # =========================
        else:
            print("No object detected")
            # run_conveyor_step()
            go_obs()
        time.sleep(1)
        robot.tool.close_gripper()

except KeyboardInterrupt:
    print("\nStopping...")

finally:
    # robot.conveyor.stop_conveyor(conveyor_id)
    go_obs()
    robot.end()
    print("Safe shutdown")