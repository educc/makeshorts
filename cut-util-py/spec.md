# make_shorts.py — Specification

This document defines the requirements, CLI contract, ffmpeg recipes, implementation notes, test plan, and acceptance criteria for a Python script that extracts multiple ranges from a source video and concatenates them into a single vertical (phone-ratio) MP4 suitable for YouTube Shorts.

## Goal

Create a small, well-documented Python CLI tool that accepts an input video and any number of start/end pairs and produces a single portrait (9:16) MP4 containing the concatenated clips in the given order.

Minimum behavior:
- First positional argument: input video file path.
- Subsequent positional arguments: repeated start end pairs (time format: `HH:MM:SS[.ms]` or seconds as float/int).
- Output: one MP4 video re-encoded/cropped/padded to the target phone aspect ratio (default 1080x1920).

## CLI contract

Usage examples:

```
python make_shorts.py input.mp4 00:00:10 00:00:30 00:05:00 00:05:20
python make_shorts.py input.mp4 10 30 --output shorts.mp4 --resolution 1080x1920 --scale-mode pad --dry-run
```

Arguments and flags:
- Positional `input_path` (str) — path to source video (required).
- Positional `time_tokens`... — must be an even number of tokens; treated as start end start end ... in that order.

Options:
- `-o, --output` (default: `shorts.mp4`) — output file path.
- `-r, --resolution` (default: `1080x1920`) — target WxH (portrait) resolution.
- `--scale-mode` (choices: `pad`, `crop`, `stretch`; default `pad`) — how to fit source into target.
- `--codec-v` (default `libx264`), `--crf` (default `20`), `--preset` (default `medium`).
- `--codec-a` (default `aac`), `--audio-bitrate` (default `128k`).
- `--dry-run` — print the ffmpeg command(s) without running.
- `--verbose` — stream ffmpeg output.
- `--max-duration` — cap final output length (seconds).
- `--clamp` — clamp start/end to input duration instead of failing.

Behavioral contract (inputs/outputs/error modes):
- Input validation errors (odd number of time tokens, invalid time format, start >= end) should exit non-zero with a helpful message.
- If any range is outside the input duration and `--clamp` is not set, script fails with an error.
- If `--dry-run` is provided, script prints generated ffmpeg command(s) and exits 0.

## Time parsing and validation

- Acceptable formats:
	- `HH:MM:SS[.ms]` (e.g. `00:01:23.45`).
	- Plain seconds as integer or float (e.g. `83` or `83.45`).
- Convert tokens to float seconds for validation and to feed ffmpeg.
- Validate each range: `0 <= start < end <= duration` (or clamp if `--clamp`).
- Skip zero-length clips (emit a warning).

Use `ffprobe` (via subprocess) to read input duration, stream counts, and rotation metadata.

## Output aspect ratio, scaling rules and rotation handling

- Target aspect ratio: 9:16 (portrait). Default target resolution: `1080x1920` (WxH).
- `pad` mode (default): scale input with `force_original_aspect_ratio=decrease`, then pad to exact WxH. This preserves full frame and adds black bars.
- `crop` mode: scale with `force_original_aspect_ratio=increase`, then center-crop to WxH.
- `stretch` mode: scale directly to WxH (may distort image).
- Normalize rotation: detect rotation metadata with `ffprobe` and apply transpose or use `transpose`/`rotate` in the filter chain so the orientation is correct before scaling.

Standard per-clip video filter chain (pad mode) — conceptual:

scale=WIDTH:HEIGHT:force_original_aspect_ratio=decrease, pad=WIDTH:HEIGHT:(ow-iw)/2:(oh-ih)/2, setsar=1

Replace WIDTH/HEIGHT with the resolved target values from `--resolution`.

## Two recommended implementation approaches (developer choice)

1) Single-pass ffmpeg with `filter_complex` (recommended for simplicity & fewer temp files)

- For N segments:
	- Create N `trim`+`setpts` filter chains for video and `atrim`+`asetpts` for audio.
	- Apply scaling/padding to each video trim.
	- Concatenate the labeled outputs with a single `concat=n=N:v=1:a=1` filter.

Example (2 segments) — generator must produce this dynamically for N segments:

```
ffmpeg -i input.mp4 -filter_complex \
	"[0:v]trim=start=10:end=30,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1[v0]; \
	 [0:a]atrim=start=10:end=30,asetpts=PTS-STARTPTS[a0]; \
	 [0:v]trim=start=300:end=320,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1[v1]; \
	 [0:a]atrim=start=300:end=320,asetpts=PTS-STARTPTS[a1]; \
	 [v0][a0][v1][a1]concat=n=2:v=1:a=1[outv][outa]" \
	-map "[outv]" -map "[outa]" -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 128k output.mp4
```

Notes:
- If source has no audio: use `concat=n={N}:v=1:a=0` and map only the video output.
- Use `-movflags +faststart` for web-friendly MP4.

