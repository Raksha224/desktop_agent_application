# Advanced Activity Tracker

This Python script implements an advanced activity tracker designed to monitor and log user behavior on a computer, including mouse movements and keyboard inputs. The tracker captures screenshots at configurable intervals and uploads these screenshots, along with logs of detected suspicious activities, to an AWS S3 bucket for further analysis.

## Key Components

1. **ConfigManager Class**:
   - Manages configuration settings stored in a JSON file.
   - Allows dynamic fetching and updating of settings.

2. **DataManager Class**:
   - Handles AWS S3 connections using credentials from environment variables.
   - Validates credentials and sets up the S3 client with encrypted uploads and gzip compression.
   - Manages a queue of files (screenshots and logs) for S3 uploads with robust error handling and retry logic.
   - Updates timestamps with local timezone awareness.

3. **ActivityTracker Class**:
   - Monitors mouse movements and keyboard inputs using `pynput` library listeners.
   - Detects scripted activities by analyzing input speed and timing consistency.
   - Starts multiple threads to:
     - Track user activity.
     - Detect and handle scripted behavior.
     - Poll for configuration updates.
     - Check for timezone changes.
   - Captures screenshots with options to resize and blur for privacy.
   - Saves screenshots locally before uploading them to S3.
   - Utilizes threading for responsiveness and concurrent task execution.

## Scripted Activity Detection

1. **Mouse Movement**:
   - Calculates mouse speed to detect unnatural movements.
   - Flags movements if speed exceeds a defined threshold.

2. **Keyboard Input**:
   - Monitors timing consistency of key presses.
   - Detects suspiciously consistent intervals that may indicate automated input.

## Error Handling

- Comprehensive handling for AWS S3 operations, including:
  - Missing or incomplete credentials.
  - Network errors and unexpected exceptions.
- Logs errors and re-queues files for retry attempts in case of issues.

## User Configuration

- Provides a flexible mechanism for user configuration through a local JSON file.
- Allows customization of:
  - Screenshot intervals.
  - Feature toggles (e.g., enable/disable screenshot capture).
  - Thresholds for detecting scripted activities.

## Timezone Awareness

- Adjusts to changes in the system's timezone.
- Ensures accurate timestamps for logs and uploads.

## Usage

- The tracker runs indefinitely, capturing and uploading data until stopped by the user.
- Includes a graceful shutdown procedure to stop threads and release resources correctly.

## Applications

- Useful for monitoring user behavior in scenarios like:
  - Cybersecurity.
  - Fraud detection.
  - User behavior analysis in software testing.
