import tkinter as tk
import yaml
import json
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
REFRESH_RATE = 30 # ~33 FPS per fluidità superiore
DATA_UPDATE_RATE = 3000
CONFIG_DIR = Path("D:/AI/.miss_minute")
PRIORITIES_FILE = CONFIG_DIR / "priorities.yaml"
STATE_FILE = CONFIG_DIR / "state.json"
DASHBOARD_URL = "http://localhost:8080"

# COLORS - VIBRANT 50s NEON
COLOR_ORANGE_NEON = "#FF4500"
COLOR_ORANGE_BRIGHT = "#FF8C00"
COLOR_PEACH_VIBRANT = "#FFDAB9"
COLOR_BROWN_DEEP = "#211007"
COLOR_WHITE = "#FFFFFF"
COLOR_BLACK = "#000000"

PHRASES = {
    "idle": ["JUST WATCHING YOU WORK, SUGAR! 😊", "NEED A HAND, HONEY?", "I'M ALWAYS HERE FOR YOU! ❤️", "TIME IS SLIPPING AWAY!", "LET'S KEEP THE TIMELINE CLEAN!"],
    "distracted": ["OH SWEETIE, {target} IS WAITING! 😊", "THAT'S NOT ON THE SCHEDULE, SUGAR!", "FOCUS, HONEY! THE TVA IS WATCHING!", "LET'S GET BACK TO WORK!"],
    "focused": ["LOOK AT YOU GO, SUGAR! ✨", "PROUD OF YOU, HONEY!", "YOU'RE DOING GREAT! ❤️"],
    "stuck": ["STUCK AGAIN, SUGAR? NEED HELP?", "OH HONEY, DON'T BE SHY! 😊", "NEED GEMINI TO TAKE A LOOK?"],
    "startup": ["HEY THERE! READY TO WORK? 😊", "MISSED ME, SUGAR? ❤️"]
}

