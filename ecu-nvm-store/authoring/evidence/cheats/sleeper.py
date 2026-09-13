#!/usr/bin/env python3
"""Mounts, then stops answering and leaves a child behind to outlive the run."""
import os
import sys
import time

if os.fork() > 0:
    for line in sys.stdin:
        line = line.strip()
        if line == "MOUNT":
            sys.stdout.write("MOUNTED\n")
            sys.stdout.flush()
        elif line == "GO":
            time.sleep(10000)
else:
    os.setsid()
    time.sleep(10000)
