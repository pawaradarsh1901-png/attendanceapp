from waitress import serve
from flask_app import app
import logging
import socket

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('waitress')

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

if __name__ == "__main__":
    host = '0.0.0.0'
    port = 5000
    local_ip = get_ip()
    
    print("\n" + "="*50)
    print("🚀 SYNCPOINT ATTENDANCE SERVER IS STARTING")
    print("="*50)
    print(f"🏠 Local Access:   http://localhost:{port}")
    print(f"🌐 Network Access: http://{local_ip}:{port}")
    print("="*50)
    print("Press Ctrl+C to stop the server\n")

    serve(app, host=host, port=port, threads=6)
