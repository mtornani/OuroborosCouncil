import tkinter as tk
import yaml
import os
from pathlib import Path
import webbrowser
from datetime import datetime
import sys
import traceback

# LOGGING
LOG_FILE = Path("D:/AI/.miss_minute/widget_debug.log")

def log_msg(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.now()}: {msg}\n")

# CONFIG
REFRESH_RATE = 2000 # ms
CONFIG_DIR = Path("D:/AI/.miss_minute")
PRIORITIES_FILE = CONFIG_DIR / "priorities.yaml"
DASHBOARD_URL = "http://localhost:8080"

# COLORS & STYLE - PIP-BOY EDITION
TVA_ORANGE = "#00ff41" # Fosforo verde
TVA_BG = "#000000" 
TVA_GLOW = "#003b00"
PIP_GREEN_DARK = "#003b00"
PIP_GREEN_BRIGHT = "#00ff41"

class MissMinuteWidget:
    def __init__(self):
        log_msg("Initializing Widget (Tactical Pip-Boy)...")
        self.root = tk.Tk()
        self.root.title("Miss Minute")
        
        # Window setup - More horizontal for a "wrist-mounted" feel
        width = 320
        height = 180
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = int(screen_width - width - 40)
        y = int(screen_height - height - 80)
        
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.92)
        self.root.wm_attributes("-transparentcolor", "black") 
        self.root.configure(bg='black')

        self.canvas = tk.Canvas(self.root, width=width, height=height, bg='black', highlightthickness=0)
        self.canvas.pack()

        self.draw_ui()
        
        # Events
        self.canvas.bind('<Button-1>', self.start_move)
        self.canvas.bind('<ButtonRelease-1>', self.stop_move)
        self.canvas.bind('<B1-Motion>', self.on_move)
        self.canvas.bind('<Double-Button-1>', self.open_dashboard)
        self.canvas.bind('<Button-3>', self.show_menu)
        
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Open Dashboard", command=lambda: webbrowser.open(DASHBOARD_URL))
        self.menu.add_command(label="Exit", command=self.root.destroy)

        self.x = 0
        self.y = 0

        self.update_data()
        log_msg("Starting Mainloop")
        self.root.mainloop()

    def draw_ui(self):
        self.canvas.delete("all")
        w, h = 320, 180
        
        # Glow effect per i bordi esterni
        self.canvas.create_rectangle(5, 5, w-5, h-5, outline=PIP_GREEN_DARK, width=1)
        self.canvas.create_rectangle(8, 8, w-8, h-8, outline=PIP_GREEN_BRIGHT, width=2)
        
        # Top Header - Ad alto contrasto (Sfondo pieno per leggibilità)
        self.canvas.create_rectangle(10, 10, w-10, 35, fill=PIP_GREEN_BRIGHT, outline="")
        self.canvas.create_text(20, 22, text="MISS MINUTE :: TACTICAL HUD", font=("Consolas", 10, "bold"), fill="black", anchor="w")
        self.canvas.create_text(w-20, 22, text="v2.1", font=("Consolas", 9, "bold"), fill="black", anchor="e")

        # Background Blocks per i testi (Finto semi-trasparente scuro)
        self.canvas.create_rectangle(140, 45, w-15, 95, fill="#051005", outline=PIP_GREEN_DARK)
        self.canvas.create_rectangle(140, 105, w-15, 155, fill="#051005", outline=PIP_GREEN_DARK)

        # Left Side: Miss Minute "Aperture"
        self.canvas.create_oval(30, 50, 130, 150, outline=PIP_GREEN_BRIGHT, width=2)
        self.canvas.create_line(80, 50, 80, 150, fill=PIP_GREEN_DARK)
        self.canvas.create_line(30, 100, 130, 100, fill=PIP_GREEN_DARK)
        
        # Digital Eyes
        self.canvas.create_rectangle(55, 75, 70, 90, fill=PIP_GREEN_BRIGHT, outline="")
        self.canvas.create_rectangle(90, 75, 105, 90, fill=PIP_GREEN_BRIGHT, outline="")
        
        # Labels e Valori con font più grandi e chiari
        self.canvas.create_text(150, 58, text="[ STATUS ]", font=("Consolas", 8, "bold"), fill=PIP_GREEN_BRIGHT, anchor="w")
        self.lbl_msg_id = self.canvas.create_text(150, 78, text="SCANNING...", font=("Consolas", 12, "bold"), fill=PIP_GREEN_BRIGHT, anchor="w")
        
        self.canvas.create_text(150, 118, text="[ TIMELINE ]", font=("Consolas", 8, "bold"), fill=PIP_GREEN_BRIGHT, anchor="w")
        self.lbl_deadline_id = self.canvas.create_text(150, 138, text="---", font=("Consolas", 14, "bold"), fill=PIP_GREEN_BRIGHT, anchor="w")

        # Footer
        self.canvas.create_text(w-20, h-18, text="RADIATION_LEVEL: 0.00", font=("Consolas", 7), fill=PIP_GREEN_DARK, anchor="e")


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

    def open_dashboard(self, event):
        webbrowser.open(DASHBOARD_URL)
        
    def show_menu(self, event):
        self.menu.post(event.x_root, event.y_root)

    def load_data(self):
        try:
            if PRIORITIES_FILE.exists():
                with open(PRIORITIES_FILE, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
            return {}
        except Exception as e:
            log_msg(f"Error loading yaml: {e}")
            return {}

    def update_data(self):
        data = self.load_data()
        deadlines = data.get('deadlines', {})
        min_days = 999
        nearest_name = ""
        
        for name, info in deadlines.items():
            try:
                target = datetime.strptime(info['date'], "%Y-%m-%d")
                delta = (target - datetime.now()).days
                if delta < min_days:
                    min_days = delta
                    nearest_name = name
            except:
                pass

        # Update Waveform (Visual feedback)
        self.canvas.delete("wave")
        points = []
        for x in range(50, 110, 4):
            import random
            amp = 2 if min_days > 7 else 8 # Più agitata se scadenze vicine
            offset = random.randint(-amp, amp)
            points.extend([x, 125 + offset])
        self.canvas.create_line(points, fill=PIP_GREEN_BRIGHT, smooth=True, width=2, tags="wave")

        if min_days < 0:
             self.canvas.itemconfig(self.lbl_msg_id, text="CRITICAL_ERR")
             self.canvas.itemconfig(self.lbl_deadline_id, text=f"EXPIRED", fill="#ff0000")
        elif min_days <= 7:
             self.canvas.itemconfig(self.lbl_msg_id, text="URGENT_MSG")
             self.canvas.itemconfig(self.lbl_deadline_id, text=f"{min_days}D UNTIL_0", fill=PIP_GREEN_BRIGHT)
        else:
             focus = data.get('focus_mode', {}).get('current_focus', 'RELAX')
             self.canvas.itemconfig(self.lbl_msg_id, text=focus.upper())
             self.canvas.itemconfig(self.lbl_deadline_id, text=f"{min_days} DAYS", fill=PIP_GREEN_BRIGHT)
        
        self.root.after(REFRESH_RATE, self.update_data)

if __name__ == "__main__":
    try:
        MissMinuteWidget()
    except Exception as e:
        log_msg(f"CRITICAL CRASH: {e}")
        log_msg(traceback.format_exc())

