import time
from multiprocessing import shared_memory

# Define the shared memory name for the winner
WINNER_SHM_NAME = "/winner_shm"

def wait_for_shared_memory(name, timeout=10):
    """Wait for the shared memory block to be created."""
    start_time = time.time()
    while True:
        try:
            shm = shared_memory.SharedMemory(name='/winner_shm')
            shm.close()
            print("Shared memory winner found.")
            return
        except FileNotFoundError:
            if time.time() - start_time > timeout:
                raise TimeoutError("Shared memory not found within the timeout period.")
            time.sleep(0.1)

            
def monitor_winner():
    print("im inside monitor_winner function")
    """
    Continuously checks the shared memory for a winner and prints it when found.
    """
    
    shm = None
    try:
        while True:
            time.sleep(1)
            # Attach to the shared memory segment for the winner
            shm = shared_memory.SharedMemory(name=WINNER_SHM_NAME)
            
            # Read the winner value (assuming it's an integer stored in the first 4 bytes)
            winner_value = shm.buf[0]
            
            # If the winner value is not zero, print it and break the loop
            if winner_value != 255:
                print(f"We have a Winner: Player {winner_value}")
                break  # Exit the loop once the winner is found
            
            time.sleep(1)  # Wait for 1 second before checking again
    except FileNotFoundError:
        print(f"Shared memory {WINNER_SHM_NAME} not found. Waiting for it to be created...")
    except KeyboardInterrupt:
        print("\nProgram interrupted by user.")
    finally:
        # Ensure the shared memory is unlinked after use
        if shm:
            try:
                shm.close()  # Close shared memory
                shm.unlink()  # Unlink the shared memory
                print("Shared memory winner closed and unlinked.")
            except Exception as e:
                print(f"Error while cleaning up shared memory: {e}")
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
"""
    shm = None
    while True:
        try:
            time.sleep(1)
            # Attach to the shared memory segment for the winner
            shm = shared_memory.SharedMemory(name='/winner_shm')
            #print("Content of winner_shm:", bytes(shm.buf[:]).decode("utf-8"))
            # Read the winner value (assuming it's an integer stored in the first 4 bytes)
            winner_value = shm.buf[0]
            # If the winner value is not zero, print it and break the loop
            print(f"Winner: Player {winner_value}")
            if winner_value != 5:
                print(f"Winner: Player {winner_value}")
                shm.close()  # Close shared memory
                break  # Exit the loop once the winner is found

            shm.close()
            time.sleep(1)  # Wait for 1 second before checking again
        except FileNotFoundError:
            print(f"Shared memory {WINNER_SHM_NAME} not found. Waiting for it to be created...")
            time.sleep(1)  # Wait and check again
        except KeyboardInterrupt:
            print("\nProgram interrupted by user.")
        finally:
            print("Releasing wiiner shared memory.")
        # Ensure the shared memory is unlinked after use
            if shm:
                try:
                    shm.close()  # Close shared memory
                    shm.unlink()  # Unlink the shared memory
                    print("Shared memory closed and unlinked.")
                except Exception as e:
                    print(f"Error while cleaning up shared memory: {e}")
"""
if __name__ == "__main__":
    
    #shm = None  # Initialize shared memory reference
    wait_for_shared_memory('winner_shm', timeout=10)
    #shm = shared_memory.SharedMemory(name='/winner_shm')
    monitor_winner()  # Start monitoring for winner

