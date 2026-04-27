import subprocess
import sys
import time

def main():
    print("Starting TTS Server...")
    tts_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.tts_server:app", "--host", "127.0.0.1", "--port", "15000"]
    )
    
    time.sleep(2)  # 给 TTS 服务一点启动时间
    
    print("Starting Main Server...")
    main_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "15005"]
    )

    try:
        # 阻塞主进程，直到用户按 Ctrl+C
        tts_process.wait()
        main_process.wait()
    except KeyboardInterrupt:
        print("\nShutting down both servers...")
        tts_process.terminate()
        main_process.terminate()
        tts_process.wait()
        main_process.wait()
        print("Servers stopped.")

if __name__ == "__main__":
    main()
