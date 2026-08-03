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

# ✅ Header Configurations
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
REFERER = "https://www.imsa.com/"

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

    # ✅ Strict HTTP User-Agent & Referer configuration for HLS/CloudFront
    input_options = [
        "-user_agent", USER_AGENT,
        "-headers", f"Referer: {REFERER}\r\nUser-Agent: {USER_AGENT}\r\n",
        "-http_persistent", "0",            # Disable persistent HTTP connections to stop 502 Bad Gateways
        "-reconnect", "1",
        "-reconnect_at_eof", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "10",
        "-rw_timeout", "15000000",          # 15s timeout
        "-max_reload", "10"
    ]

    return [
        "ffmpeg",
        "-threads", "0",
        "-re",
        "-ss", str(PREBUFFER_SECONDS),
        *input_options,
        "-i", url,
        "-i", OVERLAY,
        "-filter_complex",
        f"[0:v]scale=1280:720:flags=bicubic[v];"
        f"[1:v]scale=1280:720[ol];"
        f"[v][ol]overlay=0:0[vo];"
        f"[vo]drawtext=fontfile='{FONT_PATH}':text='{text}':fontcolor=white:fontsize=20:x=35:y=35[outv]",
        "-map", "[outv]",
        "-map", "0:a?",
        "-r", "29.97",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-g", "60",
        "-keyint_min", "60",
        "-sc_threshold", "0",
        "-b:v", "4000k",
        "-maxrate", "5000k",
        "-bufsize", "10000k",
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
            if "404 Not Found" in line:
                print(f"⚠️ 404 Not Found! Segment/Playlist expired for: {title}")
                process.kill()
                return
            if "502 Bad Gateway" in line:
                print(f"⚠️ 502 Bad Gateway! CloudFront error for: {title}")
                process.kill()
                return
            if "403 Forbidden" in line:
                print(f"🚫 403 Forbidden! Referer/User-Agent rejected for: {title}")
                process.kill()
                return
            print(line.strip())
        process.wait()
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
