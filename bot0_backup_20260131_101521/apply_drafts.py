# -*- coding: utf-8 -*-
import sys
path = "/home/goida/label/bot0/label.py"
print("Reading label.py...")
with open(path, "r", encoding="utf-8") as f:
    content = f.read()
print(f"File size: {len(content)} chars")
# Test: just check if we can find some markers
if "def start_bot_with_retry():" in content:
    print("✓ Found start_bot_with_retry")
if '@bot.message_handler(commands=[\'cancel\'])' in content:
    print("✓ Found cancel handler")
print("Done test.")
