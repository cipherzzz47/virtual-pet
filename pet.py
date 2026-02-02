# Install: pip install requests pillow
import requests
import tkinter as tk
from PIL import Image, ImageTk, ImageSequence
import subprocess
import threading
import os
import winreg

# ────────────────────────────────────────
GIF_PATH = "Post by @felinerin · 1 image.gif"
CHAT_URL = "https://grok.com/"
WINDOW_GEOMETRY = "480x720+200+50"
TRANSPARENT_COLOR = "#ff00ff"

# ────────────────────────────────────────
# Find Microsoft Edge path
def find_edge_path():
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"
        )
        path = winreg.QueryValue(key, None)
        winreg.CloseKey(key)
        return path
    except:
        return None


EDGE_PATH = find_edge_path()

# ────────────────────────────────────────
# Global menu references
main_menu = None
games_submenu = None

# ────────────────────────────────────────
# Main transparent window + GIF pet
root = tk.Tk()
root.overrideredirect(True)
root.attributes("-topmost", True)
root.geometry(WINDOW_GEOMETRY)
root.configure(bg=TRANSPARENT_COLOR)
root.wm_attributes("-transparentcolor", TRANSPARENT_COLOR)

# Load & animate GIF
im = Image.open(GIF_PATH)
frames = [ImageTk.PhotoImage(frame.copy().convert("RGBA"))
          for frame in ImageSequence.Iterator(im)]

gif_label = tk.Label(
    root,
    image=frames[0],
    bg=TRANSPARENT_COLOR,
    borderwidth=0,
    highlightthickness=0
)
gif_label.place(x=0, y=0, relwidth=1, relheight=1)

def animate(i=0):
    gif_label.configure(image=frames[i % len(frames)])
    root.after(im.info.get("duration", 100), animate, i + 1)

animate()

# ────────────────────────────────────────
# Window dragging
def start_drag(event):
    root._drag_x = event.x_root - root.winfo_x()
    root._drag_y = event.y_root - root.winfo_y()

def do_drag(event):
    x = event.x_root - root._drag_x
    y = event.y_root - root._drag_y
    root.geometry(f"+{x}+{y}")

gif_label.bind("<Button-1>", start_drag)
gif_label.bind("<B1-Motion>", do_drag)

# ────────────────────────────────────────
# Right-click → quick kill menu
def show_kill_menu(event):
    global kill_menu
    if 'kill_menu' in globals() and kill_menu.winfo_exists():
        kill_menu.destroy()

    kill_menu = tk.Toplevel(root)
    kill_menu.overrideredirect(True)
    kill_menu.attributes("-topmost", True)
    kill_menu.geometry(f"+{event.x_root}+{event.y_root}")
    kill_menu.configure(bg="#2b2b2b")

    tk.Button(kill_menu, text="Kill Pet", command=root.destroy,
              bg="#2b2b2b", fg="red", width=15).pack(pady=2)
    tk.Button(kill_menu, text="Cancel", command=kill_menu.destroy,
              bg="#2b2b2b", fg="white", width=15).pack(pady=2)

gif_label.bind("<Button-3>", show_kill_menu)

# ────────────────────────────────────────
# Games list (edit paths here~)
GAMES = {
    "Game 1": r"C:\path\to\game1.exe",
    "Game 2": r"C:\path\to\game2.exe",
    "Game 3": r"C:\path\to\game3.exe",
}

# ────────────────────────────────────────
# Menu actions
def open_grok():
    if EDGE_PATH:
        subprocess.Popen([EDGE_PATH, '--new-window', CHAT_URL])
    close_all_menus()

def open_youtube():
    if EDGE_PATH:
        subprocess.Popen([EDGE_PATH, '--new-window', "https://youtube.com"])
    close_all_menus()

def launch_game(game_path):
    try:
        subprocess.Popen(game_path)
    except FileNotFoundError:
        print(f"Game not found: {game_path}")
    # ^ intentionally **does not** close menus so you can launch many ♡

# ────────────────────────────────────────
# Menu closing helpers
def close_submenu_only():
    """Kept just for you~ even if unused right now"""
    global games_submenu
    if games_submenu and games_submenu.winfo_exists():
        games_submenu.destroy()
        games_submenu = None

def close_main_menu():
    global main_menu
    if main_menu and main_menu.winfo_exists():
        main_menu.destroy()
        main_menu = None

def close_all_menus():
    close_submenu_only()
    close_main_menu()





# ────────────────────────────────────────
# Modern dropdown menu (main + games submenu)
def create_menu(event, is_submenu=False):
    global main_menu, games_submenu

    # Close previous one of the same type
    if is_submenu and games_submenu and games_submenu.winfo_exists():
        games_submenu.destroy()
    if not is_submenu and main_menu and main_menu.winfo_exists():
        main_menu.destroy()

    window = tk.Toplevel(root)
    window.overrideredirect(True)
    window.attributes("-topmost", True)
    window.attributes("-alpha", 0.98)
    window.configure(bg="#1e1e2e")

    # Position
    offset_x = 140 if is_submenu else 0
    offset_y = 50  if is_submenu else 0
    window.geometry(f"+{event.x_root + offset_x}+{event.y_root + offset_y}")

    frame = tk.Frame(window, bg="#1e1e2e", bd=0)
    frame.pack(padx=8, pady=8)

    if is_submenu:
        buttons = [
            (name + " 🎮", lambda p=path: launch_game(p))
            for name, path in GAMES.items()
        ]
        buttons.append(("← Back", window.destroy))
        target = games_submenu = window
    else:
        buttons = [
            ("Grok Chat ♡", open_grok),
            ("YouTube ▶", open_youtube),
            ("Launch Game 🎮", lambda: create_menu(event, is_submenu=True)),
            ("Close ×", close_all_menus),
        ]
        target = main_menu = window

    for text, cmd in buttons:
        btn = tk.Button(
            frame,
            text=text,
            command=cmd,
            bg="#31334a",
            fg="#cdd6f4",
            activebackground="#89b4fa",
            activeforeground="#1e1e2e",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            padx=20, pady=10,
            width=18,
            cursor="hand2"
        )
        btn.pack(pady=3, fill="x")

        btn.bind("<Enter>", lambda e, b=btn: b.configure(bg="#89b4fa", fg="#1e1e2e"))
        btn.bind("<Leave>",  lambda e, b=btn: b.configure(bg="#31334a", fg="#cdd6f4"))

# ────────────────────────────────────────
# Double-click → open main menu
gif_label.bind("<Double-Button-1>", lambda e: create_menu(e))

# ────────────────────────────────────────
root.mainloop()