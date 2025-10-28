#!/usr/bin/env python3
import sys
from .main import main as run_tempmail

def cli():
    if len(sys.argv) == 2 and sys.argv[1] == '-h':
        print("clitm - TempMail CLI Tool")
        print("\nUsage:")
        print("  clitm            Run the TempMail CLI interface")
        print("  clitm -h         Show this help message")
        print("  clitm -info      Show developer information")
        sys.exit(0)

    elif len(sys.argv) == 2 and sys.argv[1] == '-info':
        print("clitm - developed by Luminar")
        print("Version: 1.0.0")
        print("License: MIT")
        print("Repository: https://github.com/siddharthguptapydev/clitm")
        sys.exit(0)

    else:
        run_tempmail()
