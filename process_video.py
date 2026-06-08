import subprocess
import os

# The exact file yt-dlp created
video_file = "Theo de Raadt (ruBSD 2013) [OXS8ljif9b8].mkv"
base_name = "theo_rubsd2013"

# 1. Extract Audio (MP3) for your existing RAG pipeline
print("Extracting audio...")
subprocess.run([
    'ffmpeg', '-i', video_file, 
    '-map', '0:a', '-c:a', 'libmp3lame', '-q:a', '2', 
    f'{base_name}.mp3', '-y'
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(f"✓ Saved {base_name}.mp3")

# 2. Extract 4 frames from a 10-second clip (02:00 to 02:10)
start_time = 120 # Start at 2 minutes (120 seconds)
duration = 10
num_frames = 4
interval = duration / num_frames

os.makedirs(f"{base_name}_frames", exist_ok=True)

print("Extracting frames...")
for i in range(num_frames):
    # Calculate the exact middle of each interval
    timestamp = start_time + (i * interval) + (interval / 2)
    output_path = f"{base_name}_frames/frame_{i+1}.jpg"
    
    # -ss before -i makes it incredibly fast (input seeking)
    subprocess.run([
        'ffmpeg', '-ss', str(timestamp), 
        '-i', video_file, 
        '-frames:v', '1', '-q:v', '2', # High quality JPEG
        output_path, '-y'
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    print(f"✓ Saved {output_path} (at {timestamp:.1f}s)")

print("\nProcessing complete!")
