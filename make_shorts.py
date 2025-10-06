#!/usr/bin/env python3
"""
make_shorts.py — A CLI tool to extract multiple ranges from a source video
and concatenate them into a single vertical (phone-ratio) MP4 suitable for YouTube Shorts.
"""

import argparse
import json
import logging
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(levelname)s: %(message)s'
    )


def parse_time(time_str: str) -> float:
    """
    Parse time string to seconds.
    
    Accepts:
    - HH:MM:SS[.ms] format (e.g., "00:01:23.45")
    - Plain seconds as float/int (e.g., "83.45" or "83")
    
    Returns:
        float: Time in seconds
    """
    # Try parsing as plain number first
    try:
        return float(time_str)
    except ValueError:
        pass
    
    # Try parsing as HH:MM:SS[.ms] format
    time_pattern = r'^(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d+))?$'
    match = re.match(time_pattern, time_str)
    
    if not match:
        raise ValueError(f"Invalid time format: '{time_str}'. Use HH:MM:SS[.ms] or seconds as number.")
    
    hours, minutes, seconds, milliseconds = match.groups()
    total_seconds = int(hours) * 3600 + int(minutes) * 60 + int(seconds)
    
    if milliseconds:
        # Convert milliseconds to decimal seconds
        ms_decimal = float(f"0.{milliseconds}")
        total_seconds += ms_decimal
    
    return float(total_seconds)


def parse_time_pairs(time_tokens: List[str]) -> List[Tuple[float, float]]:
    """
    Parse time tokens into start/end pairs.
    
    Args:
        time_tokens: List of time strings (must be even number)
    
    Returns:
        List of (start, end) tuples in seconds
    """
    if len(time_tokens) % 2 != 0:
        raise ValueError(f"Odd number of time tokens ({len(time_tokens)}). Must provide start/end pairs.")
    
    pairs = []
    for i in range(0, len(time_tokens), 2):
        start = parse_time(time_tokens[i])
        end = parse_time(time_tokens[i + 1])
        
        if start >= end:
            if start == end:
                logging.warning(f"Skipping zero-length clip: {start} == {end}")
                continue
            else:
                raise ValueError(f"Invalid range: start ({start}) >= end ({end})")
        
        pairs.append((start, end))
    
    return pairs


def get_video_info(input_path: str) -> Dict[str, Any]:
    """
    Get video information using ffprobe.
    
    Returns:
        Dict containing duration, has_audio, rotation, etc.
    """
    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams',
        input_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe failed: {e.stderr}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse ffprobe output: {e}")
    
    # Extract duration
    duration = None
    if 'format' in data and 'duration' in data['format']:
        duration = float(data['format']['duration'])
    
    # Check for audio stream
    has_audio = False
    video_streams = []
    audio_streams = []
    
    for stream in data.get('streams', []):
        if stream.get('codec_type') == 'video':
            video_streams.append(stream)
        elif stream.get('codec_type') == 'audio':
            audio_streams.append(stream)
            has_audio = True
    
    # Check for rotation metadata
    rotation = 0
    if video_streams:
        # Check for rotation in side_data_list
        for side_data in video_streams[0].get('side_data_list', []):
            if side_data.get('side_data_type') == 'Display Matrix':
                rotation_str = side_data.get('rotation', '0')
                try:
                    rotation = int(float(rotation_str))
                except (ValueError, TypeError):
                    rotation = 0
    
    return {
        'duration': duration,
        'has_audio': has_audio,
        'rotation': rotation,
        'video_streams': video_streams,
        'audio_streams': audio_streams
    }


def validate_and_clamp_ranges(ranges: List[Tuple[float, float]], duration: float, clamp: bool = False) -> List[Tuple[float, float]]:
    """
    Validate time ranges against video duration.
    
    Args:
        ranges: List of (start, end) tuples
        duration: Video duration in seconds
        clamp: If True, clamp ranges to valid bounds instead of failing
    
    Returns:
        List of validated (start, end) tuples
    """
    validated_ranges = []
    
    for i, (start, end) in enumerate(ranges):
        original_start, original_end = start, end
        
        if not clamp:
            if start < 0 or end > duration:
                raise ValueError(f"Range {i+1} ({start}, {end}) is outside video duration (0, {duration})")
        else:
            # Clamp to valid bounds
            start = max(0, start)
            end = min(duration, end)
            
            if (start, end) != (original_start, original_end):
                logging.warning(f"Clamped range {i+1}: ({original_start}, {original_end}) -> ({start}, {end})")
            
            # Skip if range becomes invalid after clamping
            if start >= end:
                logging.warning(f"Skipping invalid range after clamping: ({start}, {end})")
                continue
        
        validated_ranges.append((start, end))
    
    return validated_ranges


