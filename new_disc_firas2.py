import cv2
import numpy as np
import time
from collections import deque
import warnings
from multiprocessing import shared_memory
import struct
num_columns = 7
# Define ROI coordinates (adjust based on camera position)
x_start, y_start = 75, 90
x_end, y_end = 550, 450


# shared memory init
shm_name = "/new_disc_shared_memory"
shm_size = 8

def video_capture():
    cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
    #cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    #cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    cap.set(3, 640)
    cap.set(4, 480)
    return cap


def detect_circles(image, image_height):
    # Convert the image to HSV
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # Define color range for yellow
    
    lower_yellow = np.array([15, 100, 100])
    upper_yellow = np.array([45, 255, 255])
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))


    # Create mask for yellow
    mask_yellow = cv2.inRange(hsv, lower_yellow, upper_yellow)
    mask_yellow = cv2.morphologyEx(mask_yellow, cv2.MORPH_CLOSE, kernel)
    mask_yellow = cv2.morphologyEx(mask_yellow, cv2.MORPH_OPEN, kernel)
    #cv2.imshow("Yellow Mask", mask_yellow)
    # Blur the mask to reduce noise
    blurred = cv2.GaussianBlur(mask_yellow, (15, 15), 0)

    # Detect circles using HoughCircles
    circles = cv2.HoughCircles(blurred, cv2.HOUGH_GRADIENT, dp=1, minDist=30,
                               param1=50, param2=30, minRadius=20, maxRadius=50)

    #cv2.destroyAllWindows()
    detected_circles = []
    if circles is not None:
        circles = np.round(circles[0, :]).astype("int")
        for (x, y, r) in circles:
            y = image_height - y
            # Determine the color of the circle
            if mask_yellow[y, x] > 0:
                color = "yellow"
                #cv2.circle(image, (x, y), r, (0, 255, 255), 4)  # Yellow in BGR
            else:
                color = "unknown"

            detected_circles.append((x, y, r, color))
    #else:
        #print("No circles were detected in this image.")  # Print a message when no circles are found

    return detected_circles

def find_new_disc(circles1, circles2):
    """Find the new disc by comparing two sets of detected circles."""
    new_disc = None
    circles1_set = set((x, y) for x, y, _, _ in circles1)

    for (x, y, r, color) in circles2:
        if (x, y) not in circles1_set:
            new_disc = (x, y, color)
            break
    return new_disc

def determine_column(x_coordinate, num_columns, image_width):
    """Determine the column based on the x-coordinate."""
    column_width = image_width / num_columns
    column = int(x_coordinate // column_width) + 1
    return column

def update_board_state(circles, image_width, num_columns):
    """Updates the board state based on the detected circles."""
    board_state = [None] * num_columns  # Keep track of filled columns
    column_width = image_width // num_columns

    # Iterate through detected circles
    for (x, y, r, color) in circles:
        column = determine_column(x, num_columns, image_width)
        
        # If the column is empty, set the current y position as the first filled position
        if board_state[column - 1] is None or y > board_state[column - 1]:
            board_state[column - 1] = y  # Update the column with the topmost filled spot
    
    return board_state

def display_board_state(board_state):
    """Prints out the current board state."""
    for col, state in enumerate(board_state, start=1):
        if state is None:
            print(f"Column {col}: Empty")
        else:
            print(f"Column {col}: Filled up to y={state}")

def compare_board_states(board_state1, board_state2):
    """Compare board states to find new discs."""
    new_discs = []
    for col in range(len(board_state1)):
        # If board_state2 has a new disc or is significantly different
        if board_state2[col] is not None:
            print("\nscol ", col+1)
            if board_state1[col] is None:
                new_discs.append(col + 1)  # Columns are 1-indexed
            elif board_state1[col] is not None and np.abs(board_state2[col] - board_state1[col]) > 20:
                new_discs.append(col + 1)  # Columns are 1-indexed 
    return new_discs
    


# Define history buffer size
history_size = 5
column_history = [deque([0] * history_size, maxlen=history_size) for _ in range(7)]

def stabilize_column_counts(columns_in_state):
    global column_history
    for i in range(num_columns):
        column_history[i].append(columns_in_state[i])
    # Calculate the average for each column
    smoothed_counts = [int(round(np.mean(column_history[i]))) for i in range(num_columns)]
    return smoothed_counts

def detect_new_disc(previous_board_state, current_stable_columns):
    for i in range(len(previous_board_state)):
        if current_stable_columns[i] == previous_board_state[i] + 1:
            return i + 1  # Return the 1-based index of the column
    return None  # Return None if no column increased

def write_to_txt(detected_column):
    with open("detected_disc.txt", "w") as file:
        file.write(f"{detected_column}\n")
    time.sleep(3)
    print(f"Written to file: {detected_column}")

def write_to_shared_memory(shm, detected_column):
    packed_data = struct.pack('i', detected_column) + struct.pack('i', 1)  # Value + Ready Flag
    shm.buf[:8] = packed_data
    print(f"Written to shared memory: {detected_column} (Ready)")
    time.sleep(2)
    shm.buf[4:8] = struct.pack('i', 0)  # Reset the flag

def main():
    cap = video_capture()
    columns_in_state = [0] * num_columns  # Initialize an empty list to store detected columns
    previous_board_state = [0] * num_columns
    print("Max Resolution: ", cap.get(cv2.CAP_PROP_FRAME_WIDTH), "x", cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    
    try:
        shm = shared_memory.SharedMemory(name=shm_name, create=True, size=shm_size)
        print(f"Shared memory '{shm_name}' created.")
    except FileExistsError:
        shm = shared_memory.SharedMemory(name=shm_name, create=False)
        print(f"Shared memory '{shm_name}' already exists. Attached to existing memory.")  
    try:
        while cap.isOpened():
            time.sleep(.5)
            ret, frame = cap.read()
            if not ret:
                print("Failed to capture video")
                break
            
            # Crop ROI from the frame
            live_cam = frame.copy()
            roi = frame[y_start:y_end, x_start:x_end]
            image_height, image_width = roi.shape[:2]
            
            circles = detect_circles(roi, image_height)
            for (x, y, r, color) in circles:
                y = image_height - y
                cv2.circle(roi, (x, y), r, (0, 0, 0), 4) 

                column = determine_column(x, num_columns, image_width)
                
                columns_in_state[column - 1] += 1
            
            stable_columns = stabilize_column_counts(columns_in_state)
            #print("Stabilized column counts:", stable_columns)

            new_disc_column = detect_new_disc(previous_board_state, stable_columns)
            if new_disc_column is not None:
                print(f"New disc detected in column: {new_disc_column}")
                #write_to_shared_memory(shm, new_disc_column)
                write_to_txt(new_disc_column)
                time.sleep(1)  # Simulate delay
            # Update the previous board state
                previous_board_state = stable_columns.copy()
           # else:
                #print("No new disc detected.")


            columns_in_state = [0] * num_columns
            cv2.imshow("Detected Circles", roi)
           
            
            # Display the live feed with ROI
            cv2.rectangle(live_cam, (70, 80), (560, 440), (0, 255, 0), 2)
            cv2.imshow("live cam", live_cam)
          

            # Exit condition
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        # Cleanup shared memory
    finally:
        shm.close()
        shm.unlink()
        print(f"Shared memory '{shm_name}' unlinked.")
        cap.release()
        cv2.destroyAllWindows()
        # Release resources
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
    
