import argparse
import sys
import os
import uvicorn
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse

from src import config
from src import database
from src import writer
from src import tts
from src import audio
from src import telegram_uploader

# ĐÃ SỬA: Ghi đè hàm print để tránh lỗi UnicodeEncodeError trên terminal Windows
def safe_print(*args, **kwargs):
    msg = " ".join(str(arg) for arg in args)
    try:
        sys.stdout.write(msg + kwargs.get("end", "\n"))
        sys.stdout.flush()
    except UnicodeEncodeError:
        try:
            encoding = sys.stdout.encoding or 'utf-8'
            sys.stdout.write(msg.encode(encoding, errors='replace').decode(encoding) + kwargs.get("end", "\n"))
            sys.stdout.flush()
        except Exception:
            sys.stdout.write(msg.encode('ascii', errors='replace').decode('ascii') + kwargs.get("end", "\n"))
            sys.stdout.flush()

print = safe_print
# ... phần code khởi chạy API và CLI ở phía sau giữ nguyên ...
