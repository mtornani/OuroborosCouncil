import tkinter as tk
import yaml
import random
import math
from datetime import datetime
from pathlib import Path

# Configurazioni
PRIORITIES_FILE = Path("d:/AI/_archivio/miss_minute/priorities.yaml")
COLOR_BG = "#0f1216"
COLOR_PRIMARY = "#ffffff"
COLOR_DIM = "#737373"
COLOR_ALERT = "#ff2a2a"
COLOR_WARN = "#fca311"

class TacticalHUD:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Miss Minute Tactical HUD")
        
        self.width = 340
        self.height = 160
        x = int(self.root.winfo_screenwidth() - self.width - 40)
        y = int(self.root.winfo_screenheight() - self.height - 60)
        
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.90)
        self.root.configure(bg=COLOR_BG)
        
        self.canvas = tk.Canvas(self.root, width=self.width, height=self.height, bg=COLOR_BG, highlightthickness=1, highlightbackground="#333333")
        self.canvas.pack(fill="both", expand=True)
        
        self.canvas.bind('<Button-1>', self.start_move)
        self.canvas.bind('<ButtonRelease-1>', self.stop_move)
        self.canvas.bind('<B1-Motion>', self.on_move)
        self.canvas.bind('<Button-3>', self.show_menu)
        
        self.menu = tk.Menu(self.root, tearoff=0, bg=COLOR_BG, fg=COLOR_PRIMARY)
        self.menu.add_command(label="TERMINATE HUD", command=self.root.destroy)
        
        self.frame_count = 0
        self.current_focus = "AWAITING LINK..."
        self.urgent_deadline = ""
        self.days_left = 999
        self.quotes_normal = [
            "Direttore, il tempo scorre.",
            "Rimango in ascolto sul background.",
            "Niente divagazioni collaterali, mi raccomando.",
            "P1 è l'unica cosa che conta oggi.",
            "Sembra che tu sia bloccato. Serve Gemini?",
            "Conscientiousness al 25%. Ti tengo a freno io.",
            "Zitto e programma.",
            "Pensa all'obiettivo finale.",
            "Sto monitorando il tuo YAML. Torna su OB1."
        ]
        self.quotes_urgent = [
            "SCADENZA IMMINENTE. Smetti di fare altro.",
            "Non c'è tempo per progetti secondari.",
            "Chiudi tutto il resto. SUBITO.",
            "Stiamo per fallire su P1 se non acceleri."
        ]
        
        self.current_quote = "Initialization sequence..."
        self.quote_timer = 200 # Frames
        self.type_index = 0
        
        self.x = 0
        self.y = 0
        
        self.update_data()
        self.animate()
        
        self.root.mainloop()

    def update_data(self):
        try:
            if PRIORITIES_FILE.exists():
                with open(PRIORITIES_FILE, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    
                self.current_focus = data.get('focus_mode', {}).get('current_focus', 'N/A')
                
                # Trova la deadline più vicina
                min_days = 999
                nearest_name = ""
                deadlines = data.get('deadlines', {})
                for name, info in deadlines.items():
                    target = datetime.strptime(info['date'], "%Y-%m-%d")
                    delta = (target - datetime.now()).days
                    if delta < min_days:
                        min_days = delta
                        nearest_name = name
                
                self.days_left = min_days
                self.urgent_deadline = info['description'] if min_days != 999 else "NONE"
                
        except Exception as e:
            pass
            
        self.root.after(10000, self.update_data)

    def change_quote(self):
        # Sceglie una frase in base all'emergenza (e in base alla Behavioral Briefing)
        if self.days_left <= 7:
            self.current_quote = random.choice(self.quotes_urgent)
        else:
            self.current_quote = random.choice(self.quotes_normal)
            
        self.type_index = 0

    def draw_ui(self):
        self.canvas.delete("ui")
        
        # Sfondo griglia minimal
        for i in range(0, self.width, 20):
            self.canvas.create_line(i, 0, i, self.height, fill="#15181c", tags="ui")
        for i in range(0, self.height, 20):
            self.canvas.create_line(0, i, self.width, i, fill="#15181c", tags="ui")
            
        # Cornici interne
        self.canvas.create_rectangle(5, 5, self.width-5, self.height-5, outline="#222222", tags="ui")
        
        # Testo top level
        self.canvas.create_text(15, 20, text="MISS_MINUTE // TACTICAL WIDGET", fill=COLOR_DIM, font=("Courier", 8, "bold"), anchor="w", tags="ui")
        
        # Status "Recording" dot
        if self.frame_count % 20 < 10:
            self.canvas.create_rectangle(self.width-20, 15, self.width-12, 23, fill=COLOR_ALERT, outline="", tags="ui")
            
        # Info primaria
        color_focus = COLOR_PRIMARY if self.days_left > 7 else COLOR_ALERT
        self.canvas.create_text(15, 50, text="FOCUS:", fill=COLOR_DIM, font=("Courier", 10, "bold"), anchor="w", tags="ui")
        self.canvas.create_text(70, 50, text=str(self.current_focus).upper(), fill=color_focus, font=("Courier", 10, "bold"), anchor="w", tags="ui")
        
        if self.days_left != 999:
            status_text = f"D-{self.days_left}" if self.days_left > 0 else "SCADUTO"
            color_dl = COLOR_WARN if self.days_left <= 14 else COLOR_DIM
            color_dl = COLOR_ALERT if self.days_left <= 0 else color_dl
            self.canvas.create_text(15, 75, text="DEADLINE:", fill=COLOR_DIM, font=("Courier", 10, "bold"), anchor="w", tags="ui")
            self.canvas.create_text(100, 75, text=f"{status_text}", fill=color_dl, font=("Courier", 10, "bold"), anchor="w", tags="ui")

        # Typewriter Quote Console
        self.canvas.create_rectangle(15, 100, self.width-15, 145, fill="#0a0c0f", outline="#1c2026", tags="ui")
        
        if self.type_index < len(self.current_quote):
            self.type_index += 0.5 # Rallento un filo l'effetto macchina da scrivere
            
        displayed = self.current_quote[:int(self.type_index)]
        # Simulazione cursore terminale
        cursor = " _" if (self.frame_count % 10 < 5) else ""
        
        # Uso un verde/cyan neon per far staccare la "Voce" di Miss Minute
        self.canvas.create_text(22, 110, text=f"> {displayed}{cursor}", fill="#00ffcc", font=("Courier", 9), anchor="nw", 
                                width=self.width-40, tags="ui")

    def animate(self):
        self.frame_count += 1
        
        self.quote_timer -= 1
        if self.quote_timer <= 0:
            self.change_quote()
            self.quote_timer = random.randint(300, 500) # Dai 15 ai 25 secondi circa
            
        self.draw_ui()
        self.root.after(50, self.animate)

    def start_move(self, event):
        self.x = event.x
        self.y = event.y

    def stop_move(self, event):
        self.x = None
        self.y = None

    def on_move(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")

    def show_menu(self, event):
        self.menu.post(event.x_root, event.y_root)

if __name__ == "__main__":
    TacticalHUD()
