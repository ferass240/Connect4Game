import cv2

# Open the webcam
cap = cv2.VideoCapture(0)
cap.set(3, 640)
cap.set(4, 480)
if not cap.isOpened():
    print("Error: Could not open camera.")
    exit()

while True:
    # Capture frame-by-frame
    ret, frame = cap.read()
    
    if not ret:
        print("Failed to grab frame.")
        break
    
    # Draw a green rectangle (100x70 pixels) on the frame
    start_point = (70, 80)  # Top-left corner (x, y)
    end_point = (560, 440)  # Bottom-right corner (x+100, y+70)
    color = (0, 255, 0)  # Green color in BGR
    thickness = 2  # Rectangle border thickness
    frame = cv2.rectangle(frame, start_point, end_point, color, thickness)
    
    # Display the resulting frame
    cv2.imshow("Webcam Feed", frame)

    # Wait for key press
    key = cv2.waitKey(1) & 0xFF

    # Capture the image when 's' key is pressed
    if key == ord('s'):
        # Save the captured frame as an image
        cv2.imwrite("captured_image.jpg", frame)
        print("Image captured and saved as 'captured_image.jpg'.")

    # Exit the loop when 'q' key is pressed
    if key == ord('q'):
        print("Exiting...")
        break

# Release the camera and close all OpenCV windows
cap.release()
cv2.destroyAllWindows()
