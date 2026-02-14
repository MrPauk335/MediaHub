import socket
import http.server
import socketserver
import threading
import json
import os
import time
import webbrowser
import uuid

class MediaNetwork:
    """
    Модуль для работы с локальной сетью: 
    - UDP Discovery (поиск соседей)
    - HTTP Server (раздача контента)
    """
    def __init__(self, http_port=8888, udp_port=9999):
        self.http_port = http_port
        self.udp_port = udp_port
        self.lan_name = socket.gethostname()
        self.session_id = str(uuid.uuid4())
        self.neighbors = {} # {ip_port: {name: str, last_seen: float}}
        self.on_refresh_cb = None
        self.save_path = None

    def start(self, save_path, refresh_callback):
        self.save_path = save_path
        self.on_refresh_cb = refresh_callback
        
        # 1. Запуск HTTP сервера
        threading.Thread(target=self._run_http, daemon=True).start()
        # 2. Запуск UDP слушателя
        threading.Thread(target=self._run_discovery, daemon=True).start()
        # 3. Первичный поиск
        self.broadcast_presence()

    def _run_http(self):
        try:
            os.chdir(self.save_path)
            handler = http.server.SimpleHTTPRequestHandler
            # Allow address reuse to prevent "Address already in use" errors during quick restarts
            socketserver.TCPServer.allow_reuse_address = True
            with socketserver.TCPServer(("", self.http_port), handler) as httpd:
                httpd.serve_forever()
        except Exception as e:
            print(f"[Network] HTTP Error: {e}")

    def _run_discovery(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', self.udp_port))
        
        my_ip = socket.gethostbyname(socket.gethostname())
        
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                msg = json.loads(data.decode())
                
                # Игнорируем приветствия от самого себя (по session_id)
                if msg.get("sid") == self.session_id: continue
                
                if msg.get("type") == "hello":
                    # Используем связку IP + SID как ключ, чтобы видеть несколько окон на одном ПК
                    peer_key = f"{addr[0]}_{msg['sid'][:8]}"
                    self.neighbors[peer_key] = {"name": msg["name"], "ip": addr[0], "last_seen": time.time()}
                    
                    if self.on_refresh_cb: 
                        self.on_refresh_cb()
                    
                    if msg.get("broadcast", False):
                        resp = {"type": "hello", "name": self.lan_name, "sid": self.session_id, "broadcast": False}
                        sock.sendto(json.dumps(resp).encode(), addr)
            except:
                pass

    def broadcast_presence(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        msg = json.dumps({"type": "hello", "name": self.lan_name, "sid": self.session_id, "broadcast": True})
        sock.sendto(msg.encode(), ('<broadcast>', self.udp_port))

    def browse_neighbor(self, ip):
        webbrowser.open(f"http://{ip}:{self.http_port}")
