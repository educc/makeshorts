#!/usr/bin/env python3
"""
Integration test for make_shorts.py - tests end-to-end functionality
"""

import subprocess
import tempfile
import os
from pathlib import Path

def test_integration():
    """Test that the script creates a valid output with expected properties."""
    
    # Path to the example video and script
    script_path = Path(__file__).parent / "make_shorts.py"
    video_path = Path(__file__).parent / "examples" / "video.mp4"
    
    print(f"Testing with script: {script_path}")
    print(f"Testing with video: {video_path}")
    
    # Test basic functionality
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_file:
        output_path = tmp_file.name
    
    try:
        # Run the script
        cmd = [
            "python", str(script_path),
            str(video_path),
            "0", "5",  # Extract first 5 seconds
            "--output", output_path,
            "--resolution", "720x1280"  # Use smaller resolution for faster test
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"Script failed with code {result.returncode}")
            print(f"Stdout: {result.stdout}")
            print(f"Stderr: {result.stderr}")
            return False
        
        # Check that output file exists
        if not Path(output_path).exists():
            print("Output file was not created")
            return False
        
        # Check file size (should be > 0)
        file_size = Path(output_path).stat().st_size
        if file_size == 0:
            print("Output file is empty")
            return False
        
        print(f"✅ Output file created successfully: {file_size} bytes")
        
        # Use ffprobe to check video properties
        probe_cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", output_path
        ]
        
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
        
        if probe_result.returncode != 0:
            print("Failed to probe output video")
            return False
        
        import json
        probe_data = json.loads(probe_result.stdout)
        
        # Check video stream properties
        video_stream = None
        for stream in probe_data.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break
        
        if not video_stream:
            print("No video stream found in output")
            return False
        
        # Verify resolution
        width = video_stream.get("width")
        height = video_stream.get("height")
        duration = float(probe_data.get("format", {}).get("duration", 0))
        
        print(f"✅ Video properties: {width}x{height}, duration: {duration:.2f}s")
        
        if width != 720 or height != 1280:
            print(f"❌ Wrong resolution: expected 720x1280, got {width}x{height}")
            return False
        
        if not (4.8 <= duration <= 5.2):  # Allow some tolerance
            print(f"❌ Wrong duration: expected ~5s, got {duration:.2f}s")
            return False
        
        print("✅ All integration tests passed!")
        return True
        
    finally:
        # Cleanup
        if Path(output_path).exists():
            os.unlink(output_path)

if __name__ == "__main__":
    success = test_integration()
    exit(0 if success else 1)