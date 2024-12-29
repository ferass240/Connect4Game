import RPi.GPIO as GPIO # Import Raspberry Pi GPIO library
import time
import os
import sys
import subprocess 
import signal 
from multiprocessing import shared_memory
import tkinter as tk 
from tkinter import PhotoImage
from threading import Thread
# Define shared memory name
SHARED_MEMORY_NAME = "/game_mode_shm"
WINNER_SHM_NAME = "/winner_shm"
# Pin setup
GPIO.setmode(GPIO.BCM)  # Use BCM GPIO numbering
GPIO.setup(22, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)  
GPIO.setup(24, GPIO.IN, pull_up_down=GPIO.PUD_DOWN) 
GPIO.setup(23, GPIO.OUT)
game_window = None
countdown_label = None
# Initialize global variables
game_process = None
new_disc_process = None
winner_monitor_process = None


def draw_colored_circle(game_window, color):
    """
    Draw a green circle in the middle of the window to represent the AI starting.
    """
    # Create a canvas to draw on
    canvas = tk.Canvas(game_window, width=800, height=800)
    canvas.pack()
    #canvas.pack(expand=True)
    # Calculate the center of the window
    center_x = 400  # Width / 2
    center_y = 400  # Height / 2

    # Draw a green circle in the center
    canvas.create_oval(center_x - 150, center_y - 150, center_x + 150, center_y + 150, fill=color)




def wait_for_shared_memory(name, timeout=10):
    #Wait for the shared memory block to be created.
    start_time = time.time()
    while True:
        try:
            shm = shared_memory.SharedMemory(name)
            shm.close()
            print("Shared memory game mode found.")
            return
        except FileNotFoundError:
            if time.time() - start_time > timeout:
                raise TimeoutError("Shared memory not found within the timeout period.")
            time.sleep(0.1)
            
            
# Start monitoring winner in a separate thread or process
def start_winner_monitor():
    global winner_monitor_process
    """Start monitoring for winner in the background."""
    winner_monitor_process = subprocess.Popen(["python3", "monitor_winner.py"]) 
            
def start_new_disc_monitor():
    #Start the new_disc.py monitoring process.
    global new_disc_process
    new_disc_process = subprocess.Popen(["python3", "new_disc_firas2.py"])

def start_bot_monitor():
    #Start the monitor_bot_move.py monitoring process.
    global game_process 
    game_process = subprocess.Popen(["python3", "monitor_bot_move.py"])  # Run the game in the background


def cleanup_gpio():
    
    GPIO.cleanup()
    
    shm.close()
    shm.unlink()  # Remove shared memory
    
    shm_winner = shared_memory.SharedMemory(name=WINNER_SHM_NAME)
    if shm_winner:
        try:
            shm_winner.close()
            shm_winner.unlink()  # Unlink shared memory to ensure it is removed
            print("Shared memory winner unlinked.")
        except Exception as e:
            print(f"Error while cleaning up shared  memory: {e}")
    exit(0)
    


def flash_countdown_and_detect_second_press(countdown_label, gpio_pin, game_window):
    """
    Flash a countdown on the GUI while detecting a second button press on the specified GPIO pin.
    """
    # Load the image and add it to the GUI
    try:
        img = PhotoImage(file="~/Desktop/connect4-sewar-deleted/images/connect4_image.png")  # Replace with your image path
        image_label = tk.Label(game_window, image=img)
        image_label.pack(pady=10)
    except Exception as e:
        print(f"Error loading image: {e}")
    for i in range(10, 0, -1):  # Countdown from 10 to 1

        if GPIO.input(gpio_pin) == GPIO.HIGH:  # Check if the button is pressed again
            countdown_label.config(text="Human starting the game!")
            game_window.update()  # Update the GUI
            print("Second button press detected! Human starting the game.")
            image_label.destroy()
            return True  # Indicate the countdown was interrupted

        # Update the GUI with the countdown
        countdown_label.config(text=f"Starting in {i}...")
        
        game_window.update()

        # Flash the GPIO LED
        GPIO.output(23, GPIO.HIGH)
        time.sleep(0.5)
        GPIO.output(23, GPIO.LOW)
        time.sleep(0.5)

    # If no second press is detected
    countdown_label.config(text="AI starting the game!")
    game_window.update()
    image_label.destroy()
    print("Countdown completed. Proceeding with default game start.")
    return False









