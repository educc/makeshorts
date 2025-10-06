#!/usr/bin/env python3
"""
Test script for make_shorts.py functionality.
"""

import pytest
import sys
import os
from pathlib import Path

# Add the parent directory to the path so we can import make_shorts
sys.path.insert(0, str(Path(__file__).parent.parent))

from make_shorts import (
    parse_time, parse_time_pairs, parse_resolution,
    validate_and_clamp_ranges, build_filter_complex
)


class TestTimeParsing:
    """Test time parsing functionality."""
    
    def test_parse_time_seconds(self):
        """Test parsing plain seconds."""
        assert parse_time("10") == 10.0
        assert parse_time("10.5") == 10.5
        assert parse_time("0") == 0.0
        assert parse_time("123.456") == 123.456
    
    def test_parse_time_hms_format(self):
        """Test parsing HH:MM:SS format."""
        assert parse_time("00:00:10") == 10.0
        assert parse_time("00:01:30") == 90.0
        assert parse_time("01:00:00") == 3600.0
        assert parse_time("00:00:00") == 0.0
    
    def test_parse_time_hms_with_milliseconds(self):
        """Test parsing HH:MM:SS.ms format."""
        assert parse_time("00:00:10.5") == 10.5
        assert parse_time("00:01:23.45") == 83.45
        assert parse_time("01:00:00.123") == 3600.123
    
    def test_parse_time_invalid_format(self):
        """Test parsing invalid formats."""
        with pytest.raises(ValueError):
            parse_time("invalid")
        with pytest.raises(ValueError):
            parse_time("1:2:3")  # Wrong format (need leading zeros for minutes/seconds)
        with pytest.raises(ValueError):
            parse_time("1:2")  # Missing seconds
        with pytest.raises(ValueError):
            parse_time("ab:cd:ef")  # Non-numeric values


class TestTimePairs:
    """Test time pair parsing."""
    
    def test_parse_time_pairs_valid(self):
        """Test parsing valid time pairs."""
        pairs = parse_time_pairs(["10", "20", "30", "40"])
        assert pairs == [(10.0, 20.0), (30.0, 40.0)]
        
        pairs = parse_time_pairs(["00:00:10", "00:00:20"])
        assert pairs == [(10.0, 20.0)]
    
    def test_parse_time_pairs_odd_count(self):
        """Test error on odd number of tokens."""
        with pytest.raises(ValueError, match="Odd number of time tokens"):
            parse_time_pairs(["10", "20", "30"])
    
    def test_parse_time_pairs_invalid_range(self):
        """Test error when start >= end."""
        with pytest.raises(ValueError, match="Invalid range"):
            parse_time_pairs(["20", "10"])
        
        # Equal times should be skipped with warning, not error
        pairs = parse_time_pairs(["10", "10", "20", "30"])
        assert pairs == [(20.0, 30.0)]


class TestResolutionParsing:
    """Test resolution parsing."""
    
    def test_parse_resolution_valid(self):
        """Test parsing valid resolutions."""
        assert parse_resolution("1080x1920") == (1080, 1920)
        assert parse_resolution("720x1280") == (720, 1280)
        assert parse_resolution("1920x1080") == (1920, 1080)
    
    def test_parse_resolution_invalid(self):
        """Test parsing invalid resolutions."""
        with pytest.raises(ValueError):
            parse_resolution("1080")
        with pytest.raises(ValueError):
            parse_resolution("1080x")
        with pytest.raises(ValueError):
            parse_resolution("invalid")


class TestRangeValidation:
    """Test range validation and clamping."""
    
    def test_validate_ranges_valid(self):
        """Test validation of valid ranges."""
        ranges = [(10.0, 20.0), (30.0, 40.0)]
        result = validate_and_clamp_ranges(ranges, 60.0, clamp=False)
        assert result == ranges
    
    def test_validate_ranges_outside_duration(self):
        """Test validation of ranges outside duration."""
        ranges = [(10.0, 20.0), (50.0, 70.0)]  # Second range goes beyond 60s
        
        # Should fail without clamp
        with pytest.raises(ValueError, match="outside video duration"):
            validate_and_clamp_ranges(ranges, 60.0, clamp=False)
        
        # Should clamp with clamp=True
        result = validate_and_clamp_ranges(ranges, 60.0, clamp=True)
        assert result == [(10.0, 20.0), (50.0, 60.0)]
    
    def test_validate_ranges_clamp_invalid(self):
        """Test clamping that makes ranges invalid."""
        ranges = [(70.0, 80.0)]  # Entirely outside 60s duration
        result = validate_and_clamp_ranges(ranges, 60.0, clamp=True)
        assert result == []  # Should be empty after clamping


class TestFilterComplex:
    """Test filter complex generation."""
    
    def test_build_filter_complex_single_clip_with_audio(self):
        """Test filter complex for single clip with audio."""
        ranges = [(10.0, 20.0)]
        filter_str = build_filter_complex(ranges, 1080, 1920, 'pad', has_audio=True)
        
        # Should contain basic components
        assert 'trim=start=10.0:end=20.0' in filter_str
        assert 'atrim=start=10.0:end=20.0' in filter_str
        assert 'scale=1080:1920:force_original_aspect_ratio=decrease' in filter_str
        assert 'concat=n=1:v=1:a=1' in filter_str
    
    def test_build_filter_complex_single_clip_no_audio(self):
        """Test filter complex for single clip without audio."""
        ranges = [(10.0, 20.0)]
        filter_str = build_filter_complex(ranges, 1080, 1920, 'pad', has_audio=False)
        
        # Should not contain audio components
        assert 'trim=start=10.0:end=20.0' in filter_str
        assert 'atrim' not in filter_str
        assert 'concat=n=1:v=1:a=0' in filter_str
    
    def test_build_filter_complex_multiple_clips(self):
        """Test filter complex for multiple clips."""
        ranges = [(10.0, 20.0), (30.0, 40.0)]
        filter_str = build_filter_complex(ranges, 1080, 1920, 'crop', has_audio=True)
        
        # Should contain components for both clips
        assert 'trim=start=10.0:end=20.0' in filter_str
        assert 'trim=start=30.0:end=40.0' in filter_str
        assert 'atrim=start=10.0:end=20.0' in filter_str
        assert 'atrim=start=30.0:end=40.0' in filter_str
        assert 'concat=n=2:v=1:a=1' in filter_str
        
        # Should use crop scaling
        assert 'force_original_aspect_ratio=increase' in filter_str
        assert 'crop=1080:1920' in filter_str
    
    def test_build_filter_complex_stretch_mode(self):
        """Test filter complex with stretch scaling mode."""
        ranges = [(10.0, 20.0)]
        filter_str = build_filter_complex(ranges, 720, 1280, 'stretch', has_audio=False)
        
        # Should use direct scaling without aspect ratio preservation
        assert 'scale=720:1280' in filter_str
        assert 'force_original_aspect_ratio' not in filter_str
        assert 'pad=' not in filter_str
        assert 'crop=' not in filter_str


if __name__ == '__main__':
    # Run tests if script is executed directly
    pytest.main([__file__, '-v'])