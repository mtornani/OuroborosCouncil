import time
import json
import yaml
import os
from pathlib import Path
from datetime import datetime, timedelta
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from winotify import Notification, audio

# CONFIGURAZIONE
BASE_DIR = Path("D:/AI")
CONFIG_DIR = BASE_DIR / ".miss_minute"
PRIORITIES_FILE = CONFIG_DIR / "priorities.yaml"
STATE_FILE = CONFIG_DIR / "state.json"

# IGNORE PATTERNS
IGNORE_DIRS = {'.git', '.venv', '__pycache__', 'node_modules', '.idea', '.vscode', 'dist', 'build'}
IGNORE_EXTENSIONS = {'.tmp', '.log', '.pyc'}

class MissMinuteWatcher(FileSystemEventHandler):
    def __init__(self):
        self.last_check = datetime.now()
        self.state = self.load_state()
        self.config = self.load_config()
        self.last_notification_time = {} # Per evitare spam

    def load_config(self):
        if PRIORITIES_FILE.exists():
            with open(PRIORITIES_FILE, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        return {}

    def load_state(self):
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            "last_activity": {},
            "current_project": None,
            "session_start": datetime.now().isoformat()
        }

    def save_state(self):
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)

    def get_project_from_path(self, path):
        path = Path(path)
        try:
            rel = path.relative_to(BASE_DIR)
            if len(rel.parts) > 0:
                project = rel.parts[0]
                if project.startswith('.'): return None # Ignora cartelle config
                return project
        except ValueError:
            return None
        return None

    def on_any_event(self, event):
        if event.is_directory: return
        
        path = Path(event.src_path)
        
        # Filtri rumore
        if any(part in IGNORE_DIRS for part in path.parts): return
        if path.suffix in IGNORE_EXTENSIONS: return
        
        project = self.get_project_from_path(path)
        if not project: return
        
        now = datetime.now().isoformat()
        self.state['last_activity'][project] = now
        self.state['current_project'] = project
        self.state['active_file'] = str(path)
        
        # Jarvis Feature: Check for error logs
        if "log" in path.name.lower() or path.suffix == ".err":
            self.analyze_error(path)
            
        self.save_state()

    def analyze_error(self, path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.readlines()[-10:] # Ultime 10 righe
                if any(x in str(content).upper() for x in ["ERROR", "EXCEPTION", "CRITICAL", "FAILED"]):
                    self.send_notification("🚨 ERROR DETECTED", f"I found something in {path.name}, sugar! Need help?", level='warning')
        except: pass

    def check_git_status(self, project):
        # Jarvis Feature: Git monitoring
        project_path = BASE_DIR / project
        if (project_path / ".git").exists():
            try:
                import subprocess
                res = subprocess.check_output(["git", "status", "--short"], cwd=project_path).decode()
                if res.strip():
                    self.state['git_dirty'] = True
                    return len(res.splitlines())
            except: pass
        return 0

    def send_notification(self, title, msg, level='info', sound=audio.Default):
        # Anti-spam: max 1 notifica ogni 5 min per stesso tipo (salvo emergenza)
        last = self.last_notification_time.get(title)
        if last and level != 'emergency':
            if (datetime.now() - last).seconds < 300:
                return

        toast = Notification(
            app_id="Miss Minute",
            title=title,
            msg=msg,
            duration="short" if level != 'emergency' else "long"
        )
        
        if level in ['warning', 'emergency']:
            toast.set_audio(audio.LoopingAlarm if level == 'emergency' else audio.SystemHand, loop=False)
        else:
            toast.set_audio(audio.Silent, loop=False)
            
        toast.show()
        self.last_notification_time[title] = datetime.now()

    def check_rules(self):
        """Valuta regole comportamentali Jarvis-style"""
        now = datetime.now()
        config = self.load_config()
        current = self.state.get('current_project')
        
        # 1. GIT CHECK
        if current:
            dirty_files = self.check_git_status(current)
            if dirty_files > 10 and now.minute % 15 == 0:
                self.send_notification("📦 GIT ALERT", f"You have {dirty_files} uncommitted files in {current}. Don't lose your work, sugar!", level='info')
        # Regola: Se priorità 1 ferma da > 3h in orario lavoro (9-18)
        if 9 <= now.hour <= 18:
            ob1_last = self.state['last_activity'].get('ob1-scout')
            if ob1_last:
                last_time = datetime.fromisoformat(ob1_last)
                delta_hours = (now - last_time).seconds / 3600 + (now - last_time).days * 24
                
                if delta_hours > 6:
                    self.send_notification("⚠️ OB1 TRASCURATO", "Fermo da > 6 ore. Chiellini aspetta.", level='warning')
                elif delta_hours > 3:
                    self.send_notification("👀 OB1 Status", "Fermo da 3 ore. Tutto ok?", level='info')

        # 2. CHECK DEADLINES
        deadlines = config.get('deadlines', {})
        for name, info in deadlines.items():
            date = datetime.strptime(info['date'], "%Y-%m-%d")
            days = (date - now).days
            
            if days == 0:
                self.send_notification("🚨 DEADLINE OGGI", f"{name.upper()} SCADE OGGI!", level='emergency')
            elif days <= 2 and now.hour == 10 and now.minute == 0: # Reminder mattina
                self.send_notification("🔥 URGENTE", f"{name}: mancano {days} giorni", level='warning')

        # 3. CHECK WRONG FOCUS
        current = self.state.get('current_project')
        focus_mode = config.get('focus_mode', {})
        
        if focus_mode.get('enabled'):
            target = focus_mode.get('current_project')
            if current and current != target and current not in ['miss_minute']:
                 # Se sta lavorando su altro da > 5 min (qui semplificato a istantaneo per ora)
                 # In futuro: buffer di tempo
                 self.send_notification("🎯 FOCUS VIOLATION", f"Stai su {current}. Torna su {target}.", level='warning')

def run_watcher():
    print(f"👁️ Miss Minute Watcher attivo su {BASE_DIR}")
    event_handler = MissMinuteWatcher()
    observer = Observer()
    observer.schedule(event_handler, str(BASE_DIR), recursive=True)
    observer.start()
    
    try:
        while True:
            time.sleep(60) # Loop principale ogni 60s
            event_handler.check_rules()
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    run_watcher()
