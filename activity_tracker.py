import threading
import time
import pyautogui
from PIL import Image, ImageFilter
from pynput.mouse import Listener as MouseListener
from pynput.keyboard import Listener as KeyboardListener
import math
import json
import os
from dotenv import load_dotenv
from datetime import datetime
from tzlocal import get_localzone
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
from botocore.client import Config
import gzip

class ConfigManager:
    def __init__(self, config_path):
        self.config_path = config_path
        self.load_config()

    def load_config(self):
        try:
            with open(self.config_path, 'r') as config_file:
                self.config = json.load(config_file)
        except FileNotFoundError:
            self.config = {}
            self.save_config()

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save_config()

    def save_config(self):
        with open(self.config_path, 'w') as config_file:
            json.dump(self.config, config_file, indent=4)

class DataManager:
    def __init__(self):
        self.timezone = get_localzone()  # Default to the local timezone
        
        load_dotenv()
        aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        self.bucket_name = os.getenv('S3_BUCKET_NAME')
        
        # Check for credentials
        if not aws_access_key or not aws_secret_key or not self.bucket_name:
            raise ValueError("AWS credentials or S3 bucket name not set. Check environment variables.")
        
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            config=Config(signature_version='s3v4')
        )
        
        self.upload_queue = []  

    def update_timezone(self):
        self.timezone = get_localzone()  # Update to the current timezone

    def save_screenshot(self, screenshot):
        """Save the screenshot to disk and upload to S3 with timezone-aware timestamp."""
        timestamp = datetime.now(self.timezone).strftime("%Y%m%d_%H%M%S")
        screenshot_path = f"screenshot_{timestamp}.png"
        
        # Resize screenshot to reduce size (optional)
        screenshot = screenshot.resize((800, 600), Image.Resampling.LANCZOS)  

        screenshot.save(screenshot_path)
        print(f"Screenshot saved: {screenshot_path}")

        self.upload_queue.append(screenshot_path)
        self.upload_to_s3()

    def log_scripted_activity(self, activity_type):
        """Log detected scripted activity with timezone-aware timestamp."""
        timestamp = datetime.now(self.timezone).strftime("%Y-%m-%d %H-%M-%S %Z")
        log_message = f"{timestamp} - Suspicious {activity_type} detected and flagged!"
        print(log_message)

        log_filename_timestamp = datetime.now(self.timezone).strftime("%Y%m%d_%H%M%S")
        log_path = f"log_{log_filename_timestamp}.txt"
        
        with open(log_path, 'w') as log_file:
            log_file.write(log_message)

        self.upload_queue.append(log_path)
        self.upload_to_s3()

    def upload_to_s3(self):
        """Upload files from the queue to S3 with chunked upload and encryption."""
        while self.upload_queue:
            file_path = self.upload_queue.pop(0)  # Get the next file in the queue
            try:
                with open(file_path, 'rb') as file:
                    file_data = file.read()
                    compressed_data = gzip.compress(file_data)  # Compress the data
                    s3_key = f"uploads/{os.path.basename(file_path)}"
                    self.s3_client.put_object(
                        Bucket=self.bucket_name,
                        Key=s3_key,
                        Body=compressed_data,
                        ContentEncoding='gzip',
                        ServerSideEncryption='AES256' 
                    )
                    print(f"Uploaded {file_path} to S3 as {s3_key}")

                os.remove(file_path)  # Remove local file after successful upload

            except FileNotFoundError:
                print(f"The file {file_path} was not found.")
            except NoCredentialsError:
                print("AWS credentials not available.")
                self.upload_queue.append(file_path)  # Re-add to queue for retry
                time.sleep(10)  # Wait before retrying
            except PartialCredentialsError:
                print("Incomplete AWS credentials.")
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == 'NetworkConnectionError':
                    print("No internet connection. Queuing upload.")
                    self.upload_queue.append(file_path)  # Re-add to queue for retry
                    time.sleep(10)  # Wait before retrying
                else:
                    print(f"Client error occurred: {e}")
                    os.remove(file_path)  # Remove the file if not recoverable
            except Exception as e:
                print(f"Unexpected error occurred: {e}")
                self.upload_queue.append(file_path)  # Re-add to queue for retry
                time.sleep(10)  # Wait before retrying

