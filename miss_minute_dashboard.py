import http.server
import socketserver
import json
import yaml
import os
from pathlib import Path
from datetime import datetime

PORT = 8080
CONFIG_FILE = Path("priorities.yaml")

class MissMinuteHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            try:
                if CONFIG_FILE.exists():
                    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f)
                    
                    # Aggiungo timestamp server
                    data['last_update'] = datetime.now().isoformat()
                    self.wfile.write(json.dumps(data).encode())
                else:
                    self.wfile.write(json.dumps({"error": "Config not found"}).encode())
            except Exception as e:
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        
        elif self.path == '/':
            self.path = '/miss_minute_dashboard.html'
            return http.server.SimpleHTTPRequestHandler.do_GET(self)
        
        else:
            return http.server.SimpleHTTPRequestHandler.do_GET(self)

print(f"⏰ Miss Minute HUD attiva su http://localhost:{PORT}")
print("Minimizza questa finestra e tieni d'occhio la dashboard.")

with socketserver.TCPServer(("", PORT), MissMinuteHandler) as httpd:
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nChiusura dashboard...")