def check_overlapping_ranges(ranges: List[Tuple[float, float]]) -> None:
    """Check for overlapping ranges and warn user."""
    for i, (start1, end1) in enumerate(ranges):
        for j, (start2, end2) in enumerate(ranges[i+1:], i+1):
            if not (end1 <= start2 or end2 <= start1):  # Ranges overlap
                logging.warning(f"Overlapping ranges detected: range {i+1} ({start1}, {end1}) and range {j+1} ({start2}, {end2})")


def parse_resolution(resolution_str: str) -> Tuple[int, int]:
    """Parse resolution string like '1080x1920' to (width, height)."""
    try:
        width, height = resolution_str.split('x')
        return int(width), int(height)
    except ValueError:
        raise ValueError(f"Invalid resolution format: '{resolution_str}'. Use WIDTHxHEIGHT (e.g., 1080x1920)")


def build_filter_complex(ranges: List[Tuple[float, float]], target_width: int, target_height: int, 
                        scale_mode: str, has_audio: bool) -> str:
    """
    Build ffmpeg filter_complex string for concatenating multiple clips.
    
    Args:
        ranges: List of (start, end) time pairs
        target_width: Target video width
        target_height: Target video height  
        scale_mode: Scaling mode ('pad', 'crop', 'stretch')
        has_audio: Whether input has audio
    
    Returns:
        Complete filter_complex string
    """
    if not ranges:
        raise ValueError("No valid ranges to process")
    
    # Build scaling filter based on mode
    if scale_mode == 'pad':
        scale_filter = f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    elif scale_mode == 'crop':
        scale_filter = f"scale={target_width}:{target_height}:force_original_aspect_ratio=increase,crop={target_width}:{target_height},setsar=1"
    elif scale_mode == 'stretch':
        scale_filter = f"scale={target_width}:{target_height},setsar=1"
    else:
        raise ValueError(f"Invalid scale mode: {scale_mode}")
    
    filter_parts = []
    video_labels = []
    audio_labels = []
    
    # Create filter chains for each segment
    for i, (start, end) in enumerate(ranges):
        # Video filter chain
        video_filter = f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,{scale_filter}[v{i}]"
        filter_parts.append(video_filter)
        video_labels.append(f"[v{i}]")
        
        # Audio filter chain (if audio exists)
        if has_audio:
            audio_filter = f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}]"
            filter_parts.append(audio_filter)
            audio_labels.append(f"[a{i}]")
    
    # Concatenation filter
    n_segments = len(ranges)
    if has_audio:
        concat_inputs = []
        for i in range(n_segments):
            concat_inputs.extend([f"[v{i}]", f"[a{i}]"])
        concat_filter = f"{''.join(concat_inputs)}concat=n={n_segments}:v=1:a=1[outv][outa]"
    else:
        concat_inputs = ''.join(video_labels)
        concat_filter = f"{concat_inputs}concat=n={n_segments}:v=1:a=0[outv]"
    
    filter_parts.append(concat_filter)
    
    return '; '.join(filter_parts)


def build_ffmpeg_command(input_path: str, output_path: str, filter_complex: str, 
                        has_audio: bool, codec_v: str, crf: int, preset: str,
                        codec_a: str, audio_bitrate: str) -> List[str]:
    """Build complete ffmpeg command."""
    cmd = [
        'ffmpeg', '-i', input_path,
        '-filter_complex', filter_complex,
        '-map', '[outv]'
    ]
    
    if has_audio:
        cmd.extend(['-map', '[outa]'])
    
    # Video encoding options
    cmd.extend(['-c:v', codec_v, '-crf', str(crf), '-preset', preset])
    
    # Audio encoding options (if audio exists)
    if has_audio:
        cmd.extend(['-c:a', codec_a, '-b:a', audio_bitrate])
    
    # MP4 optimization
    cmd.extend(['-movflags', '+faststart'])
    
    # Output file
    cmd.append(output_path)
    
    return cmd


def run_ffmpeg(cmd: List[str], verbose: bool = False) -> None:
    """Run ffmpeg command and handle output."""
    if verbose:
        logging.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd)
    else:
        result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        error_msg = f"ffmpeg failed with return code {result.returncode}"
        if not verbose and result.stderr:
            error_msg += f"\nStderr: {result.stderr}"
        raise RuntimeError(error_msg)


