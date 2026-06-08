import sqlite3
import os

# 1. Connect to your RAG database
conn = sqlite3.connect('imperium_archive.db')
cursor = conn.cursor()

# 2. Create the video_frames table if it doesn't exist
cursor.execute('''
CREATE TABLE IF NOT EXISTS video_frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER,
    frame_path TEXT,
    timestamp_sec REAL
)
''')

# 3. Find the ID of the newly processed MP3 in your main documents table
# (Adjust 'documents' and 'filename' to match your actual schema if needed)
source_file = 'theo_rubsd2013.mp3'
cursor.execute(
    "SELECT id FROM documents WHERE filename = ? OR title LIKE ?",
    (source_file,
     '%theo%'))
result = cursor.fetchone()

if result:
    doc_id = result[0]
    print(f"Found document ID: {doc_id}")

    # 4. Insert the 4 frames into the new table
    frames_dir = 'static/images/theo_rubsd2013_frames'
    timestamps = [121.2, 123.8, 126.2, 128.8]

    for i in range(1, 5):
        frame_path = f"{frames_dir}/frame_{i}.jpg"
        if os.path.exists(frame_path):
            cursor.execute('''
                INSERT INTO video_frames (document_id, frame_path, timestamp_sec)
                VALUES (?, ?, ?)
            ''', (doc_id, frame_path, timestamps[i - 1]))

    conn.commit()
    print(f"Successfully linked 4 frames to document ID {doc_id}!")
else:
    print(
        f"Could not find {source_file} in the database yet. Run your MP3 transcription first!")

conn.close()
