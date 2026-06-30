import os
import sys
import threading
import time
import uvicorn
from pystray import Icon, Menu, MenuItem
from PIL import Image

def start_backend():
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000)

# Generate a secure boot token for WebSocket authentication
import secrets
os.environ["OPTIMUS_BOOT_TOKEN"] = secrets.token_urlsafe(32)

def open_dashboard(icon, item):
    import webbrowser
    token = os.environ["OPTIMUS_BOOT_TOKEN"]
    webbrowser.open(f"http://127.0.0.1:8000/?token={token}")

def view_logs(icon, item):
    os.startfile(os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

def quit_app(icon, item):
    icon.stop()
    os._exit(0)

ngrok_url = None
ngrok_auth = None

def start_ngrok():
    global ngrok_url, ngrok_auth
    try:
        from pyngrok import ngrok
        import string
        
        alphabet = string.ascii_letters + string.digits
        password = ''.join(secrets.choice(alphabet) for i in range(12))
        ngrok_auth = f"optimus:{password}"
        
        tunnel = ngrok.connect(8000, "http", auth=ngrok_auth)
        ngrok_url = tunnel.public_url
        
        full_url = f"{ngrok_url}/?token={os.environ['OPTIMUS_BOOT_TOKEN']}"
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "remote_access.txt"), "w") as f:
            f.write(f"Optimus Remote Access\nURL: {full_url}\nUsername: optimus\nPassword: {password}\n")
            
    except Exception as e:
        print(f"Ngrok failed to start: {e}")

def show_remote_access(icon, item):
    import ctypes
    if ngrok_url:
        full_url = f"{ngrok_url}/?token={os.environ['OPTIMUS_BOOT_TOKEN']}"
        msg = f"URL: {full_url}\nAuth: {ngrok_auth}"
        ctypes.windll.user32.MessageBoxW(0, msg, "Optimus Remote Access", 0x40)
    else:
        ctypes.windll.user32.MessageBoxW(0, "Ngrok tunnel is not active.", "Optimus Remote Access", 0x10)

def main():
    # Create system tray icon
    try:
        image = Image.open("icon.ico")
    except:
        image = Image.new('RGB', (64, 64), color = (0, 0, 0))
        
    menu = Menu(
        MenuItem('Open Dashboard', open_dashboard, default=True),
        MenuItem('Remote Access Info', show_remote_access),
        MenuItem('View Logs', view_logs),
        MenuItem('Quit', quit_app)
    )
    icon = Icon("Optimus", image, "Optimus Neural Interface", menu)
    
    # Start the FastAPI server in a background process
    t1 = threading.Thread(target=start_backend, daemon=True)
    t1.start()
    
    # Start Ngrok Remote Tunnel
    #t3 = threading.Thread(target=start_ngrok, daemon=True)
    #t3.start()
    
    time.sleep(1)
    
    secure_url = f"http://127.0.0.1:8000/?token={os.environ['OPTIMUS_BOOT_TOKEN']}"
    print("\n" + "="*60)
    print(" OPTIMUS CORE IS ONLINE")
    print("="*60)
    print(f" Access your dashboard securely here:")
    print(f" -> {secure_url}")
    
    icon.run()

if __name__ == '__main__':
    main()
