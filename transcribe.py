#!/usr/bin/env python3
"""
Transcribe every word from a video and generate an SRT subtitle file.
Based on the Scrolling_Subtitles_On_Video_using_Python notebook.
"""

import argparse
import os
import sys
import json
from pathlib import Path
import ffmpeg
from faster_whisper import WhisperModel


def extract_audio(video_path, audio_path):
    """Extract audio from video file using ffmpeg."""
    print(f"Extracting audio from {video_path}...")
    
    # Create the ffmpeg input stream
    input_stream = ffmpeg.input(video_path)
    
    # Extract the audio stream from the input stream
    audio = input_stream.audio
    
    # Save the audio stream as an MP3 file
    output_stream = ffmpeg.output(audio, audio_path)
    
    # Overwrite output file if it already exists
    output_stream = ffmpeg.overwrite_output(output_stream)
    
    ffmpeg.run(output_stream, quiet=True)
    print(f"Audio extracted to {audio_path}")


def transcribe_audio(audio_path, model_size="medium"):
    """Transcribe audio file with word-level timestamps using Whisper."""
    print(f"Loading Whisper model ({model_size})...")
    model = WhisperModel(model_size)
    
    print(f"Transcribing {audio_path}...")
    segments, info = model.transcribe(audio_path, word_timestamps=True)
    segments = list(segments)  # The transcription will actually run here
    
    wordlevel_info = []
    for segment in segments:
        for word in segment.words:
            wordlevel_info.append({
                'word': word.word,
                'start': word.start,
                'end': word.end
            })
    
    print(f"Transcription complete: {len(wordlevel_info)} words found")
    return wordlevel_info


def format_srt_time(seconds):
    """Convert seconds to SRT time format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def split_text_into_lines(data, max_chars=30, max_words=3, max_duration=2.5, max_gap=1.5):
    """
    Split word-level timestamps into line-level subtitles.
    
    Args:
        data: List of word dictionaries with 'word', 'start', 'end' keys
        max_chars: Maximum characters per line (default: 30)
        max_words: Maximum words per line (default: 3)
        max_duration: Maximum duration per line in seconds
        max_gap: Maximum gap between words before splitting in seconds
    """
    subtitles = []
    line = []
    line_duration = 0

    for idx, word_data in enumerate(data):
        word = word_data["word"]
        start = word_data["start"]
        end = word_data["end"]

        line.append(word_data)
        line_duration += end - start

        temp = " ".join(item["word"] for item in line)

        # Check if adding a new word exceeds the maximum character count or duration
        new_line_chars = len(temp)
        word_count = len(line)

        duration_exceeded = line_duration > max_duration
        chars_exceeded = new_line_chars > max_chars
        words_exceeded = word_count >= max_words
        
        if idx > 0:
            gap = word_data['start'] - data[idx-1]['end']
            maxgap_exceeded = gap > max_gap
        else:
            maxgap_exceeded = False

        if duration_exceeded or chars_exceeded or maxgap_exceeded or words_exceeded:
            if line:
                subtitle_line = {
                    "word": " ".join(item["word"] for item in line),
                    "start": line[0]["start"],
                    "end": line[-1]["end"],
                    "textcontents": line
                }
                subtitles.append(subtitle_line)
                line = []
                line_duration = 0

    if line:
        subtitle_line = {
            "word": " ".join(item["word"] for item in line),
            "start": line[0]["start"],
            "end": line[-1]["end"],
            "textcontents": line
        }
        subtitles.append(subtitle_line)

    return subtitles


def generate_srt(wordlevel_info, output_path):
    """Generate SRT subtitle file from word-level timestamps."""
    print(f"Generating SRT file...")
    
    # Split into lines
    linelevel_subtitles = split_text_into_lines(wordlevel_info)
    
    # Write SRT file
    with open(output_path, 'w', encoding='utf-8') as f:
        for idx, subtitle in enumerate(linelevel_subtitles, 1):
            # SRT format:
            # 1
            # 00:00:00,000 --> 00:00:02,000
            # Subtitle text
            # (blank line)
            
            start_time = format_srt_time(subtitle['start'])
            end_time = format_srt_time(subtitle['end'])
            text = subtitle['word']
            
            f.write(f"{idx}\n")
            f.write(f"{start_time} --> {end_time}\n")
            f.write(f"{text}\n")
            f.write("\n")
    
    print(f"SRT file saved to {output_path}")


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Transcribe every word from a video and generate an SRT subtitle file."
    )
    parser.add_argument(
        "video",
        help="Path to the input video file (mp4)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Path to the output SRT file (default: video_name.srt)"
    )
    parser.add_argument(
        "-m", "--model",
        default="medium",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size (default: medium)"
    )
    parser.add_argument(
        "--keep-audio",
        action="store_true",
        help="Keep the extracted audio file"
    )
    parser.add_argument(
        "--json",
        help="Save word-level timestamps to JSON file"
    )
    
    args = parser.parse_args()
    
    # Validate input video exists
    video_path = Path(args.video)
    if not video_path.exists():
        print(f"Error: Video file not found: {args.video}", file=sys.stderr)
        sys.exit(1)
    
    # Determine output paths
    if args.output:
        srt_path = Path(args.output)
    else:
        srt_path = video_path.with_suffix('.srt')
    
    audio_path = video_path.with_suffix('.mp3')
    
    try:
        # Step 1: Extract audio
        extract_audio(str(video_path), str(audio_path))
        
        # Step 2: Transcribe with word-level timestamps
        wordlevel_info = transcribe_audio(str(audio_path), args.model)
        
        # Step 3: Save JSON if requested
        if args.json:
            json_path = Path(args.json)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(wordlevel_info, f, indent=4)
            print(f"Word-level timestamps saved to {json_path}")
        
        # Step 4: Generate SRT file
        generate_srt(wordlevel_info, str(srt_path))
        
        # Clean up audio file unless --keep-audio is specified
        if not args.keep_audio and audio_path.exists():
            audio_path.unlink()
            print(f"Cleaned up temporary audio file")
        
        print(f"\n✓ Success! SRT file created: {srt_path}")
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
