#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import base64
import sys

# Base64 encoded content will be passed via stdin
if len(sys.argv) > 1:
    # If argument provided, decode it
    encoded = sys.argv[1]
else:
    # Otherwise read from stdin
    encoded = sys.stdin.read()

try:
    content = base64.b64decode(encoded).decode('utf-8')
    with open('/home/goida/label/site/api.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Файл успешно восстановлен. Размер: {len(content)} символов")
except Exception as e:
    print(f"Ошибка: {e}")
    sys.exit(1)