def main():
    parser = argparse.ArgumentParser(
        description="Extract multiple ranges from a video and concatenate into portrait MP4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python make_shorts.py input.mp4 00:00:10 00:00:30 00:05:00 00:05:20
  python make_shorts.py input.mp4 10 30 --output shorts.mp4 --resolution 1080x1920
  python make_shorts.py input.mp4 10 30 300 320 --scale-mode crop --dry-run
        """
    )
    
    # Positional arguments
    parser.add_argument('input_path', help='Input video file path')
    parser.add_argument('time_tokens', nargs='*', 
                       help='Start and end times (must be even number of tokens)')
    
    # Output options
    parser.add_argument('-o', '--output', default='shorts.mp4',
                       help='Output file path (default: shorts.mp4)')
    parser.add_argument('-r', '--resolution', default='1080x1920',
                       help='Target WxH resolution (default: 1080x1920)')
    
    # Scaling options
    parser.add_argument('--scale-mode', choices=['pad', 'crop', 'stretch'], default='pad',
                       help='Scaling mode (default: pad)')
    
    # Encoding options
    parser.add_argument('--codec-v', default='libx264', help='Video codec (default: libx264)')
    parser.add_argument('--crf', type=int, default=20, help='CRF value (default: 20)')
    parser.add_argument('--preset', default='medium', help='Encoding preset (default: medium)')
    parser.add_argument('--codec-a', default='aac', help='Audio codec (default: aac)')
    parser.add_argument('--audio-bitrate', default='128k', help='Audio bitrate (default: 128k)')
    
    # Behavior options
    parser.add_argument('--dry-run', action='store_true',
                       help='Print ffmpeg command without running')
    parser.add_argument('--verbose', action='store_true',
                       help='Stream ffmpeg output')
    parser.add_argument('--max-duration', type=float,
                       help='Cap final output length (seconds)')
    parser.add_argument('--clamp', action='store_true',
                       help='Clamp start/end to input duration instead of failing')
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    
    try:
        # Validate input file exists
        if not Path(args.input_path).exists():
            raise FileNotFoundError(f"Input file not found: {args.input_path}")
        
        # Parse time tokens
        if not args.time_tokens:
            raise ValueError("No time ranges provided. Specify start/end time pairs.")
        
        ranges = parse_time_pairs(args.time_tokens)
        if not ranges:
            raise ValueError("No valid time ranges after parsing.")
        
        # Get video information
        logging.info(f"Analyzing input video: {args.input_path}")
        video_info = get_video_info(args.input_path)
        
        if video_info['duration'] is None:
            raise RuntimeError("Could not determine video duration")
        
        logging.info(f"Video duration: {video_info['duration']:.2f}s")
        logging.info(f"Has audio: {video_info['has_audio']}")
        
        # Validate and clamp ranges
        validated_ranges = validate_and_clamp_ranges(ranges, video_info['duration'], args.clamp)
        
        if not validated_ranges:
            raise ValueError("No valid ranges after validation/clamping")
        
        # Check for overlapping ranges
        check_overlapping_ranges(validated_ranges)
        
        # Apply max duration if specified
        if args.max_duration:
            total_duration = sum(end - start for start, end in validated_ranges)
            if total_duration > args.max_duration:
                logging.warning(f"Total duration ({total_duration:.2f}s) exceeds max duration ({args.max_duration}s)")
                # Truncate ranges to fit within max duration
                new_ranges = []
                current_duration = 0
                for start, end in validated_ranges:
                    clip_duration = end - start
                    if current_duration + clip_duration <= args.max_duration:
                        new_ranges.append((start, end))
                        current_duration += clip_duration
                    else:
                        # Partial clip to reach max duration
                        remaining = args.max_duration - current_duration
                        if remaining > 0:
                            new_ranges.append((start, start + remaining))
                        break
                validated_ranges = new_ranges
        
        # Parse resolution
        target_width, target_height = parse_resolution(args.resolution)
        
        # Build filter complex
        filter_complex = build_filter_complex(
            validated_ranges, target_width, target_height, 
            args.scale_mode, video_info['has_audio']
        )
        
        # Build ffmpeg command
        cmd = build_ffmpeg_command(
            args.input_path, args.output, filter_complex,
            video_info['has_audio'], args.codec_v, args.crf, args.preset,
            args.codec_a, args.audio_bitrate
        )
        
        if args.dry_run:
            print("Generated ffmpeg command:")
            print(' '.join(cmd))
            return 0
        
        # Run ffmpeg
        logging.info(f"Processing {len(validated_ranges)} clip(s) to {args.output}")
        run_ffmpeg(cmd, args.verbose)
        
        logging.info(f"Successfully created: {args.output}")
        return 0
        
    except Exception as e:
        logging.error(str(e))
        return 1


if __name__ == '__main__':
    sys.exit(main())