#!/usr/bin/env python3
"""
Meme Radar - Cross-Platform Meme Detection System

Main entry point for the CLI.

Usage:
    python radar.py --help
    python radar.py init-db
    python radar.py collect --platform reddit
    python radar.py show --since 2
    python radar.py run --interval 30
"""

from meme_radar.cli import main

if __name__ == '__main__':
    main()
