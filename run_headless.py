"""
run_headless.py — Optimus Background Daemon Wrapper
===================================================
Initializes the FastAPI backend silently inside a background daemon context
without allocating an explicit Windows console window block. Wires the tray
icon with interactive contextual menus.
"""
import os
import subprocess
import sys
import threading
import time
from PIL import Image, ImageDraw

try:
    import pystray
    from pystray import MenuItem as item
except ImportError:
    print("pystray not installed. Run: pip install pystray")
    sys.exit(1)

# Global reference to the backend process
backend_process = None
frontend_process = None

def create_image():
    """Generates a simple neon blue O (Optimus) icon for the system tray."""
    width = 64
    height = 64
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    # Draw a blue circle
    dc.ellipse((8, 8, width - 8, height - 8), outline=(0, 255, 255, 255), width=4)
    # Draw an inner dot
    dc.ellipse((28, 28, 36, 36), fill=(0, 255, 255, 255))
    return image

def check_port(port):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def start_backend():
    global backend_process
    if check_port(8000):
        print("Port 8000 in use.")
        os._exit(1)
    # Use pythonw or start detached so it doesn't open a console window
    # sys.executable points to the current venv python
    cmd = [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"]
    
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW

    log_file = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", "core.log"), "a")
    backend_process = subprocess.Popen(
        cmd,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stdout=log_file,
        stderr=log_file,
        creationflags=creationflags
    )

def start_frontend():
    global frontend_process
    if check_port(8080):
        print("Port 8080 in use.")
        os._exit(1)
    cmd = [sys.executable, "-m", "http.server", "8080", "-d", "frontend"]
    
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW

    frontend_process = subprocess.Popen(
        cmd,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags
    )

def open_dashboard(icon, item):
    import webbrowser
    # Assuming frontend is served via an extension like Live Server, or Nginx on 8080
    webbrowser.open("http://127.0.0.1:8080")

def view_logs(icon, item):
    # Just opens the backend folder for now, or a specific log file
    os.startfile(os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

def terminate_core(icon, item):
    global backend_process, frontend_process
    if backend_process:
        backend_process.terminate()
        backend_process.wait()
    if frontend_process:
        frontend_process.terminate()
        frontend_process.wait()
    icon.stop()
    sys.exit(0)

def monitor_processes(icon):
    while True:
        time.sleep(2)
        if backend_process and backend_process.poll() is not None:
            icon.notify("Optimus Core crashed!")
            time.sleep(1)
            os._exit(1)
        if frontend_process and frontend_process.poll() is not None:
            icon.notify("Optimus UI crashed!")
            time.sleep(1)
            os._exit(1)

ngrok_url = None
ngrok_auth = None

def start_ngrok():
    global ngrok_url, ngrok_auth
    try:
        from pyngrok import ngrok
        import secrets
        import string
        
        # Generate secure random password
        alphabet = string.ascii_letters + string.digits
        password = ''.join(secrets.choice(alphabet) for i in range(12))
        ngrok_auth = f"optimus:{password}"
        
        # Start tunnel to frontend port 8080
        tunnel = ngrok.connect(8080, "http", auth=ngrok_auth)
        ngrok_url = tunnel.public_url
        
        # Write to desktop for user convenience
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "remote_access.txt"), "w") as f:
            f.write(f"Optimus Remote Access\nURL: {ngrok_url}\nUsername: optimus\nPassword: {password}\n")
            
    except Exception as e:
        print(f"Ngrok failed to start: {e}")

def show_remote_access(icon, item):
    import ctypes
    if ngrok_url:
        msg = f"URL: {ngrok_url}\nAuth: {ngrok_auth}"
        ctypes.windll.user32.MessageBoxW(0, msg, "Optimus Remote Access", 0x40)
    else:
        ctypes.windll.user32.MessageBoxW(0, "Ngrok tunnel is not active.", "Optimus Remote Access", 0x10)

def main():
    # Start the FastAPI server in a background process
    t1 = threading.Thread(target=start_backend, daemon=True)
    t1.start()
    
    # Start the Frontend static server
    t2 = threading.Thread(target=start_frontend, daemon=True)
    t2.start()
    
    # Start Ngrok Remote Tunnel
    t3 = threading.Thread(target=start_ngrok, daemon=True)
    t3.start()
    
    # Give it a second to bind
    time.sleep(1)

    # Setup the system tray icon
    menu = (
        item("Open Dashboard", open_dashboard, default=True),
        item("Show Remote Access", show_remote_access),
        item("View Core Logs", view_logs),
        item("Terminate Assistant Core", terminate_core)
    )
    
    icon = pystray.Icon("Optimus", create_image(), "Optimus OS Core", menu)
    
    # Process death monitoring
    threading.Thread(target=monitor_processes, args=(icon,), daemon=True).start()
    
    icon.run()

if __name__ == "__main__":
    main()