class ActivityTracker:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.data_manager = DataManager()
        self.running = True
        self.prev_mouse_position = None
        self.prev_mouse_time = None
        self.prev_key_time = None
        self.key_timing_diffs = []

    def start(self):
        self.tracking_thread = threading.Thread(target=self.track_activity)
        self.scripted_activity_thread = threading.Thread(target=self.detect_and_handle_activity)
        self.config_polling_thread = threading.Thread(target=self.poll_config_updates)
        self.timezone_check_thread = threading.Thread(target=self.check_for_timezone_changes)
        
        self.tracking_thread.start()
        self.scripted_activity_thread.start()
        self.config_polling_thread.start()
        self.timezone_check_thread.start()

        self.mouse_listener = MouseListener(on_move=self.on_move)
        self.keyboard_listener = KeyboardListener(on_press=self.on_press)
        self.mouse_listener.start()
        self.keyboard_listener.start()

    def track_activity(self):
        while self.running:
            screenshot_interval = self.config_manager.get('screenshot_interval', 300)
            capture_screenshots = self.config_manager.get('capture_screenshots', True)
            blur_screenshots = self.config_manager.get('blur_screenshots', False)

            if capture_screenshots:
                screenshot = pyautogui.screenshot()

                if blur_screenshots:
                    screenshot = screenshot.filter(ImageFilter.GaussianBlur(15))

                self.data_manager.save_screenshot(screenshot)

            time.sleep(screenshot_interval)

    def stop(self):
        self.running = False
        self.tracking_thread.join()
        self.scripted_activity_thread.join()
        self.config_polling_thread.join()
        self.timezone_check_thread.join()
        self.mouse_listener.stop()
        self.keyboard_listener.stop()

    def detect_and_handle_activity(self):
        while self.running:
            time.sleep(1)  

    def on_move(self, x, y):
        self.detect_scripted_mouse_movement(x, y)

    def detect_scripted_mouse_movement(self, x, y):
        current_time = time.time()
        
        if self.prev_mouse_position is not None and self.prev_mouse_time is not None:
            dx = x - self.prev_mouse_position[0]
            dy = y - self.prev_mouse_position[1]
            distance = math.sqrt(dx**2 + dy**2)
            time_diff = current_time - self.prev_mouse_time
            
            if time_diff > 0:
                speed = distance / time_diff
                print(f"Mouse speed: {speed:.2f} pixels/sec")

                if speed > 1000:  # Set the threshold for mouse speed in pixels/sec
                    self.data_manager.log_scripted_activity("mouse movement")

        self.prev_mouse_position = (x, y)
        self.prev_mouse_time = current_time

    def on_press(self, key):
        self.detect_scripted_keyboard_input()

    def detect_scripted_keyboard_input(self):
        current_time = time.time()

        if self.prev_key_time is not None:
            time_diff = current_time - self.prev_key_time
            self.key_timing_diffs.append(time_diff)

            if len(self.key_timing_diffs) >= 5:  # Check the last 5 key presses
                timing_deviation = max(self.key_timing_diffs) - min(self.key_timing_diffs)
                print(f"Keyboard timing deviation: {timing_deviation:.3f} sec")

                if timing_deviation < 0.05: 
                    self.data_manager.log_scripted_activity("keyboard input")

                self.key_timing_diffs.clear()

        self.prev_key_time = current_time

    def poll_config_updates(self):
        while self.running:
            self.config_manager.load_config()  # Fetch and apply new config from the local file
            time.sleep(10)  # Poll every 10 seconds (adjust as needed)

    def check_for_timezone_changes(self):
        prev_timezone = get_localzone()
        while self.running:
            current_timezone = get_localzone()
            if current_timezone != prev_timezone:
                self.data_manager.update_timezone()  # Update the DataManager with the new timezone
                prev_timezone = current_timezone
                print(f"Timezone changed to: {current_timezone}")
            time.sleep(60) 

# Example path to the local configuration file
config_path = "config.json"

if __name__ == "__main__":
    config_manager = ConfigManager(config_path)
    tracker = ActivityTracker(config_manager)
    
    try:
        tracker.start()
        while True:
            time.sleep(1)  
    except KeyboardInterrupt:
        tracker.stop()
        print("Activity tracker stopped.")
