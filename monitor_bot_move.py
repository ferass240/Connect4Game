import time
import RPi.GPIO as GPIO
from multiprocessing import shared_memory
import sys
import os
import subprocess


WINNER_FILE = "winner.txt"



def cleanup(pin_map, shm=None, c_process=None):
    """Clean up GPIO pins, shared memory, and C program process."""
    GPIO.setmode(GPIO.BCM)  # Use BCM pin numbering
    GPIO.setwarnings(False)
    
    # Set all pins to LOW initially
    for pin in pin_map.values():
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
    for pin in pin_map.values():
        GPIO.output(pin, GPIO.LOW)
    
    GPIO.cleanup()
    
    if shm:
        # Reset shared memory to 255 (idle state)
        shm.buf[0] = 255
        shm.close()
        shm.unlink()  # Unlink shared memory to ensure it is removed
        print("Shared memory unlinked.")
    
    if c_process:
        c_process.terminate()
        c_process.wait()  # Ensure the process is fully terminated
        print("C program terminated.")

   
def read_winner_from_file():
    try:
        with open(WINNER_FILE, "r") as file:
            winner = file.read().strip()
            if winner:
                return int(winner)  # Return the winner as an integer (1 or 2)
            else:
                return None  # No winner yet
    except FileNotFoundError:
        print(f"{WINNER_FILE} not found.")
        return None 
    
def start_c_program():
    """Compile and run the C program."""
    #print("In function start_c_program")
    time.sleep(5)  # Delay to simulate some startup time
    c_program = "./connect4"
    c_source = "connect4.c"
    if not os.path.exists(c_program):
        print("C program not compiled. Compiling now...")
        compile_command = f"gcc -o {c_program} {c_source} -lm"
        result = subprocess.run(compile_command, shell=True)
        if result.returncode != 0:
            print("Compilation failed. Please check the C source code.")
            sys.exit(1)
    print("Starting C program...")
    return subprocess.Popen(c_program)

def monitor_bot_move():
    # Set up GPIO
    GPIO.setmode(GPIO.BCM)  # Use BCM pin numbering
    GPIO.setwarnings(False)
    
    # Map GPIO pins for binary output (0-7 needs 3 bits)
    pin_map = {
        0: 17,  # LSB
        1: 18,
        2: 27   # MSB
    }
    
    # Set all pins to LOW initially
    for pin in pin_map.values():
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

    # Start the C program
    print("Calling function start_c_program")
    c_process = start_c_program()
    
    time.sleep(1)

    shm = None  # Initialize shared memory reference
    
    try:
        # Attach to shared memory created by the C program
        shm = shared_memory.SharedMemory(name='/bot_move')  # Match the name in C code
        print("Shared memory attached.")
        last_move = None  # Track the last processed move
        
        #print("Monitoring bot moves...")
        while True:
            try:
                # Read the move from shared memory
                move = shm.buf[0]  # Shared memory buffer contains the move as a byte
        
                # Check if a move is valid and ready for processing
                if move != 255 and move != 0:
                    print(f"Bot's move: Binary {bin(move)[2:].zfill(3)}")
                    
                    if 0 <= move <= 7:  # Ensure the move is in range
                        # Update GPIO pins to represent the binary value
                        for bit_position, pin in pin_map.items():
                            # Extract the bit value (0 or 1) using bitwise operations
                            bit_value = (move >> bit_position) & 1
                            GPIO.output(pin, GPIO.HIGH if bit_value else GPIO.LOW)
                        time.sleep(1)
                        for pin in  pin_map.values():
                            GPIO.output(pin, GPIO.LOW)
                    else:
                        print("Move out of range (0-7).")
                    
                    # Signal the bot that the move has been processed by resetting shared memory
                    shm.buf[0] = 255  # Reset state to indicate ready for the next move
                else:
                    # Wait for a new move to be entered
                    time.sleep(0.1)
            except ValueError:
                print("Invalid value in shared memory. Expected a number between 0 and 7.")
            
    except FileNotFoundError:
        print("Shared memory not found. Ensure the C program is running.")
        
        cleanup(pin_map, shm, c_process)

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        cleanup(pin_map, shm, c_process)

    finally:
        # Cleanup GPIO and shared memory
        winner = read_winner_from_file()
        if winner is not None:
            print(f"The winner is player {winner}")
        else:
            print("Game over")
        
        cleanup(pin_map, shm, c_process)

if __name__ == "__main__":
    try:
        monitor_bot_move()
    except KeyboardInterrupt:
        print("\nProgram interrupted by user.")
        sys.exit(0)
        
        


