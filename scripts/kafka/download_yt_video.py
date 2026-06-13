import subprocess
import sys

def download_1_trailer(trailer_id):
    url = "https://www.youtube.com/watch?v=" + trailer_id
    output = "trailer/" + trailer_id + ".mp4"
    cmd = [
        "yt-dlp",
        "--quiet",
        "--no-warnings",
        "--force-overwrites",
        "--download-sections", "*00:00:30-00:01:00",
        "--force-keyframes-at-cuts",
        "-f", "bv*[width=1280]",
        "--merge-output-format", "mp4",
        "-o", output,
        url
    ]
    subprocess.run(cmd, check=True)
    print('Finish downloading: ' + trailer_id)

if __name__ == "__main__":
    #take trailer ids as command line argument and download the trailers
    args = sys.argv[1:]
    print(args)
    for trailer_id in args: 
        download_1_trailer(trailer_id)