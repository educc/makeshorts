#!/usr/bin/env python3
"""
Integration test for make_shorts.py - tests end-to-end functionality
"""

import pytest
import subprocess
import sys
import tempfile
import os
from pathlib import Path

def test_integration():
    """Test that the script creates a valid output with expected properties."""
    
        # Path to the example video and script
    script_path = Path(__file__).parent.parent / "make_shorts.py"
    video_path = Path(__file__).parent.parent / "examples" / "ai-tech-jobs.mp4"
    
    print(f"Testing with script: {script_path}")
    print(f"Testing with video: {video_path}")
    print(f"sys.executable: {sys.executable}")
    
    # Test basic functionality - use mktemp instead of NamedTemporaryFile
    # to avoid file handle conflicts with ffmpeg
    import time
    temp_dir = tempfile.gettempdir()
    output_path = os.path.join(temp_dir, f"test_output_{int(time.time() * 1000000)}.mp4")
    
    try:
        # Run the script - use sys.executable to get the right Python
        cmd = [
            sys.executable, str(script_path),
            str(video_path),
            "0", "5",  # Extract first 5 seconds
            "--output", output_path,
            "--resolution", "720x1280"  # Use smaller resolution for faster test
        ]
        
        print(f"Running cmd: {cmd}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        print(f"Return code: {result.returncode}")
        print(f"Stdout: {result.stdout}")
        print(f"Stderr: {result.stderr}")
        
        if result.returncode != 0:
            pytest.fail(f"Script failed with code {result.returncode}\nStdout: {result.stdout}\nStderr: {result.stderr}")
        
        # Check that output file exists
        assert Path(output_path).exists(), "Output file was not created"
        
        # Check file size (should be > 0)
        file_size = Path(output_path).stat().st_size
        assert file_size > 0, "Output file is empty"
        
        print(f"✅ Output file created successfully: {file_size} bytes")
        
        # Use ffprobe to check video properties
        probe_cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", output_path
        ]
        
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
        
        assert probe_result.returncode == 0, "Failed to probe output video"
        
        import json
        probe_data = json.loads(probe_result.stdout)
        
        # Check video stream properties
        video_stream = None
        for stream in probe_data.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break
        
        assert video_stream is not None, "No video stream found in output"
        
        # Verify resolution
        width = video_stream.get("width")
        height = video_stream.get("height")
        duration = float(probe_data.get("format", {}).get("duration", 0))
        
        print(f"✅ Video properties: {width}x{height}, duration: {duration:.2f}s")
        
        assert width == 720, f"Wrong width: expected 720, got {width}"
        assert height == 1280, f"Wrong height: expected 1280, got {height}"
        assert 4.8 <= duration <= 5.2, f"Wrong duration: expected ~5s, got {duration:.2f}s"
        
        print("✅ All integration tests passed!")
        
    finally:
        # Cleanup
        if Path(output_path).exists():
            os.unlink(output_path)


if __name__ == "__main__":
    pytest.main([__file__, '-v'])