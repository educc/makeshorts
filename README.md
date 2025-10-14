# make_shorts.py

A Python CLI tool that extracts multiple ranges from a source video and concatenates them into a single vertical (phone-ratio) MP4 suitable for YouTube Shorts.

## Requirements

- Python 3.9+
- ffmpeg and ffprobe installed and available in PATH

### Installing Python

**macOS:**

Install pyenv using Homebrew:
```bash
brew install pyenv
```

Add pyenv to your shell (assuming zsh):
```bash
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.zshrc
echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.zshrc
echo 'eval "$(pyenv init -)"' >> ~/.zshrc
```

Restart your terminal or run `source ~/.zshrc`.

Install Python 3.13.7:
```bash
pyenv install 3.13.7
pyenv global 3.13.7
```

**Linux (Ubuntu/Debian):**

Install required dependencies:
```bash
sudo apt update
sudo apt install -y build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev curl libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev
```

Install pyenv:
```bash
curl https://pyenv.run | bash
```

Add pyenv to your shell (assuming bash):
```bash
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
```

Restart your terminal or run `source ~/.bashrc`.

Install Python 3.13.7:
```bash
pyenv install 3.13.7
pyenv global 3.13.7
```

**Windows:**

Install pyenv-win using Chocolatey:
```bash
choco install pyenv-win
```

Alternatively, download and install from https://github.com/pyenv-win/pyenv-win.

Install Python 3.13.7:
```bash
pyenv install 3.13.7
pyenv global 3.13.7
```

### Setting up Virtual Environment

Create and activate a virtual environment:
```bash
python -m venv .venv
```

Activate the virtual environment:
- **macOS/Linux:** `source .venv/bin/activate`
- **Windows:** `.venv\Scripts\activate`

### Installing Dependencies

Install the required Python packages:
```bash
pip install -r requirements.txt
```

### Installing ffmpeg

**macOS (using Homebrew):**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install ffmpeg
```

**Windows:**
Download from https://ffmpeg.org/download.html or use chocolatey:
```bash
choco install ffmpeg
```

## Usage

### Basic Usage

Extract two clips and concatenate them:
```bash
python make_shorts.py input.mp4 00:00:10 00:00:30 00:05:00 00:05:20
```

Using seconds instead of HH:MM:SS format:
```bash
python make_shorts.py input.mp4 10 30 300 320
```

### Advanced Usage

Specify custom output file and resolution:
```bash
python make_shorts.py input.mp4 10 30 --output my_shorts.mp4 --resolution 720x1280
```

Use crop mode instead of padding:
```bash
python make_shorts.py input.mp4 10 30 --scale-mode crop
```

Preview the ffmpeg command without running:
```bash
python make_shorts.py input.mp4 10 30 --dry-run
```

Show verbose output during processing:
```bash
python make_shorts.py input.mp4 10 30 --verbose
```

Extract only audio and output as MP3:
```bash
python make_shorts.py input.mp4 10 30 --only-audio --output audio.mp3
```

Clamp times to video duration instead of failing:
```bash
python make_shorts.py input.mp4 10 30 500 600 --clamp
```

Limit total output duration:
```bash
python make_shorts.py input.mp4 10 30 300 320 --max-duration 30
```

## Command Line Options

### Positional Arguments
- `input_path` - Path to source video file (required)
- `time_tokens` - Start and end times in pairs (must be even number of tokens)

### Time Formats
- `HH:MM:SS[.ms]` format: `00:01:23.45`, `00:05:00`
- Seconds as number: `83.45`, `300`, `10`

### Output Options
- `-o, --output` - Output file path (default: `shorts.mp4`)
- `-r, --resolution` - Target WxH resolution (default: `1080x1920`)

### Scaling Options
- `--scale-mode` - How to fit source into target aspect ratio:
  - `pad` (default) - Scale and add black bars to preserve full frame
  - `crop` - Scale and crop to fill frame exactly
  - `stretch` - Stretch to exact dimensions (may distort)

### Encoding Options
- `--codec-v` - Video codec (default: `libx264`)
- `--crf` - Constant Rate Factor, lower = higher quality (default: `20`)
- `--preset` - Encoding speed preset (default: `medium`)
- `--codec-a` - Audio codec (default: `aac`)
- `--audio-bitrate` - Audio bitrate (default: `128k`)

### Behavior Options
- `--dry-run` - Print ffmpeg command without running
- `--verbose` - Stream ffmpeg output to console
- `--max-duration` - Cap final output length in seconds
- `--clamp` - Clamp start/end times to input duration instead of failing
- `--only-audio` - Extract only audio and output as MP3

## Examples

### Extract highlights from a long video:
```bash
python make_shorts.py lecture.mp4 00:05:30 00:06:00 00:15:45 00:16:15 00:42:10 00:42:40
```

### Create a short compilation with custom settings:
```bash
python make_shorts.py gameplay.mp4 30 45 120 135 300 315 \
  --output "best_moments.mp4" \
  --resolution 1080x1920 \
  --scale-mode crop \
  --crf 18 \
  --preset slow
```

### Preview command for a complex edit:
```bash
python make_shorts.py movie.mp4 600 630 1800 1830 3600 3630 \
  --scale-mode pad \
  --max-duration 60 \
  --dry-run
```

### Extract audio highlights as MP3:
```bash
python make_shorts.py podcast.mp4 00:05:30 00:06:00 00:15:45 00:16:15 \
  --only-audio \
  --output "podcast_highlights.mp3"
```

## Output Format

- **Aspect Ratio:** 9:16 (portrait) for video output
- **Default Resolution:** 1080x1920 for video output
- **Container:** MP4 with web-optimized flags for video, MP3 for audio-only
- **Video Codec:** H.264 (libx264) for video output
- **Audio Codec:** AAC (if source has audio) for video, MP3 for audio-only

## Error Handling

The script will fail with helpful error messages for:
- Odd number of time tokens
- Invalid time formats
- Start time >= end time
- Times outside video duration (unless `--clamp` is used)
- Missing input file
- ffmpeg/ffprobe not found

## Implementation Notes

- Uses ffmpeg's `filter_complex` for single-pass processing
- Automatically detects video duration and audio presence
- Preserves audio if present in source
- Handles video rotation metadata
- Warns about overlapping time ranges
- Skips zero-length clips with warning

## Testing

Test with the included example video:
```bash
python make_shorts.py examples/video.mp4 0 5 10 15 --output test_shorts.mp4
```
## Utils

To cut the large video.
```bash
ffmpeg -i video_raw.mp4 -ss 00:27:00 -c copy video.mp4
```

Burn subtitles to a video
```bash
ffmpeg -i input.mp4 -vf subtitles=subtitles.srt -c:a copy output.mp4
```