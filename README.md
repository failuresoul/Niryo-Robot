# Getting Started with Niryo NED Robot

This guide will help you set up and connect to your Niryo NED robot using different connection methods.

## Prerequisites

- Niryo NED robot
- Niryo Studio software (download from [Niryo website](https://niryo.com))
- Computer with WiFi capability
- Power supply for the robot

## Connection Methods

There are two primary wireless connection methods for the Niryo NED robot:

### 1. Hotspot Mode (Easiest)

**Description:** The robot creates its own WiFi network that you can connect to directly.

**Steps:**
1. Power on your Niryo NED robot
2. Wait for the LED ring on the back panel to turn **blue** (this indicates hotspot mode is active)
3. On your computer, open WiFi settings
4. Look for a network named **"Niryo Hotspot XX-XXX-XXX"** (where XX-XXX-XXX is your robot's unique ID)
5. Connect to this network using the password: **niryorobot**
6. Open Niryo Studio and click "Connect Robot"
7. Select "Hotspot" as the connection method
8. Enter the IP address: **10.10.10.10**

**Advantages:**
- Easy setup, no configuration required
- No cables needed
- Works anywhere without existing WiFi infrastructure

**Limitations:**
- Your computer will lose internet access while connected to the robot's hotspot
- The robot itself has no internet access and cannot update itself
- Limited range (typically 10-20 meters)

---

### 2. WiFi Mode (Connected Mode)

**Description:** The robot connects to your existing WiFi network, allowing both your computer and robot to access the internet.

**Steps:**
1. First, connect to your robot using Hotspot Mode (see above)
2. In Niryo Studio, go to **Robot Settings** → **Network Configuration**
3. Enter your WiFi network name (SSID) and password
4. Click "Connect Robot to WiFi"
5. The robot will reboot - wait for the LED ring to turn **green** (this indicates successful WiFi connection)
6. On your computer, connect to the same WiFi network
7. In Niryo Studio, click "Connect Robot"
8. Use the "WiFi + Search" button to find your robot on the network
9. Select your robot and connect

**Advantages:**
- Both computer and robot have internet access
- Can update robot firmware remotely
- Better range and stability (depending on your WiFi network)

**Limitations:**
- Requires initial hotspot connection for setup
- Depends on your WiFi network's stability
- IP address may change if not configured statically

---

## LED Status Indicators

The LED ring on the back of your Niryo NED indicates the robot's status:

| LED Color | Status |
|-----------|--------|
| **Blue** | Hotspot mode active - ready for direct connection |
| **Green** | Connected to WiFi network - ready for use |
| **Red** | Error or booting up |
| **Yellow/Orange** | Warning or calibration needed |

---

## Troubleshooting

### Cannot find the hotspot network
- Ensure the robot is powered on and has been booting for at least 2 minutes
- Check that the LED ring is blue
- Move closer to the robot (within 5 meters)
- Restart the robot if the LED is not blue

### WiFi connection fails
- Double-check your WiFi SSID and password (case-sensitive)
- Ensure your WiFi network is 2.4GHz (Niryo NED does not support 5GHz)
- Check that the robot is within range of your WiFi router
- Verify your router's firewall is not blocking the connection

### Robot not found in Niryo Studio
- Ensure your computer is on the same network as the robot
- Try using the "WiFi + Search" feature to scan for robots
- Check if your firewall is blocking Niryo Studio
- Restart Niryo Studio and try again

### IP address issues
- Hotspot mode always uses: **10.10.10.10**
- WiFi mode: IP depends on your router's DHCP settings
- You can set a static IP in Niryo Studio under Robot Settings

---

## SSH Access (Advanced Users)

For advanced users, you can access the robot via SSH:

```bash
ssh niryo@<robot_ip>
```

Default credentials:
- Username: **niryo**
- Password: **robotics**

---

## Additional Resources

- [Niryo Documentation](https://docs.niryo.com)
- [Niryo Academy](https://academy.niryo.com)
- [Niryo Studio Download](https://niryo.com/download)
- [ROS Stack Documentation](https://niryorobotics.github.io/ned_ros/)

---

## Next Steps

Once connected, you can:
1. Calibrate the robot using Niryo Studio
2. Program movements using theBlockly interface
3. Use Python API for custom scripts
4. Integrate with ROS for advanced applications

For more detailed instructions, refer to the official Niryo documentation at [docs.niryo.com](https://docs.niryo.com).