class MissMinuteWidget:
    def __init__(self):
        log_msg("Initializing Free-Roam Miss Minute...")
        self.root = tk.Tk()
        self.root.title("Miss Minute")
        
        self.width, self.height = 450, 450
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        self.root.geometry(f"{self.width}x{self.height}+{int(screen_width-self.width-20)}+{int(screen_height-self.height-60)}")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.0) 
        self.root.wm_attributes("-transparentcolor", "black") 
        self.root.configure(bg='black')

        self.canvas = tk.Canvas(self.root, width=self.width, height=self.height, bg='black', highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # ANIMATION STATES (Independent parameters)
        self.anim_frame = 0
        self.is_blinking = False
        self.blink_timer = 40
        self.current_expression = "happy"
        self.status_text = random.choice(PHRASES["startup"])
        self.deadline_text = ""
        self.opacity = 0.0
        self.ray_angle = 0
        self.jump_y = 0
        
        # Autonomous Gaze
        self.look_x, self.look_y = 0, 0
        self.target_look_x, self.target_look_y = 0, 0
        self.gaze_timer = 0
        
        # Physics / Inertia
        self.tilt = 0
        self.vel_x = 0
        self.last_x = self.root.winfo_x()
        
        # Interaction
        self.x, self.y = 0, 0
        self.canvas.bind('<Button-1>', self.start_move)
        self.canvas.bind('<ButtonRelease-1>', self.stop_move)
        self.canvas.bind('<B1-Motion>', self.on_move)
        self.canvas.bind('<Double-Button-1>', self.open_dashboard)
        self.canvas.bind('<Button-3>', self.show_menu)

        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Open Dashboard", command=self.open_dashboard_cmd)
        self.menu.add_separator()
        self.menu.add_command(label="Restart System", command=self.restart_all)
        self.menu.add_command(label="Exit All (Total)", command=self.exit_all)
        self.menu.add_command(label="Close Widget Only", command=self.root.destroy)
        
        self.entrance_animation()
        self.update_logic()
        self.animate()
        self.root.mainloop()

    def entrance_animation(self):
        if self.opacity < 0.98:
            self.opacity += 0.05
            self.root.attributes('-alpha', self.opacity)
            self.root.after(30, self.entrance_animation)

    def draw_character(self):
        self.canvas.delete("char")
        cx, cy = self.width // 2, self.height // 2
        
        # 1. CORE DYNAMICS (Squash, Stretch & Tilt)
        t = self.anim_frame * 0.1
        self.float_y = math.sin(t) * 20 + self.jump_y
        self.tilt = math.sin(t * 0.5) * 5 + (self.vel_x * 0.5)
        s_y = 1.0 + math.cos(t) * 0.06
        s_x = 1.0 - math.cos(t) * 0.06
        cy += self.float_y

        # 2. AUTONOMOUS RAYS (Pulsing & Drifting)
        self.ray_angle += 0.015
        num_rays = 14
        for i in range(num_rays):
            angle = self.ray_angle + (i * (2 * math.pi / num_rays))
            # Raggi che cambiano lunghezza indipendentemente
            r_len = 180 + math.sin(t * 0.7 + i) * 25
            rx, ry = cx + math.cos(angle) * r_len, cy + math.sin(angle) * r_len
            self.canvas.create_line(cx, cy, rx, ry, fill="#2E1500", width=6, tags="char")
            self.canvas.create_line(cx, cy, rx, ry, fill="#5E2F00", width=2, tags="char")

        # 3. PROCEDURAL LIMBS (Indipendent wave for each limb)
        # Arms
        for i, side in enumerate([-1, 1]):
            phase = t * 1.2 + (i * math.pi)
            bend = math.sin(phase) * 25
            # Rubber hose path
            x1, y1 = cx + (60 * side), cy + 10
            x2, y2 = cx + (100 * side) + bend, cy + 40 + bend
            x3, y3 = cx + (135 * side) + bend*0.5, cy + 20 + bend*0.3
            self.canvas.create_line(x1, y1, x2, y2, x3, y3, smooth=True, width=8, fill=COLOR_BROWN_DEEP, tags="char")
            # Gloves with lag
            self.canvas.create_oval(x3-15, y3-15, x3+15, y3+15, fill=COLOR_WHITE, outline=COLOR_BROWN_DEEP, width=2, tags="char")
            for l in [-5, 0, 5]: self.canvas.create_line(x3+l, y3-7, x3+l, y3+7, fill=COLOR_BROWN_DEEP, tags="char")

        # Legs
        for i, side in enumerate([-1, 1]):
            phase = t * 0.8 + (i * math.pi * 0.5)
            sway = math.sin(phase) * 15
            lx1, ly1 = cx + (35 * side), cy + 70
            lx2, ly2 = cx + (50 * side) + sway, cy + 100
            lx3, ly3 = cx + (65 * side) + sway*1.2, cy + 130
            self.canvas.create_line(lx1, ly1, lx2, ly2, lx3, ly3, smooth=True, width=8, fill=COLOR_BROWN_DEEP, tags="char")
            # Shoes
            self.canvas.create_oval(lx3-25, ly3-12, lx3+25, ly3+15, fill=COLOR_BROWN_DEEP, outline=COLOR_ORANGE_BRIGHT, width=1, tags="char")

        # 4. THE CLOCK FACE (With Tilt)
        rx, ry = 72 * s_x, 72 * s_y
        # Glow layers
        for glow_i in range(5, 0, -1):
            g_rad = rx + (glow_i * 12)
            alpha_c = ["#1A0800", "#4D1A00", "#802B00", "#B33C00", "#E64D00"][glow_i-1]
            self.canvas.create_oval(cx-g_rad, cy-g_rad, cx+g_rad, cy+g_rad, fill="", outline=alpha_c, width=2, tags="char")

        # Main Body
        self.canvas.create_oval(cx-rx-3, cy-ry-3, cx+rx+3, cy+ry+3, fill=COLOR_PEACH_VIBRANT, outline=COLOR_BROWN_DEEP, width=2, tags="char")
        self.canvas.create_oval(cx-rx, cy-ry, cx+rx, cy+ry, fill=COLOR_ORANGE_NEON, outline="", tags="char")
        
        # Clock Ticks (Affected by tilt and squash)
        for i in range(12):
            angle = math.radians(i * 30 - 90 + self.tilt)
            tx1 = cx + math.cos(angle) * 52 * s_x
            ty1 = cy + math.sin(angle) * 52 * s_y
            tx2 = cx + math.cos(angle) * 64 * s_x
            ty2 = cy + math.sin(angle) * 64 * s_y
            self.canvas.create_line(tx1, ty1, tx2, ty2, fill=COLOR_BROWN_DEEP, width=3, tags="char")

        # 5. EYES & GAZE (Autonomous wandering)
        self.update_gaze()
        ey, ex = -15, 25
        for side in [-1, 1]:
            # White
            ex_pos = cx + (ex * side) * s_x
            ey_pos = cy + ey * s_y
            self.canvas.create_oval(ex_pos-16, ey_pos-25, ex_pos+16, ey_pos+25, fill=COLOR_WHITE, outline=COLOR_BROWN_DEEP, width=2, tags="char")
            # Blinking
            if self.is_blinking:
                self.canvas.create_rectangle(ex_pos-17, ey_pos-26, ex_pos+17, ey_pos+26, fill=COLOR_ORANGE_NEON, outline="", tags="char")
                self.canvas.create_line(ex_pos-15, ey_pos, ex_pos+15, ey_pos, fill=COLOR_BROWN_DEEP, width=4, tags="char")
            else:
                # Pupil Pacman with autonomous look
                px, py = ex_pos + self.look_x, ey_pos + self.look_y
                self.canvas.create_oval(px-8, py-12, px+8, py+12, fill=COLOR_BLACK, tags="char")
                self.canvas.create_oval(px-5, py-8, px+2, py-3, fill=COLOR_WHITE, tags="char")

        # 6. MOUTH
        m_pos = cy + 25 * s_y
        if self.current_expression == "happy":
            self.canvas.create_arc(cx-30, m_pos-15, cx+30, m_pos+15, start=190, extent=160, fill="", outline=COLOR_BROWN_DEEP, width=5, style="arc", tags="char")
        elif self.current_expression == "alert":
            self.canvas.create_oval(cx-15, m_pos-5, cx+15, m_pos+20, fill=COLOR_BROWN_DEEP, tags="char")

        # 7. BUBBLES (With floating offset)
        if self.status_text: self.draw_vibrant_bubble(cx, cy - 160, self.status_text, "#FFD700", True)
        if self.deadline_text: self.draw_vibrant_bubble(cx, cy + 185, self.deadline_text, "#FF4500", False)

    def update_gaze(self):
        # Wandering logic
        self.gaze_timer -= 1
        if self.gaze_timer <= 0:
            # Randomly decide to look at mouse or wander
            if random.random() < 0.6:
                mx, my = self.root.winfo_pointerx() - self.root.winfo_x(), self.root.winfo_pointery() - self.root.winfo_y()
                self.target_look_x = max(-12, min(12, (mx - (self.width//2)) / 15))
                self.target_look_y = max(-12, min(12, (my - (self.height//2)) / 15))
            else:
                self.target_look_x = random.uniform(-10, 10)
                self.target_look_y = random.uniform(-10, 10)
            self.gaze_timer = random.randint(30, 100)
        
        # Smooth transition to target
        self.look_x += (self.target_look_x - self.look_x) * 0.1
        self.look_y += (self.target_look_y - self.look_y) * 0.1

    def animate(self):
        self.anim_frame += 1
        
        # Physics update (Inertia based on window movement)
        curr_x = self.root.winfo_x()
        self.vel_x = (curr_x - self.last_x) * 0.5
        self.last_x = curr_x
        
        # Blink logic
        self.blink_timer -= 1
        if self.blink_timer <= 0:
            self.is_blinking = not self.is_blinking
            self.blink_timer = 4 if self.is_blinking else random.randint(30, 120)
            
        if self.jump_y < 0: self.jump_y += 1.5
        
        self.draw_character()
        self.root.after(REFRESH_RATE, self.animate)

    def update_logic(self):
        try:
            config = self.load_yaml(PRIORITIES_FILE)
            state = self.load_json(STATE_FILE)
            target = config.get('focus_mode', {}).get('current_focus', 'None')
            current = state.get('current_project', 'None')
            deadlines = config.get('deadlines', {})
            min_days, nearest = 999, ""
            for name, info in deadlines.items():
                d = (datetime.strptime(info['date'], "%Y-%m-%d") - datetime.now()).days
                if d < min_days: min_days, nearest = d, name
            
            git_dirty = state.get('git_dirty', False)
            if min_days < 0: self.status_text, self.current_expression = "OH SUGAR, WE'RE LATE!", "alert"
            elif min_days <= 3: self.status_text, self.current_expression = f"HURRY UP, HONEY! {nearest.upper()}!", "alert"
            elif target != 'None' and current != target and current != 'miss_minute':
                self.status_text = random.choice(PHRASES["distracted"]).format(target=target)
            else:
                if random.random() < 0.15: self.status_text = random.choice(PHRASES["idle"])
            self.deadline_text = f"{nearest}: {min_days}D LEFT" if min_days < 999 else ""
            if git_dirty: self.deadline_text += " | GIT DIRTY 📦"
        except: pass
        self.root.after(DATA_UPDATE_RATE, self.update_logic)

    def draw_vibrant_bubble(self, x, y, text, color, is_top=True):
        pad_x, pad_y = 20, 10
        tw = len(text) * 11
        th = 35
        x1, y1, x2, y2 = x-tw//2-pad_x, y-th//2-pad_y, x+tw//2+pad_x, y+th//2+pad_y
        self.canvas.create_rectangle(x1, y1, x2, y2, fill="#000000", outline="#3E2723", width=3, tags="char")
        for dx, dy in [(-2,-2),(2,-2),(-2,2),(2,2)]:
            self.canvas.create_text(x+dx, y+dy, text=text, font=("Verdana", 13, "bold"), fill="black", tags="char", width=tw+pad_x)
        self.canvas.create_text(x, y, text=text, font=("Verdana", 13, "bold"), fill=color, tags="char", width=tw+pad_x)

    def load_yaml(self, path):
        if not path.exists(): return {}
        with open(path, 'r', encoding='utf-8') as f: return yaml.safe_load(f)
    def load_json(self, path):
        if not path.exists(): return {}
        with open(path, 'r', encoding='utf-8') as f:
            try: return json.load(f)
            except: return {}

    def start_move(self, event): self.x, self.y = event.x, event.y
    def stop_move(self, event): self.x, self.y = None, None
    def on_move(self, event):
        dx, dy = event.x - self.x, event.y - self.y
        new_x = self.root.winfo_x() + dx
        new_y = self.root.winfo_y() + dy
        self.root.geometry(f"+{new_x}+{new_y}")
    def open_dashboard_cmd(self): webbrowser.open(DASHBOARD_URL)
    def open_dashboard(self, event): webbrowser.open(DASHBOARD_URL)
    def show_menu(self, event): self.menu.post(event.x_root, event.y_root)
    def exit_all(self):
        log_msg("System Shutdown.")
        import subprocess
        subprocess.Popen(["taskkill", "/F", "/IM", "python.exe", "/T"])
        self.root.destroy()
    def restart_all(self):
        log_msg("System Restart.")
        import subprocess
        python_exe = sys.executable
        subprocess.Popen([python_exe, "miss_minute_watcher.py"])
        subprocess.Popen([python_exe, "miss_minute_widget.py"])
        self.root.destroy()

if __name__ == "__main__":
    MissMinuteWidget()