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
PREBUFFER_SECONDS = 5

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

def build_ffmpeg_command(url, title):
    text = escape_drawtext(title)

    # ✅ Network input options: enable HTTP auto-reconnect & spoof Chrome User-Agent
    input_options = [
        "-reconnect", "1",
        "-reconnect_at_eof", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
        "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "-headers", "Referer: https://screenify.fun\r\n"
    ]

    return [
        "ffmpeg",
        # ❌ REMOVED: -fflags +nobuffer and -flags low_delay (allows stable network reading)
        "-ss", str(PREBUFFER_SECONDS),
        *input_options,
        "-i", url,             # Works with mkv, mp4, avi, mov, m3u8, etc.
        "-i", OVERLAY,
        "-filter_complex",
        # ✅ Lightened scaling algorithm and removed unsharp filter to minimize CPU load
        f"[0:v]scale=1280:720:flags=bicubic[v];"
        f"[1:v]scale=1280:720[ol];"
        f"[v][ol]overlay=0:0[vo];"
        f"[vo]drawtext=fontfile='{FONT_PATH}':text='{text}':fontcolor=white:fontsize=20:x=35:y=35",
        "-r", "29.97",
        "-c:v", "libx264",
        "-preset", "veryfast",   # Keeps encoding fast while stabilizing video quality
        "-tune", "zerolatency",
        "-g", "60",              # Keyframe interval (every 2 seconds at 29.97 fps)
        "-keyint_min", "60",
        "-sc_threshold", "0",
        "-b:v", "3000k",
        "-maxrate", "3500k",
        "-bufsize", "7000k",     # 2-second VBR buffer prevents RTMP stream drops
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "48000",
        "-ac", "2",
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
    command = build_ffmpeg_command(url, title)

    try:
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        for line in process.stderr:
            if "403 Forbidden" in line:
                print(f"🚫 403 Forbidden! Skipping: {title}")
                process.kill()
                return
            print(line.strip())
        process.wait()  # ✅ Waits for full movie to finish
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
