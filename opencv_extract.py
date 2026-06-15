import cv2
import os
from pathlib import Path


def extract_frames_from_time_range(
    video_path,
    start_time_seconds,
    duration=10,
    num_frames=4,
    output_dir="extracted_frames",
):
    """
    Extract frames from a specific time range in the video.

    Args:
        video_path: Path to the video file
        start_time_seconds: Where to start (in seconds)
        duration: Length of clip in seconds (default: 10)
        num_frames: Number of frames to extract (default: 4)
        output_dir: Directory to save frames
    """
    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Open video
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise Exception(f"Could not open video: {video_path}")

    # Get video properties
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Calculate frame positions
    start_frame = int(start_time_seconds * fps)
    end_frame = int((start_time_seconds + duration) * fps)
    end_frame = min(end_frame, total_frames)  # Don't exceed video length

    # Calculate evenly spaced frame indices within the 10-second range
    frame_indices = [
        int(
            start_frame
            + i * (end_frame - start_frame) / max(num_frames - 1, 1)
        )
        for i in range(num_frames)
    ]

    extracted_files = []

    for i, frame_idx in enumerate(frame_indices):
        # Set position to the specific frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()

        if ret:
            # Calculate timestamp for filename
            timestamp = frame_idx / fps
            output_path = os.path.join(
                output_dir, f"theo_frame_{i + 1}_{timestamp:.2f}s.jpg"
            )

            # Save frame
            cv2.imwrite(output_path, frame)
            extracted_files.append(
                {
                    "path": output_path,
                    "timestamp": timestamp,
                    "frame_number": frame_idx,
                }
            )
            print(f"✓ Saved: {output_path} (at {timestamp:.2f}s)")

    cap.release()
    return extracted_files


# Example usage for the Theo de Raadt video
if __name__ == "__main__":
    video_file = "theo_de_raadt_rubsd2013.mp4"  # Your downloaded video

    # Extract 4 frames from a 10-second clip starting at 2:30 (150 seconds)
    frames = extract_frames_from_time_range(
        video_path=video_file,
        start_time_seconds=150,  # Start at 2:30
        duration=10,  # 10-second clip
        num_frames=4,  # Extract 4 frames
        output_dir="theo_frames",
    )

    print(f"\nExtracted {len(frames)} frames successfully!")
