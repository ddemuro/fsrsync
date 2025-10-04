"""Pytest configuration and shared fixtures"""
import pytest
import sys
import os

# Add parent directory to path so tests can import fsrsync modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
