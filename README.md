Pi Kiosk Project

This project turns a Raspberry Pi into a configurable kiosk display. It runs Chromium in fullscreen mode and cycles through a list of websites during specified "on" hours. During "off" hours, it displays a single, different website.

All settings (URLs, times, rotation speed) can be managed from a simple web interface hosted on the Pi itself.

Files

kiosk_control.py: The main Python script that runs the kiosk. It reads the config, checks the time, and manages the Chromium process.

server.py: A Python Flask web server that hosts the web interface and provides API endpoints to read/write the configuration.

index.html: The frontend web interface (the main HTML file).

config.json: A JSON file that stores all the user-configurable settings.

static/style.css: A CSS file containing styles for the index.html web interface.

Setup Instructions

1. Hardware

A Raspberry Pi (3, 4, or 5 recommended)

Raspberry Pi OS (with desktop) installed and configured (Wi-Fi/Ethernet).

2. Install Dependencies

First, make sure your Pi is up-to-date:

sudo apt-get update
sudo apt-get upgrade



Then, install Chromium and Python dependencies:

# Install Chromium
sudo apt-get install chromium-browser -y

# Install required Python libraries
pip install Flask psutil



(Note: psutil is used to find and kill old Chromium processes safely.)

3. Run the Web Interface

To configure the kiosk, you must first run the web server.

# Navigate to the project directory
cd /path/to/pi-kiosk

# Run the server
python3 server.py



You will see output indicating the server is running on port 8080. You can now access the web interface from any other computer on the same network by visiting:

http://<your-pi-ip-address>:8080

(Find your Pi's IP address using the ifconfig or ip a command on the Pi).

4. Run the Kiosk Script

Once you have saved your configuration via the web interface, you can start the kiosk.

A. For Testing:
You can run the script directly from the terminal. This is good for checking for errors.

python3 kiosk_control.py



(Note: This will only work if you are in the Pi's desktop environment, not over SSH unless you configure the DISPLAY variable).

B. For Automatic Startup (Recommended):
You want the kiosk to start automatically when the Pi boots up. The easiest way is to edit the autostart file for the Pi's desktop session.

Create the autostart directory if it doesn't exist:

mkdir -p ~/.config/lxsession/LXDE-pi



Open the autostart file in a text editor:

nano ~/.config/lxsession/LXDE-pi/autostart



Add the following lines. Make sure to use the absolute path to your kiosk_control.py script.

@lxpanel --profile LXDE-pi
@pcmanfm --desktop --profile LXDE-pi
@xscreensaver -no-splash

# Disable screen blanking
@xset s noblank
@xset s off
@xset -dpms

# Run the kiosk script (replace with your actual path)
@python3 /home/pi/pi-kiosk/kiosk_control.py



Save the file (Ctrl+O, Enter) and exit (Ctrl+X).

Now, when you reboot your Raspberry Pi, it will load the desktop and automatically launch your kiosk script. The script will run in an infinite loop, managing Chromium based on the settings in your config.json.