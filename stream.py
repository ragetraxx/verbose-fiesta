import os
import json
import subprocess
import time

# ✅ Configuration
PLAY_FILE = "play.json"
RTMP_URL = os.getenv("RTMP_URL")
OVERLAY = os.path.abspath("overlay.png")
FONT_PATH = os.path.abspath("Roboto-Black.ttf")
RETRY_DELAY = 60

# ✅ Sanity Checks
if not RTMP_URL:
    print("❌ ERROR: RTMP_URL is not set!")
    exit(1)

for path, name in [(PLAY_FILE, "Playlist JSON"), (OVERLAY, "Overlay Image"), (FONT_PATH, "Font File")]:
    if not os.path.exists(path):
        print(f"❌ ERROR: {name} '{path}' not found!")
        exit(1)

def load_movies():
    try:
        with open(PLAY_FILE, "r") as f:
            return json.load(f) or []
    except Exception as e:
        print(f"❌ Failed to load {PLAY_FILE}: {e}")
        return []

def escape_drawtext(text):
    return text.replace('\\', '\\\\\\\\').replace(':', '\\:').replace("'", "\\'")

def build_ffmpeg_command(movie):
    title = movie.get("title", "Untitled")
    url = movie.get("url")
    text = escape_drawtext(title)

    # ✅ Network input options (compatible with direct MP4, MKV, M3U8, HLS streams)
    input_options = [
        "-reconnect", "1",
        "-reconnect_at_eof", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
        "-analyzeduration", "10000000",
        "-probesize", "10000000",
        "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
    ]

    # ✅ Optional: Dynamically attach custom referer/headers if specified in play.json entry
    referer = movie.get("referer")
    custom_headers = movie.get("headers")
    header_str = ""
    if referer:
        header_str += f"Referer: {referer}\r\n"
    if custom_headers:
        header_str += f"{custom_headers}\r\n"
    if header_str:
        input_options.extend(["-headers", header_str])

    return [
        "ffmpeg",
        "-re",                           # ✅ Fixed: -re MUST be placed before input (-i)
        "-fflags", "+genpts+discardcorrupt",
        *input_options,
        "-thread_queue_size", "4096",    # Input buffer to absorb network latency spikes
        "-i", url,
        "-thread_queue_size", "1024",
        "-i", OVERLAY,
        "-filter_complex",
        f"[0:v]scale=1280:720:flags=bicubic[v];"
        f"[1:v]scale=1280:720[ol];"
        f"[v][ol]overlay=0:0[vo];"
        f"[vo]drawtext=fontfile='{FONT_PATH}':text='{text}':fontcolor=white:fontsize=20:x=35:y=35",
        "-r", "29.97",
        "-c:v", "libx264",
        "-preset", "veryfast",           # Fast, efficient H.264 encoding
        "-g", "60",                      # Fixed 2-second keyframe interval
        "-keyint_min", "60",
        "-sc_threshold", "0",
        "-b:v", "2500k",                 # Stable target bitrate
        "-maxrate", "3000k",
        "-bufsize", "3000k",             # 2-second rate control buffer
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "48000",
        "-ac", "2",
        "-af", "aresample=async=1",      # Keeps audio tightly synchronized with video
        "-f", "flv",
        RTMP_URL
    ]

def stream_movie(movie):
    title = movie.get("title", "Untitled")
    url = movie.get("url")

    if not url:
        print(f"❌ Skipping '{title}': no URL")
        return

    print(f"🎬 Now streaming: {title}")
    command = build_ffmpeg_command(movie)

    try:
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        for line in process.stderr:
            if "403 Forbidden" in line or "404 Not Found" in line or "Server returned 404" in line:
                print(f"🚫 Stream URL error (403/404)! Skipping: {title}")
                process.kill()
                return
            print(line.strip())
        process.wait()  # ✅ Waits for the full video to finish playing
    except Exception as e:
        print(f"❌ FFmpeg crashed: {e}")

def main():
    while True:
        movies = load_movies()
        if not movies:
            print(f"📂 No entries in {PLAY_FILE}. Retrying in {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)
            continue

        for movie in movies:
            stream_movie(movie)
            print("⏭️  Next movie in 5s...")
            time.sleep(5)

if __name__ == "__main__":
    main()
