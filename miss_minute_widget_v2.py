import tkinter as tk
from tkinter import ttk
import yaml
import os
from pathlib import Path
import webbrowser
from datetime import datetime
import math
import random
import sys
import traceback

# LOGGING
LOG_FILE = Path("D:/AI/.miss_minute/widget_debug.log")

def log_msg(msg):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"{datetime.now()}: {msg}\n")
    except:
        pass

# CONFIG
REFRESH_RATE = 50 # ms for animations
DATA_UPDATE_RATE = 5000 # ms for logic
CONFIG_DIR = Path("D:/AI/.miss_minute")
PRIORITIES_FILE = CONFIG_DIR / "priorities.yaml"
DASHBOARD_URL = "http://localhost:8080"

# COLORS - RETRO FUTURISTIC 50s
COLOR_ORANGE = "#FF8C00" 
COLOR_PEACH = "#FFCC80"
COLOR_BROWN = "#5D4037"
COLOR_WHITE = "#FFFFFF"
COLOR_GLOW = "#FFB347"
COLOR_BLACK = "#1A1A1A" # Dark but not pure black

class MissMinuteWidget:
    def __init__(self):
        log_msg("Initializing Miss Minute Widget V2 (Retro-Futuristic)...")
        self.root = tk.Tk()
        self.root.title("Miss Minute")
        
        # Window setup
        self.width = 300
        self.height = 300
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = int(screen_width - self.width - 50)
        y = int(screen_height - self.height - 100)
        
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.0) # Start invisible for entrance animation
        self.root.wm_attributes("-transparentcolor", "black") 
        self.root.configure(bg='black')

        self.canvas = tk.Canvas(self.root, width=self.width, height=self.height, bg='black', highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # State variables
        self.offset_y = 0
        self.anim_frame = 0
        self.blink_timer = 0
        self.is_blinking = False
        self.current_expression = "happy" # happy, thinking, alert, worried
        self.status_text = "Hey there!"
        self.deadline_text = ""
        self.opacity = 0.0
        
        # Interaction
        self.canvas.bind('<Button-1>', self.start_move)
        self.canvas.bind('<ButtonRelease-1>', self.stop_move)
        self.canvas.bind('<B1-Motion>', self.on_move)
        self.canvas.bind('<Double-Button-1>', self.open_dashboard)
        self.canvas.bind('<Button-3>', self.show_menu)
        
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Open Dashboard", command=self.open_dashboard_cmd)
        self.menu.add_separator()
        self.menu.add_command(label="Exit", command=self.root.destroy)

        self.x = 0
        self.y = 0

        # Start loops
        self.entrance_animation()
        self.update_logic()
        self.animate()
        
        log_msg("Widget V2 Running")
        self.root.mainloop()

    def entrance_animation(self):
        if self.opacity < 0.95:
            self.opacity += 0.05
            self.root.attributes('-alpha', self.opacity)
            self.root.after(30, self.entrance_animation)

    def draw_character(self):
        self.canvas.delete("char")
        cx, cy = self.width // 2, self.height // 2
        
        # Floating motion
        self.offset_y = math.sin(self.anim_frame * 0.1) * 10
        cy += self.offset_y

        # 1. Glow (Multi-layered for "soft" look)
        for i in range(5):
            alpha_glow = ["#FFD180", "#FFB347", "#FFA726", "#FF9800", "#FB8C00"]
            self.canvas.create_oval(cx-75-i*2, cy-75-i*2, cx+75+i*2, cy+75+i*2, fill="", outline=alpha_glow[i], width=2, tags=("char", "glow"))
        
        # 2. Arms (Rubber Hose)
        arm_swing = math.sin(self.anim_frame * 0.08) * 15
        # Left Arm
        self.canvas.create_line(cx-60, cy+10, cx-95, cy+35+arm_swing, cx-120, cy+15, 
                                smooth=True, width=7, fill=COLOR_BROWN, tags="char")
        # Right Arm
        self.canvas.create_line(cx+60, cy+10, cx+95, cy+35-arm_swing, cx+120, cy+15, 
                                smooth=True, width=7, fill=COLOR_BROWN, tags="char")
        
        # 3. Hands (Gloves - Classic 50s)
        self.canvas.create_oval(cx-130, cy, cx-110, cy+25, fill=COLOR_WHITE, outline=COLOR_BROWN, width=2, tags="char")
        self.canvas.create_oval(cx+110, cy, cx+130, cy+25, fill=COLOR_WHITE, outline=COLOR_BROWN, width=2, tags="char")

        # 4. Legs
        self.canvas.create_line(cx-30, cy+65, cx-45, cy+95, cx-55, cy+110, smooth=True, width=7, fill=COLOR_BROWN, tags="char")
        self.canvas.create_line(cx+30, cy+65, cx+45, cy+95, cx+55, cy+110, smooth=True, width=7, fill=COLOR_BROWN, tags="char")
        
        # 5. Feet (Large cartoon shoes)
        self.canvas.create_oval(cx-70, cy+105, cx-40, cy+120, fill=COLOR_BROWN, tags="char")
        self.canvas.create_oval(cx+40, cy+105, cx+70, cy+120, fill=COLOR_BROWN, tags="char")

        # 6. Face (Main Body)
        # Outer Rim (Peach)
        self.canvas.create_oval(cx-72, cy-72, cx+72, cy+72, fill=COLOR_PEACH, outline=COLOR_BROWN, width=3, tags="char")
        # Inner Face (Orange)
        self.canvas.create_oval(cx-64, cy-64, cx+64, cy+64, fill=COLOR_ORANGE, outline="", tags="char")
        
        # 7. Clock Ticks
        for i in range(12):
            angle = math.radians(i * 30 - 90) # Start from 12 o'clock
            x1 = cx + math.cos(angle) * 52
            y1 = cy + math.sin(angle) * 52
            x2 = cx + math.cos(angle) * 62
            y2 = cy + math.sin(angle) * 62
            self.canvas.create_line(x1, y1, x2, y2, fill=COLOR_BROWN, width=3, tags="char")

        # 8. Eyes
        eye_y_off = -15
        eye_x_off = 25
        
        if self.is_blinking:
            # Closed eyes (thick lines)
            self.canvas.create_line(cx-eye_x_off-12, cy+eye_y_off, cx-eye_x_off+12, cy+eye_y_off, fill=COLOR_BROWN, width=4, tags="char")
            self.canvas.create_line(cx+eye_x_off-12, cy+eye_y_off, cx+eye_x_off+12, cy+eye_y_off, fill=COLOR_BROWN, width=4, tags="char")
        else:
            # Open eyes (Large Ovals)
            self.canvas.create_oval(cx-eye_x_off-14, cy+eye_y_off-22, cx-eye_x_off+14, cy+eye_y_off+22, fill=COLOR_WHITE, outline=COLOR_BROWN, width=2, tags="char")
            self.canvas.create_oval(cx+eye_x_off-14, cy+eye_y_off-22, cx+eye_x_off+14, cy+eye_y_off+22, fill=COLOR_WHITE, outline=COLOR_BROWN, width=2, tags="char")
            
            # Pupils (Pac-Man style)
            look_x = (self.root.winfo_pointerx() - self.root.winfo_x() - cx) / 100
            look_y = (self.root.winfo_pointery() - self.root.winfo_y() - cy) / 100
            look_x = max(-8, min(8, look_x))
            look_y = max(-8, min(8, look_y))
            
            for ex in [-eye_x_off, eye_x_off]:
                px, py = cx + ex + look_x, cy + eye_y_off + look_y
                # Draw black oval
                self.canvas.create_oval(px-6, py-10, px+6, py+10, fill=COLOR_BLACK, outline="", tags="char")
                # Draw white highlight (reflection)
                self.canvas.create_oval(px-3, py-6, px+1, py-2, fill=COLOR_WHITE, outline="", tags="char")

        # 9. Mouth
        m_y = cy + 28
        if self.current_expression == "happy":
            self.canvas.create_arc(cx-25, m_y-15, cx+25, m_y+15, start=190, extent=160, fill="", outline=COLOR_BROWN, width=4, style="arc", tags="char")
        elif self.current_expression == "thinking":
            self.canvas.create_line(cx-18, m_y, cx+18, m_y, fill=COLOR_BROWN, width=4, tags="char")
        elif self.current_expression == "alert":
            self.canvas.create_oval(cx-12, m_y-8, cx+12, m_y+12, fill=COLOR_BROWN, outline="", tags="char")
        elif self.current_expression == "worried":
            self.canvas.create_arc(cx-22, m_y, cx+22, m_y+25, start=10, extent=160, fill="", outline=COLOR_BROWN, width=4, style="arc", tags="char")

        # 10. Status & Deadline (Retro Font Style)
        if self.status_text:
            self.canvas.create_text(cx, cy - 110, text=self.status_text.upper(), font=("Courier", 10, "bold"), fill=COLOR_PEACH, tags="char")
        if self.deadline_text:
            self.canvas.create_text(cx, cy + 135, text=self.deadline_text, font=("Courier", 11, "bold"), fill=COLOR_ORANGE, tags="char")

    def animate(self):
        self.anim_frame += 1
        
        # Blink logic
        self.blink_timer -= 1
        if self.blink_timer <= 0:
            if self.is_blinking:
                self.is_blinking = False
                self.blink_timer = random.randint(40, 100)
            else:
                self.is_blinking = True
                self.blink_timer = 3 # Blink duration
        
        self.draw_character()
        self.root.after(REFRESH_RATE, self.animate)

    def update_logic(self):
        try:
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

            if min_days < 0:
                self.status_text = "OH NO! EXPIRED!"
                self.deadline_text = f"CRITICAL: {nearest_name.upper()}"
                self.current_expression = "worried"
            elif min_days <= 3:
                self.status_text = "Hurry up, sugar!"
                self.deadline_text = f"{min_days} days left for {nearest_name}"
                self.current_expression = "alert"
            elif min_days <= 7:
                self.status_text = "Check your timeline!"
                self.deadline_text = f"{min_days} days left"
                self.current_expression = "thinking"
            else:
                focus = data.get('focus_mode', {}).get('current_focus', 'Relax')
                self.status_text = f"Focus: {focus}"
                self.deadline_text = f"Next: {min_days} days"
                self.current_expression = "happy"
                
        except Exception as e:
            log_msg(f"Logic Error: {e}")

        self.root.after(DATA_UPDATE_RATE, self.update_logic)

    def load_data(self):
        try:
            if PRIORITIES_FILE.exists():
                with open(PRIORITIES_FILE, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
            return {}
        except:
            return {}

    # Interaction methods
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
        
    def open_dashboard_cmd(self):
        webbrowser.open(DASHBOARD_URL)

    def show_menu(self, event):
        self.menu.post(event.x_root, event.y_root)

if __name__ == "__main__":
    try:
        MissMinuteWidget()
    except Exception as e:
        log_msg(f"CRITICAL CRASH: {e}")
        print(traceback.format_exc())
