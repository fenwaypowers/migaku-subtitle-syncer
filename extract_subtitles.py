import argparse
import os
import subprocess
import json
import sys

VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv')

def get_subtitle_stream_id(file_path, lang_code):
    """Return the first subtitle stream ID (e.g., 0:3) matching the language."""
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 's',
            '-show_entries', 'stream=index:stream_tags=language',
            '-of', 'json', file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        for i, stream in enumerate(streams):
            tags = stream.get("tags", {})
            if tags.get("language", "").lower() == lang_code.lower():
                return f"0:{stream['index']}"
    except Exception as e:
        print(f"[ERROR] ffprobe failed on {file_path}: {e}")
    return None

def extract_subtitle(file_path, stream_id, lang_code):
    """Extract subtitle and convert to .srt"""
    srt_path = f"{os.path.splitext(file_path)[0]}.{lang_code}.srt"
    try:
        cmd = [
            'ffmpeg', '-y', '-i', file_path,
            '-map', stream_id,
            '-c:s', 'srt',
            srt_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if not os.path.exists(srt_path) or os.path.getsize(srt_path) == 0:
            raise RuntimeError("Subtitle file was not created or is empty.")

        return srt_path
    except Exception as e:
        print(f"[ERROR] Failed to extract subtitle from {file_path}: {e}")
        if os.path.exists(srt_path):
            os.remove(srt_path)
        print(f"[ALERT] Likely a picture-based or unsupported subtitle format.")
        return None

def process_directory(directory, lang_code):
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(VIDEO_EXTENSIONS):
                file_path = os.path.join(root, file)
                print(f"\nProcessing: {file_path}")
                stream_id = get_subtitle_stream_id(file_path, lang_code)
                if stream_id:
                    srt_file = extract_subtitle(file_path, stream_id, lang_code)
                    if srt_file:
                        print(f"✅ Extracted to: {srt_file}")
                else:
                    print(f"⚠️ No subtitles in language '{lang_code}' found in {file_path}")

def main():
    parser = argparse.ArgumentParser(description="Extract subtitle tracks by language.")
    parser.add_argument('--lang', required=True, help="Language code (e.g., eng, spa, jpn)")
    parser.add_argument('--dir', default='.', help="Directory to scan for videos (default: current)")
    args = parser.parse_args()

    if not os.path.isdir(args.dir):
        print(f"[ERROR] Directory does not exist: {args.dir}")
        sys.exit(1)

    process_directory(args.dir, args.lang)

if __name__ == "__main__":
    main()