2) Multi-step: extract each clip to a temp file (re-encode to target), then concat using the concat demuxer

- Steps:
	1. For each pair: ffmpeg -ss START -to END -i input.mp4 -vf "<scale/pad>" -c:v libx264 -crf 20 -preset medium -c:a aac tmp_clip_000.mp4
	2. Write a `mylist.txt` containing `file 'tmp_clip_000.mp4'` lines in order.
	3. ffmpeg -f concat -safe 0 -i mylist.txt -c copy output.mp4

- Pros: simpler to implement; easy to parallelize extraction. Cons: more disk usage and multiple encode passes.

## Encoding defaults

- Video codec: `libx264` (default), `-crf 18-23` (default 20), `-preset medium`.
- Audio codec: `aac` (default), `-b:a 128k`.
- Flags: `-movflags +faststart`.

## Logging & progress

- `--verbose` streams ffmpeg stdout/stderr.
- `--dry-run` prints generated ffmpeg command(s) and exits.
- Optional advanced: use ffmpeg `-progress pipe:1` and parse to show a progress bar.

## Edge cases and validation rules

- Odd number of time tokens -> error.
- start >= end -> error or skip if equal (warn and skip).
- Times outside duration -> error unless `--clamp` set, which clamps to valid range.
- Overlapping ranges: allowed, but warn the user.
- No audio track: produce audio-less MP4.
- Very large number of segments: warn about memory and performance; recommend multi-step approach.

## Implementation notes (high-level)

- Python version: 3.9+.
- Standard libs: `argparse`, `subprocess`, `tempfile`, `pathlib`, `logging`, `shutil`, `json`.
- Optional: `tqdm` for progress display, `pytest` for tests.
- Use `ffprobe` to inspect the input file (duration, streams, rotation).
- Build and run ffmpeg via `subprocess.run()` or `subprocess.Popen()` when streaming output.
- Keep temp files under `tempfile.TemporaryDirectory()` and ensure cleanup on error.

Pseudocode steps:
1. Parse args -> list of (start, end) seconds.
2. Call ffprobe -> duration, has_audio, rotation.
3. Validate/clamp ranges.
4. If `--dry-run`: build and print ffmpeg command(s) and exit.
5. Build either `filter_complex` (single-pass) or per-clip commands (multi-step).
6. Execute ffmpeg and monitor return code.
7. On success, write any metadata sidecar if desired; on failure, print ffmpeg stderr and return non-zero.

## Tests

Unit tests (pytest):
- time parsing: `"00:01:23.45"` -> `83.45`; `"83.45"` -> `83.45`.
- arg validation: odd token count -> raises error.
- build command generator: verify generated `filter_complex` structure for N=1 and N=2.

Integration/smoke test (requires a small sample video in `tests/assets`):
- Run script with two ranges; assert output exists, resolution == target, and duration ≈ sum of clips.

CI: include at least unit tests in CI; integration test optional (because of binary size).

## Files to deliver

- `make_shorts.py` — main CLI implementation.
- `README.md` — usage, examples, notes about ffmpeg requirement.
- `requirements.txt` (optional) — e.g., `tqdm`, `pytest`.
- `tests/test_parse.py` — unit tests for parsing/validation.

## Acceptance criteria

- Script accepts first param = video file and subsequent start/end pairs.
- Script validates input and time ranges and fails with clear messages on invalid input.
- Script produces an MP4 at portrait 9:16 (default 1080x1920) containing concatenated clips in order.
- Audio is preserved if present; otherwise video-only output is valid.
- `--dry-run` produces the ffmpeg command(s) without running.
- README contains usage examples.

## Example quick reference commands

Single-pass ffmpeg pattern (generated by the script):

```
ffmpeg -i input.mp4 -filter_complex "[0:v]trim=start=10:end=30,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1[v0]; [0:a]atrim=start=10:end=30,asetpts=PTS-STARTPTS[a0]; [v0][a0]concat=n=1:v=1:a=1[outv][outa]" -map "[outv]" -map "[outa]" -c:v libx264 -crf 20 -preset medium -c:a aac -b:a 128k output.mp4
```

Multi-step pattern (per-clip re-encode then concat):

```
ffmpeg -ss 10 -to 30 -i input.mp4 -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1" -c:v libx264 -crf 20 -preset medium -c:a aac tmp_000.mp4
echo "file 'tmp_000.mp4'" > mylist.txt
ffmpeg -f concat -safe 0 -i mylist.txt -c copy output.mp4
```

## Notes and follow-ups

- The implementing developer should pick one of the two implementation approaches. For small N and simplicity, use the single-pass `filter_complex` approach. For many segments or to simplify memory use, use the multi-step approach.
- Consider adding `--ranges-file` support (one start/end pair per line) as a convenience.
- Optionally implement `--progress` parsing for a nicer UX.

---

End of specification.