def start_game_gui():
    """
    Start the GUI window and handle the countdown with second press detection.
    """
    
    try:
        print("First button press detected. Monitoring for second press for 5 seconds...")
        # Create a new Tkinter window
        game_window = tk.Tk()
        game_window.title("Connect Four Game")

        # Set the window size
        game_window.geometry("800x800")
        #game_window.attributes('-fullscreen', True)  # Make it full scree

        # Add a label to display the game status
        countdown_label = tk.Label(game_window, text="Game Starting...", font=("Arial", 20))
        countdown_label.pack(pady=20)
        
        shm = shared_memory.SharedMemory(name='game_mode_shm', create=True, size=4)
        wait_for_shared_memory('game_mode_shm', timeout=10)
        
        # Flash the countdown and detect a second button press
        second_press_detected = flash_countdown_and_detect_second_press(countdown_label, gpio_pin=22, game_window=game_window)
        
        if second_press_detected:
            draw_colored_circle(game_window, "yellow")
            game_window.update()
            GPIO.output(23, GPIO.HIGH) 
            print("Second button press detected! Starting Human vs. AI mode...")
            # Handle human starting the game
            # Add further logic for human vs. AI mode
            # Add a label to display the game status
            print("Human vs. AI mode activated.")
            mode = 1  # Human vs. AIy
            shm.buf[:4] = mode.to_bytes(4, byteorder="little")   
            print(f"Game mode {mode} written to shared memory: {SHARED_MEMORY_NAME}")
            #os.system("echo 1 > game_mode.txt")  # Indicate Human vs. AI mode
            # Run the game in the background by calling the game function in a separate thread
            start_bot_monitor()
            start_new_disc_monitor()
            start_winner_monitor()
            game_process.wait()  # Wait for the game to finish
        else:
            draw_colored_circle(game_window, "green")
            game_window.update()
            GPIO.output(23, GPIO.HIGH)
            # Handle default game start
            # Add further logic for AI vs. Human mode
            print("AI vs. Human mode activated.")
            # Add a label to display the game status
            countdown_label = tk.Label(game_window, text="AI Starting...", font=("Arial", 20))
            countdown_label.pack(pady=20)
            mode = 2
            print("Timeout! Starting AI vs. Human mode...")
            # Write the game mode to the shared memory
            shm.buf[:4] = mode.to_bytes(4, byteorder="little")
            print(f"Game mode {mode} written to shared memory: {SHARED_MEMORY_NAME}")
            # Start the game GUI after the game mode is determined
            #start_game_gui()
            # Run the game in the background by calling the game function in a separate thread
            start_bot_monitor()
            start_new_disc_monitor()
            start_winner_monitor()
            game_process.wait() 
        # Start the Tkinter event loop
        game_window.mainloop()

        while True:
            pass  # Keep the script running and waiting for events
    except KeyboardInterrupt:
        print("Exiting program due to keyboard interrupt...")
        stop_program()
# Callback for stop button on GPIO 23
def stop_program(channel=None):
    global game_process  # Access the global game_process reference
    global new_disc_process
    global winner_monitor_process
    print("Stop button pressed! Exiting program...")
    # Turn off the GPIO pin 23 LED (if applicable)
    GPIO.output(23, GPIO.LOW)
    
    # Terminate the game process if running
    if game_process is not None:
        print("Terminating game process...")
        os.kill(game_process.pid, signal.SIGTERM)
        game_process = None  # Reset reference

    # Terminate the new disc monitor process if running
    if new_disc_process is not None:
        print("Terminating new disc monitor process...")
        os.kill(new_disc_process.pid, signal.SIGTERM)
        new_disc_process = None  # Reset reference

    # Terminate the winner monitor process if running
    if winner_monitor_process is not None:
        print("Terminating winner monitor process...")
        os.kill(winner_monitor_process.pid, signal.SIGTERM)
        winner_monitor_process = None  # Reset reference

    # Clean up GPIO settings
    print("Cleaning up GPIO settings...")
    GPIO.cleanup()

    # Exit the program and return to terminal
    print("Program terminated. Returning to terminal.")
    os._exit(0)


# Monitor the stop button in a separate thread
def monitor_stop_button():
    """
    Continuously monitor the stop button and trigger the stop_program function when pressed.
    """
    while True:
        if GPIO.input(23) == GPIO.HIGH:  # Assuming active low for the stop button
            stop_program()

    
GPIO.add_event_detect(22, GPIO.RISING, callback=lambda channel: start_game_gui(), bouncetime=400)
#GPIO.add_event_detect(22,GPIO.RISING,callback=button_callback, bouncetime=400) # Setup event on pin 10 rising edge
GPIO.add_event_detect(24, GPIO.RISING, callback=stop_program, bouncetime=400)
# Keep the program running
# Start monitoring the stop button in a separate thread
stop_button_thread = Thread(target=monitor_stop_button, daemon=True)
stop_button_thread.start()
    
    
if __name__ == "__main__":
    try:
        print("Waiting for button presses...")
        while True:
            time.sleep(0.1)  # Prevent excessive CPU usage
    except KeyboardInterrupt:
        GPIO.cleanup()
        

