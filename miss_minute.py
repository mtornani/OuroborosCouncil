"""
MISS MINUTE - Sistema di prioritizzazione progetti AI
======================================================
"Il tempo è prezioso. Io lo gestisco per te."

Ispirato a Miss Minute di Loki - sempre presente, sempre informata.

USO:
    python miss_minute.py              # Status rapido
    python miss_minute.py --full       # Report completo
    python miss_minute.py --focus      # Mostra solo priorità 1
    python miss_minute.py --update     # Aggiorna stato progetti
    python miss_minute.py --daemon     # Modalità sempre attiva (watch)
    
GEMINI CLI:
    gemini "miss minute status" 
    gemini "cosa devo fare oggi?"
"""

import os
import sys
import yaml
import json
from datetime import datetime, timedelta
from pathlib import Path
import time

# Configurazione
BASE_DIR = Path("D:/AI")
CONFIG_DIR = BASE_DIR / ".miss_minute"
PRIORITIES_FILE = CONFIG_DIR / "priorities.yaml"
LOG_FILE = CONFIG_DIR / "activity_log.json"

# Colori ANSI per output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

def load_priorities():
    """Carica configurazione priorità"""
    if PRIORITIES_FILE.exists():
        with open(PRIORITIES_FILE, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return None

def save_log(action, project=None, details=None):
    """Salva attività nel log"""
    log = []
    if LOG_FILE.exists():
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            log = json.load(f)
    
    log.append({
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "project": project,
        "details": details
    })
    
    # Mantieni solo ultimi 100 log
    log = log[-100:]
    
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

def days_until(date_str):
    """Calcola giorni mancanti a una data"""
    target = datetime.strptime(date_str, "%Y-%m-%d")
    delta = target - datetime.now()
    return delta.days

def get_project_health(project_path):
    """Analizza salute di un progetto"""
    path = Path(project_path)
    if not path.exists():
        return "missing", "❌ Cartella non trovata"
    
    # Controlla ultimo file modificato
    latest_mod = None
    file_count = 0
    
    for f in path.rglob("*"):
        if f.is_file() and not any(x in str(f) for x in ['.git', '__pycache__', '.venv', 'node_modules']):
            file_count += 1
            mtime = f.stat().st_mtime
            if latest_mod is None or mtime > latest_mod:
                latest_mod = mtime
    
    if latest_mod:
        days_ago = (datetime.now() - datetime.fromtimestamp(latest_mod)).days
        if days_ago == 0:
            return "active", f"✅ Modificato oggi ({file_count} files)"
        elif days_ago < 7:
            return "recent", f"🟡 Modificato {days_ago}g fa ({file_count} files)"
        else:
            return "stale", f"🔴 Fermo da {days_ago}g ({file_count} files)"
    
    return "unknown", f"❓ Stato sconosciuto ({file_count} files)"

def print_header():
    """Stampa header Miss Minute"""
    print(f"""
{Colors.CYAN}{Colors.BOLD}
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   ⏰  MISS MINUTE - Priority Management System                   ║
║                                                                  ║
║   "Il tempo è prezioso. Non sprecarlo sui progetti sbagliati."  ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
{Colors.END}""")
    print(f"   📅 {datetime.now().strftime('%A %d %B %Y, %H:%M')}")
    print()

def print_deadlines(config):
    """Stampa deadline imminenti"""
    print(f"{Colors.BOLD}{Colors.YELLOW}📌 DEADLINE IMMINENTI{Colors.END}")
    print("─" * 50)
    
    deadlines = []
    for name, info in config.get('deadlines', {}).items():
        days = days_until(info['date'])
        deadlines.append((days, name, info))
    
    deadlines.sort(key=lambda x: x[0])
    
    for days, name, info in deadlines:
        if days < 0:
            color = Colors.RED
            status = f"⚠️  SCADUTO da {-days}g"
        elif days <= 7:
            color = Colors.RED
            status = f"🔥 {days} giorni"
        elif days <= 14:
            color = Colors.YELLOW
            status = f"⚡ {days} giorni"
        else:
            color = Colors.GREEN
            status = f"📆 {days} giorni"
        
        print(f"   {color}{status}{Colors.END} │ {info['description']}")
        print(f"            │ Richiede: {', '.join(info.get('requires', []))}")
    
    print()

def print_focus_mode(config):
    """Stampa focus mode attivo"""
    focus = config.get('focus_mode', {})
    if focus.get('enabled'):
        print(f"{Colors.BOLD}{Colors.RED}🎯 FOCUS MODE ATTIVO{Colors.END}")
        print("─" * 50)
        print(f"   Progetto: {Colors.BOLD}{focus.get('current_focus')}{Colors.END}")
        print(f"   {focus.get('message')}")
        print()

def print_projects(config, full=False):
    """Stampa stato progetti"""
    print(f"{Colors.BOLD}{Colors.BLUE}📂 PROGETTI{Colors.END}")
    print("─" * 50)
    
    projects = config.get('projects', {})
    sorted_projects = sorted(projects.items(), key=lambda x: x[1].get('priority', 99))
    
    for name, info in sorted_projects:
        priority = info.get('priority', 99)
        status = info.get('status', 'unknown')
        
        # Colore in base a priorità
        if priority == 1:
            pcolor = Colors.RED + Colors.BOLD
            picon = "🔴"
        elif priority == 2:
            pcolor = Colors.YELLOW
            picon = "🟡"
        elif priority <= 4:
            pcolor = Colors.CYAN
            picon = "🔵"
        else:
            pcolor = Colors.END
            picon = "⚪"
        
        # Health check
        health_status, health_msg = get_project_health(info.get('path', ''))
        
        print(f"   {picon} {pcolor}[P{priority}] {name}{Colors.END}")
        print(f"      Status: {status} │ {health_msg}")
        
        if full or priority <= 2:
            print(f"      Next: {info.get('next_action', 'N/A')}")
            if info.get('blockers'):
                print(f"      Blockers: {', '.join(info['blockers'])}")
        
        print()

def print_recommendation(config):
    """Stampa raccomandazione azione"""
    focus = config.get('focus_mode', {})
    projects = config.get('projects', {})
    
    # Trova progetto priorità 1
    top_project = None
    for name, info in projects.items():
        if info.get('priority') == 1:
            top_project = (name, info)
            break
    
    if top_project:
        name, info = top_project
        print(f"{Colors.BOLD}{Colors.GREEN}💡 COSA FARE ADESSO{Colors.END}")
        print("─" * 50)
        print(f"""
   Progetto: {Colors.BOLD}{name}{Colors.END}
   Path: {info.get('path')}
   
   Azione: {info.get('next_action')}
   
   Comando suggerito:
   {Colors.CYAN}cd "{info.get('path')}" && code .{Colors.END}
""")

def main():
    """Entry point"""
    args = sys.argv[1:] if len(sys.argv) > 1 else []
    
    config = load_priorities()
    if not config:
        print(f"{Colors.RED}❌ Configurazione non trovata. Crea {PRIORITIES_FILE}{Colors.END}")
        return
    
    print_header()
    
    if '--focus' in args:
        print_focus_mode(config)
        print_recommendation(config)
    elif '--full' in args:
        print_deadlines(config)
        print_focus_mode(config)
        print_projects(config, full=True)
        print_recommendation(config)
    elif '--daemon' in args:
        print(f"{Colors.YELLOW}👁️ Modalità watch attiva. Ctrl+C per uscire.{Colors.END}")
        try:
            while True:
                os.system('cls' if os.name == 'nt' else 'clear')
                print_header()
                print_focus_mode(config)
                print_recommendation(config)
                print(f"\n{Colors.CYAN}Prossimo refresh: 60s{Colors.END}")
                time.sleep(60)
                config = load_priorities()  # Ricarica config
        except KeyboardInterrupt:
            print(f"\n{Colors.GREEN}👋 Miss Minute va in pausa. Buon lavoro!{Colors.END}")
    else:
        # Default: status rapido
        print_deadlines(config)
        print_focus_mode(config)
        print_projects(config, full=False)
        print_recommendation(config)
    
    save_log("status_check")

if __name__ == "__main__":
    main()
