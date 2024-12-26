import RPi.GPIO as GPIO # Import Raspberry Pi GPIO library
import time
import os
import sys
import subprocess 
import signal 
# Pin setup
GPIO.setmode(GPIO.BCM)  # Use BCM GPIO numbering
GPIO.setup(22, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)  # Set pin 15 as input with pull-down resistor
GPIO.setup(23, GPIO.OUT)
game_process = None  # Store the game process reference
new_disc_process = None  # Store the new_disc.py monitoring process
def flash_led_continuously(timeout=5):
    """Flash the LED continuously until the second press is detected or timeout occurs."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if GPIO.input(22) == GPIO.HIGH:  # Detect second press
            return True  # Break the flashing loop and indicate second press detected
        GPIO.output(23, GPIO.HIGH)  # Turn on the LED
        time.sleep(0.5)  # Wait for 0.5 seconds
        GPIO.output(23, GPIO.LOW)   # Turn off the LED
        time.sleep(0.5)  # Wait for 0.5 seconds
    return False  # Tim
def cleanup_gpio():
    GPIO.cleanup()
    exit(0)
     
def start_new_disc_monitor():
    """Start the new_disc.py monitoring process."""
    global new_disc_process
    new_disc_process = subprocess.Popen(["python3", "new_disc_firas2.py"])
    
# Define the function to start the game
def start_game_mode():
    global game_process  # Use the global game_process reference
    print("First button press detected. Monitoring for second press for 5 seconds...")
    # When the second press occurs, keep the LED on
    # Flash the LED continuously and monitor for a second press
    second_press_detected = flash_led_continuously(timeout=5)
    GPIO.output(23, GPIO.HIGH)  # Keep LED on (set GPIO 17 HIGH)
    
    
    if second_press_detected:
        print("Second button press detected! Starting Human vs. AI mode...")
        os.system("echo 1 > game_mode.txt")  # Indicate Human vs. AI mode
        # Run the game in the background by calling the game function in a separate thread
        game_process = subprocess.Popen(["python3", "monitor_bot_move.py"])  # Run the game in the background
        start_new_disc_monitor()
        game_process.wait()  # Wait for the game to finish
    else:
        print("Timeout! Starting AI vs. Human mode...")
        os.system("echo 2 > game_mode.txt")  # Indicate AI vs. Human mode
        # Run the game in the background by calling the game function in a separate thread
        game_process = subprocess.Popen(["python3", "monitor_bot_move.py"])  # Run the game in the background
        start_new_disc_monitor()
        game_process.wait() 
    
# Callback for stop button on GPIO 23
def stop_program(channel):
    global game_process  # Access the global game_process reference
    print("Stop button pressed! Exiting program...")
    GPIO.output(23, GPIO.LOW)
    if game_process is not None:
        # Send SIGTERM signal to the game process to terminate it
        os.kill(game_process.pid, signal.SIGTERM)
        print("Game process terminated.")
    
    GPIO.cleanup()  # Clean up GPIO settings
    sys.exit(0)  # Exit the prog
# Add event detection
def button_callback(channel):
    start_game_mode()
    
GPIO.add_event_detect(22,GPIO.RISING,callback=button_callback, bouncetime=400) # Setup event on pin 10 rising edge
# Keep the program running
try:
    print("Waiting for button presses...")
    while True:
        time.sleep(0.1)  # Prevent excessive CPU usage
except KeyboardInterrupt:
    GPIO.cleanup()
