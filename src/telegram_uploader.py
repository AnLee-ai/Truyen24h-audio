import os
import requests
from src import config

def send_audio_to_telegram(audio_path: str, caption: str, title: str = None, srt_path: str = None) -> bool:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("[WARNING] Telegram credentials are not configured. Skipping upload.")
        return False
        
    if not os.path.exists(audio_path):
        print(f"[ERROR] Audio file does not exist: {audio_path}")
        return False
        
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendAudio"
    print(f"[INFO] Uploading audio to Telegram: {config.TELEGRAM_CHAT_ID}...")
    
    try:
        with open(audio_path, 'rb') as audio_file:
            files = {'audio': (os.path.basename(audio_path), audio_file, 'audio/mpeg')}
            data = {
                'chat_id': config.TELEGRAM_CHAT_ID,
                'caption': caption,
                'parse_mode': 'Markdown',
                'performer': 'Truyện 24h Audio'
            }
            if title:
                data['title'] = title
                
            # ĐÃ SỬA: Tăng timeout lên 300 giây để tránh nghẽn mạng khi tải file lớn (>10MB)
            response = requests.post(url, data=data, files=files, timeout=300)
            
        if response.status_code == 200:
            print("[INFO] Audio uploaded successfully to Telegram.")
            if srt_path and os.path.exists(srt_path):
                print(f"[INFO] Uploading subtitle SRT: {srt_path}...")
                send_document_to_telegram(srt_path, f"Phụ đề chương: {title or 'SRT'}")
            return True
        else:
            print(f"[ERROR] Telegram upload failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"[ERROR] Error during Telegram upload: {e}")
        return False

def send_document_to_telegram(doc_path: str, caption: str) -> bool:
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendDocument"
    try:
        with open(doc_path, 'rb') as doc_file:
            files = {'document': (os.path.basename(doc_path), doc_file, 'application/octet-stream')}
            data = {
                'chat_id': config.TELEGRAM_CHAT_ID,
                'caption': caption,
                'parse_mode': 'Markdown'
            }
            response = requests.post(url, data=data, files=files, timeout=60)
        return response.status_code == 200
    except Exception as e:
        print(f"[ERROR] Subtitle upload failed: {e}")
        return False
