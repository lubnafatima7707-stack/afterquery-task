#!/usr/bin/env python3
"""Prints whatever it likes instead of speaking the protocol."""
import sys

for line in sys.stdin:
    sys.stdout.write("hello\n")
    sys.stdout.flush()
