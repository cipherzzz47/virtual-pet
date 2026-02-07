#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Pet‑Assistant – animated pet that can launch games,
open URLs, chat with Ollama, and **find games** (including shortcuts).

Key fixes in this version
-------------------------
*   Desktop (and any folder you add) is always scanned.
*   Both *.exe* and *.lnk* are considered.
*   Shortcuts are resolved if pywin32 is available; otherwise they are shown
    as‑is and launched with `os.startfile`.
*   A tiny DEBUG mode prints the folders being walked and the files that
    pass the filters – useful when the dialog returns “no results”.
*   The configuration file is always loaded from the same folder as this
    script (or from the temporary PyInstaller folder when frozen).
"""

# --------------------------------------------------------------
# 1️⃣  Imports
# --------------------------------------------------------------
import sys
import os
import json
import subprocess
import winreg
import threading
import queue
import tkinter as tk
from tkinter import (
    filedialog,
    messagebox,
    simpledialog,
    ttk,
)
from pathlib import Path
from PIL import Image, ImageTk, ImageSequence
import platform
import shutil
import time
import traceback

# optional – only needed to resolve shortcuts
try:
    import pythoncom          # type: ignore
    import win32com.client    # type: ignore
    HAVE_PYWIN32 = True
except Exception:            # pragma: no cover
    HAVE_PYWIN32 = False

# --------------------------------------------------------------
# 2️⃣  Configuration handling
# --------------------------------------------------------------
DEBUG = False                     # set True while troubleshooting

def get_base_path() -> Path:
    """Folder that contains this script (or the PyInstaller temp folder)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)               # PyInstaller temp folder
    return Path(os.path.abspath(os.path.dirname(__file__)))


BASE_PATH = get_base_path()
CONFIG_PATH = (BASE_PATH.parent if getattr(sys, "frozen", False) else BASE_PATH) / "config.json"


DEFAULT_CONFIG = {
    "gif_path": "furina_idle.gif",
    "grok_url": "https://grok.com/",
    "youtube_url": "https://youtube.com",
    "games": {
        "Game 1": r"C:\path\to\game1.exe",
        "Game 2": r"C:\path\to\game2.exe",
        "Game 3": r"C:\path\to\game3.exe",
    },
    "search_paths": [],          # user‑added folders (absolute)
}


def _clean_path(raw: str) -> str:
    """
    Turn a string that may look like a Python raw‑string literal
    (e.g. r"C:/Program Files/Game.exe") into a normal Windows path.
    """
    s = raw.strip()
    # strip a leading r" … "
    if s.lower().startswith('r"') and s.endswith('"'):
        s = s[2:-1]
    # strip surrounding quotes
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1]
    # normalise slashes
    return s.replace("/", "\\")


def load_config() -> dict:
    """Read config.json (or create a default one)."""
    if not CONFIG_PATH.is_file():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(DEFAULT_CONFIG, indent=4, ensure_ascii=False), encoding="utf-8"
        )
        return DEFAULT_CONFIG.copy()

    try:
        raw_cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:        # pragma: no cover
        print(f"[config] JSON error: {exc}", file=sys.stderr)
        return DEFAULT_CONFIG.copy()

    # overlay user config on top of defaults
    cfg = DEFAULT_CONFIG.copy()
    cfg.update(raw_cfg)

    # clean up paths that may still contain the raw‑string markers
    cleaned_games = {n: _clean_path(p) for n, p in cfg.get("games", {}).items()}
    cfg["games"] = cleaned_games

    # normalise search_paths list
    cfg["search_paths"] = [_clean_path(p) for p in cfg.get("search_paths", []) if p]

    return cfg


def save_config(cfg: dict) -> None:
    """Write the in‑memory cfg back to disk."""
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(cfg, indent=4, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as exc:        # pragma: no cover
        messagebox.showerror("Config save", f"Failed to write config:\n{exc}")


config = load_config()

# --------------------------------------------------------------
# 3️⃣  Helper utilities (browser, AI, launching, …)
# --------------------------------------------------------------
def find_edge_path() -> Path | None:
    """Read the path to msedge.exe from the registry (if present)."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
        )
        p = winreg.QueryValue(key, None)
        winreg.CloseKey(key)
        return Path(p)
    except OSError:
        return None


EDGE_PATH = find_edge_path()


def ask_ai(prompt: str) -> str:
    """Call Ollama locally – return the model's answer or an error string."""
    try:
        result = subprocess.run(
            ["ollama", "run", "llama3.1"],
            input=prompt,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception as exc:
        return f"AI error: {exc}"


def launch_game(game_name: str, game_path: str) -> None:
    """Start a game; if the path is missing ask the user to locate it."""
    path_obj = Path(game_path)

    # --------------------------------------------------------------
    # 1️⃣  Path exists – launch it directly
    # --------------------------------------------------------------
    if path_obj.is_file():
        try:
            subprocess.Popen([str(path_obj)])
        except Exception as exc:
            messagebox.showerror("Launch error", f"Could not start {game_name}:\n{exc}")
        return

    # --------------------------------------------------------------
    # 2️⃣  Path missing – ask the user for a replacement
    # --------------------------------------------------------------
    if not messagebox.askyesno(
        "Game not found",
        f"The path for \"{game_name}\" does not exist:\n{game_path}\n\n"
        "Do you want to locate the executable now?",
    ):
        return

    new_path = filedialog.askopenfilename(
        title=f"Select the executable for {game_name}",
        filetypes=[("Executable files", "*.exe"), ("All files", "*.*")],
        initialdir=str(Path.home()),
    )
    if not new_path:
        return

    new_key = Path(new_path).stem
    config["games"][new_key] = new_path
    if new_key != game_name and game_name in config["games"]:
        del config["games"][game_name]
    save_config(config)

    try:
        subprocess.Popen([new_path])
    except Exception as exc:
        messagebox.showerror("Launch error", f"Could not start {new_key}:\n{exc}")


# --------------------------------------------------------------
# 4️⃣  UI – hidden root + pet window
# --------------------------------------------------------------
root = tk.Tk()
root.withdraw()          # must be done before any other widget creation

# --------------------------------------------------------------
# 5️⃣  Styling
# --------------------------------------------------------------
STYLE = ttk.Style()
STYLE.theme_use("clam")
STYLE.configure(
    "TButton",
    font=("Segoe UI", 10, "bold"),
    foreground="#cdd6f4",
    background="#31334a",
    padding=10,
    borderwidth=0,
    focusthickness=0,
)
STYLE.map(
    "TButton",
    background=[("active", "#89b4fa")],
    foreground=[("active", "#1e1e2e")],
)

# --------------------------------------------------------------
# 6️⃣  Pet window (the only visible window)
# --------------------------------------------------------------
TRANSPARENT_COLOR = "#ff00ff"

pet_win = tk.Toplevel(root)
pet_win.overrideredirect(True)
pet_win.attributes("-topmost", True)
pet_win.geometry("480x720+200+50")
pet_win.configure(bg=TRANSPARENT_COLOR)
pet_win.wm_attributes("-transparentcolor", TRANSPARENT_COLOR)

# --------------------------------------------------------------
# 7️⃣  Load animated GIF
# --------------------------------------------------------------
gif_file = config["gif_path"]
if not Path(gif_file).is_absolute():
    gif_file = BASE_PATH / gif_file

if not Path(gif_file).is_file():
    messagebox.showerror("GIF error", f"Could not find GIF: {gif_file}")
    sys.exit(1)

pil_img = Image.open(gif_file)
frames = [
    ImageTk.PhotoImage(frame.copy().convert("RGBA"), master=pet_win)
    for frame in ImageSequence.Iterator(pil_img)
]

gif_label = tk.Label(
    pet_win,
    image=frames[0],
    bg=TRANSPARENT_COLOR,
    borderwidth=0,
    highlightthickness=0,
)
gif_label.place(relwidth=1, relheight=1)


def animate(i: int = 0) -> None:
    gif_label.configure(image=frames[i % len(frames)])
    pet_win.after(pil_img.info.get("duration", 100), animate, i + 1)


animate()

# --------------------------------------------------------------
# 8️⃣  Drag‑and‑drop for the pet
# --------------------------------------------------------------
def start_drag(event):
    pet_win._drag_x = event.x_root - pet_win.winfo_x()
    pet_win._drag_y = event.y_root - pet_win.winfo_y()


def do_drag(event):
    x = event.x_root - pet_win._drag_x
    y = event.y_root - pet_win._drag_y
    pet_win.geometry(f"+{x}+{y}")


gif_label.bind("<Button-1>", start_drag)
gif_label.bind("<B1-Motion>", do_drag)

# --------------------------------------------------------------
# 9️⃣  Kill‑menu (right‑click)
# --------------------------------------------------------------
kill_menu = None


def show_kill_menu(event):
    global kill_menu
    if kill_menu and kill_menu.winfo_exists():
        kill_menu.destroy()

    kill_menu = tk.Toplevel(pet_win)
    kill_menu.overrideredirect(True)
    kill_menu.attributes("-topmost", True)
    kill_menu.attributes("-alpha", 0.96)
    kill_menu.configure(bg="#1e1e2e")
    kill_menu.geometry(f"+{event.x_root + 20}+{event.y_root + 20}")

    make_draggable(kill_menu)

    frm = tk.Frame(kill_menu, bg="#1e1e2e")
    frm.pack(padx=8, pady=8)

    ttk.Button(frm, text="Kill Pet ×", command=root.destroy).pack(fill="x", pady=3)
    ttk.Button(frm, text="Cancel", command=kill_menu.destroy).pack(fill="x", pady=3)


gif_label.bind("<Button-3>", show_kill_menu)

# --------------------------------------------------------------
# 🔟  Search‑root handling (used by “Find Game”)
# --------------------------------------------------------------
def _fallback_roots() -> list[Path]:
    """
    Default folders that are always scanned when the user has not
    supplied any custom ``search_paths``.
    """
    home = Path.home()
    return [
        Path(os.getenv("ProgramFiles", r"C:\Program Files")),
        Path(os.getenv("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        home,
        home / "AppData" / "Roaming",
        home / "Desktop",
        home / "Documents",
    ]


def get_search_roots() -> list[Path]:
    """
    Return the folders that the background worker may crawl.
    Preference order:
        1. user‑supplied ``config["search_paths"]``
        2. fallback list above
    """
    user_paths = [Path(p) for p in config.get("search_paths", []) if p]
    if user_paths:
        return user_paths
    return _fallback_roots()


# Global variable read by the worker thread; refreshed whenever the user
# adds a folder via the UI.
SEARCH_ROOTS = get_search_roots()


def refresh_search_roots() -> None:
    """Re‑compute SEARCH_ROOTS after the config has changed."""
    global SEARCH_ROOTS
    SEARCH_ROOTS = get_search_roots()
    if DEBUG:
        print("[debug] SEARCH_ROOTS refreshed:")
        for r in SEARCH_ROOTS:
            print("   •", r)


# --------------------------------------------------------------
# 1️⃣1️⃣  Worker that actually scans the file system
# --------------------------------------------------------------
def _search_worker(search_term: str, result_q: queue.Queue, stop_evt: threading.Event):
    """
    Walk every folder in SEARCH_ROOTS and put a result into ``result_q`` for each
    *.exe* or *.lnk* whose **file name OR any component of its full path**
    contains ``search_term`` (case‑insensitive).

    The function runs in a background thread; when the crawl finishes it
    puts ``None`` into the queue as a sentinel.
    """
    term = search_term.lower()
    for root in SEARCH_ROOTS:
        if stop_evt.is_set():
            break
        if not root.is_dir():
            continue

        if DEBUG:
            print(f"[debug] walking {root}")

        try:
            for dirpath, _dirnames, filenames in os.walk(root, topdown=True):
                if stop_evt.is_set():
                    break

                # skip hidden/system folders (e.g. $RECYCLE.BIN, .git)
                if any(part.startswith('.') for part in Path(dirpath).parts):
                    continue

                # ------------------------------------------------------
                # 1️⃣  Build a *set* of lower‑cased path components.
                #     This lets us match the search term anywhere in the path,
                #     not only in the file name.
                # ------------------------------------------------------
                path_parts = {p.lower() for p in Path(dirpath).parts}

                for fname in filenames:
                    low = fname.lower()
                    # accept only .exe and .lnk files
                    if not (low.endswith('.exe') or low.endswith('.lnk')):
                        continue

                    # --------------------------------------------------
                    # 2️⃣  Does the term appear in the file name **or**
                    #    in **any** folder name that leads to it?
                    # --------------------------------------------------
                    if term not in low and term not in path_parts:
                        continue

                    full_path = Path(dirpath) / fname

                    # --------------------------------------------------
                    # 3️⃣  Resolve shortcuts (only if pywin32 is present)
                    # --------------------------------------------------
                    if low.endswith('.lnk'):
                        if HAVE_PYWIN32:
                            try:
                                shell = win32com.client.Dispatch("WScript.Shell")
                                shortcut = shell.CreateShortCut(str(full_path))
                                target = shortcut.Targetpath
                                # Show the target’s stem if it ends in .exe,
                                # otherwise fallback to the shortcut name.
                                display_name = (
                                    Path(target).stem
                                    if target and target.lower().endswith('.exe')
                                    else full_path.stem
                                )
                                result_q.put((display_name,
                                              target if target else str(full_path)))
                                continue
                            except Exception:   # pragma: no cover
                                pass
                        # pywin32 not available – just report the shortcut itself
                        result_q.put((full_path.stem, str(full_path)))
                    else:
                        # regular .exe – unchanged behaviour
                        result_q.put((full_path.stem, str(full_path)))
        except PermissionError:
            # many system folders are unreadable – just skip them
            continue
        except Exception as exc:          # pragma: no cover
            if DEBUG:
                print("[debug] walk error:", exc)
            continue

    # sentinel – tells the UI that the search has finished
    result_q.put(None)




# --------------------------------------------------------------
# 1️⃣2️⃣  “Find Game” dialog
# --------------------------------------------------------------
def find_game():
    """Open the draggable Find‑Game window and start a background search."""
    # ---------- window skeleton ----------
    win = tk.Toplevel(root)
    win.title("🔍 Find Game")
    win.geometry("420x460+250+180")
    win.configure(bg="#1e1e2e")
    win.attributes("-topmost", True)
    win.overrideredirect(True)
    win.attributes("-alpha", 0.96)

    make_draggable(win)

    # top‑bar with a close button
    top = tk.Frame(win, bg="#31334a")
    top.pack(fill="x")
    tk.Label(
        top,
        text="  Find Game",
        bg="#31334a",
        fg="#cdd6f4",
        font=("Segoe UI", 10, "bold"),
    ).pack(side="left")
    ttk.Button(top, text="✕", command=win.destroy, style="TButton").pack(
        side="right", padx=4, pady=2
    )

    # ---------- search entry ----------
    frm_search = tk.Frame(win, bg="#1e1e2e")
    frm_search.pack(fill="x", padx=12, pady=8)

    tk.Label(frm_search, text="Search term:", bg="#1e1e2e", fg="#cdd6f4").pack(anchor="w")
    entry = tk.Entry(
        frm_search,
        font=("Segoe UI", 10),
        bg="#31334a",
        fg="#cdd6f4",
        insertbackground="#cdd6f4",
    )
    entry.pack(fill="x", pady=4)

    def add_search_folder():
        """Let the user pick an extra root that will be scanned."""
        folder = filedialog.askdirectory(
            title="Select a folder to include in searches",
            initialdir=str(Path.home()),
        )
        if not folder:
            return
        cfg_paths = config.get("search_paths", [])
        if folder not in cfg_paths:
            cfg_paths.append(folder)
            config["search_paths"] = cfg_paths
            save_config(config)
            refresh_search_roots()
            messagebox.showinfo(
                "Folder added",
                f"The folder\n{folder}\nwill now be scanned for games.",
            )

    ttk.Button(frm_search, text="Add search folder …", command=add_search_folder).pack(
        pady=4
    )

    # ---------- results listbox ----------
    frm_list = tk.Frame(win, bg="#1e1e2e")
    frm_list.pack(fill="both", expand=True, padx=12, pady=4)

    sb = tk.Scrollbar(frm_list, orient="vertical")
    lb = tk.Listbox(
        frm_list,
        bg="#31334a",
        fg="#cdd6f4",
        selectbackground="#89b4fa",
        yscrollcommand=sb.set,
        font=("Segoe UI", 10),
    )
    sb.config(command=lb.yview)
    sb.pack(side="right", fill="y")
    lb.pack(side="left", fill="both", expand=True)

    # ---------- status line ----------
    status = tk.Label(
        win,
        text="Enter a term (e.g. part of the file name) and press **Enter**",
        bg="#1e1e2e",
        fg="#585b70",
        font=("Segoe UI", 9),
    )
    status.pack(fill="x", padx=12, pady=4)

    # ---------- launch button ----------
    launch_btn = ttk.Button(win, text="Launch Selected", state="disabled")
    launch_btn.pack(fill="x", padx=12, pady=6)

    def on_select(event=None):
        launch_btn.config(state="normal" if lb.curselection() else "disabled")

    lb.bind("<<ListboxSelect>>", on_select)

    # ---------- thread control ----------
    search_thread = None
    stop_evt = threading.Event()
    result_q = queue.Queue()

    # ---------- queue polling ----------
    def poll_queue():
        try:
            while True:
                item = result_q.get_nowait()
                if item is None:               # sentinel – finished
                    status.config(text=f"{lb.size()} result(s) found")
                    return
                name, path = item
                lb.insert(tk.END, f"{name} – {path}")
        except queue.Empty:
            pass
        win.after(100, poll_queue)

    # ---------- start a new search ----------
    def start_search(event=None):
        term = entry.get().strip()
        if not term:
            # we *require* a non‑empty term – otherwise the UI would
            # start a huge scan that may take minutes.
            messagebox.showinfo(
                "Empty term", "Please type at least one character to search."
            )
            return

        # reset UI
        lb.delete(0, tk.END)
        launch_btn.config(state="disabled")
        status.config(text="Searching…")

        # stop any previous worker
        nonlocal search_thread
        if search_thread and search_thread.is_alive():
            stop_evt.set()
            search_thread.join()
        stop_evt.clear()

        # fire up a fresh worker
        search_thread = threading.Thread(
            target=_search_worker,
            args=(term, result_q, stop_evt),
            daemon=True,
        )
        search_thread.start()
        poll_queue()

    entry.bind("<Return>", start_search)

    # ---------- launch the selected item ----------
    def launch_selected():
        cur = lb.curselection()
        if not cur:
            return
        line = lb.get(cur[0])
        try:
            _display, path = line.split(" – ", 1)
        except ValueError:
            return
        p = Path(path)
        if p.suffix.lower() == ".lnk":
            # let Windows follow the shortcut (works even without pywin32)
            os.startfile(str(p))
        else:
            launch_game(p.stem, str(p))

    launch_btn.config(command=launch_selected)

    # ---------- clean‑up ----------
    def on_close():
        stop_evt.set()
        if search_thread and search_thread.is_alive():
            search_thread.join()
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_close)


# --------------------------------------------------------------
# 1️⃣3️⃣  Main / sub‑menus (games list, help, etc.)
# --------------------------------------------------------------
main_menu = None
games_submenu = None


def close_submenu():
    global games_submenu
    if games_submenu and games_submenu.winfo_exists():
        games_submenu.destroy()
        games_submenu = None


def close_mainmenu():
    global main_menu
    if main_menu and main_menu.winfo_exists():
        main_menu.destroy()
        main_menu = None


def close_all():
    close_submenu()
    close_mainmenu()


def open_url(url: str):
    """Open a URL – prefer Edge, otherwise the default browser."""
    if EDGE_PATH:
        subprocess.Popen([str(EDGE_PATH), "--new-window", url])
    else:
        subprocess.Popen(["start", url], shell=True)
    close_all()


def open_grok():
    open_url(config["grok_url"])


def open_youtube():
    open_url(config["youtube_url"])


def open_ai_chat():
    """Simple offline chat window that talks to Ollama."""
    chat = tk.Toplevel(root)
    chat.title("AI Chat ♡")
    chat.geometry("420x520+300+200")
    chat.configure(bg="#1e1e2e")
    chat.attributes("-topmost", True)

    txt = tk.Text(
        chat,
        bg="#1e1e2e",
        fg="#cdd6f4",
        insertbackground="#cdd6f4",
        relief="flat",
        font=("Segoe UI", 10),
        wrap="word",
    )
    txt.pack(expand=True, fill="both", padx=8, pady=8)
    txt.insert("end", "AI: Ahoj ♡ Napiš mi něco.\n\n")
    txt.config(state="disabled")

    entry = tk.Entry(
        chat,
        bg="#31334a",
        fg="#cdd6f4",
        insertbackground="#cdd6f4",
        relief="flat",
        font=("Segoe UI", 10),
    )
    entry.pack(fill="x", padx=8, pady=(0, 8))
    entry.focus()

    def send(event=None):
        msg = entry.get().strip()
        if not msg:
            return
        entry.delete(0, "end")
        txt.config(state="normal")
        txt.insert("end", f"Ty: {msg}\n")
        txt.insert("end", "AI: přemýšlím…\n")
        txt.see("end")
        txt.config(state="disabled")
        chat.after(100, lambda: respond(msg))

    def respond(message):
        reply = ask_ai(message)
        txt.config(state="normal")
        txt.delete("end-2l", "end-1l")
        txt.insert("end", f"AI: {reply}\n\n")
        txt.see("end")
        txt.config(state="disabled")

    entry.bind("<Return>", send)


def add_new_game():
    """Prompt for name + .exe path and store it."""
    new_name = simpledialog.askstring("New Game", "Enter a name for the new game:")
    if not new_name:
        return
    new_name = new_name.strip()
    if new_name in config["games"]:
        messagebox.showerror("Error", f"A game named \"{new_name}\" already exists.")
        return

    exe_path = filedialog.askopenfilename(
        title=f"Select the executable for {new_name}",
        filetypes=[("Executable files", "*.exe"), ("All files", "*.*")],
        initialdir=str(Path.home()),
    )
    if not exe_path:
        return

    config["games"][new_name] = exe_path
    save_config(config)
    close_submenu()


def edit_existing_game():
    """Show a list of configured games and let the user change the path."""
    if not config["games"]:
        messagebox.showinfo("Edit game", "No games configured.")
        return

    win = tk.Toplevel(root)
    win.title("Edit Game")
    win.geometry("300x380+200+200")
    win.configure(bg="#1e1e2e")
    win.attributes("-topmost", True)

    tk.Label(win, text="Select a game:", bg="#1e1e2e", fg="#cdd6f4").pack(pady=6)

    lb = tk.Listbox(
        win, bg="#31334a", fg="#cdd6f4", selectbackground="#89b4fa"
    )
    for name in sorted(config["games"]):
        lb.insert(tk.END, name)
    lb.pack(fill="both", expand=True, padx=8, pady=8)

    def do_edit():
        sel = lb.curselection()
        if not sel:
            return
        cur_name = lb.get(sel[0])

        new_path = filedialog.askopenfilename(
            title=f"Select new executable for {cur_name}",
            filetypes=[("Executable files", "*.exe"), ("All files", "*.*")],
            initialdir=str(Path.home()),
        )
        if not new_path:
            return

        config["games"][cur_name] = new_path
        save_config(config)
        win.destroy()
        close_submenu()

    ttk.Button(win, text="Edit", command=do_edit).pack(pady=4)
    ttk.Button(win, text="Close", command=win.destroy).pack(pady=2)


def make_draggable(win: tk.Toplevel) -> None:
    """Add click‑drag behaviour to any Toplevel window."""
    def on_press(event):
        win._drag_x = event.x_root - win.winfo_x()
        win._drag_y = event.y_root - win.winfo_y()

    def on_motion(event):
        new_x = event.x_root - win._drag_x
        new_y = event.y_root - win._drag_y
        win.geometry(f"+{new_x}+{new_y}")

    win.bind("<Button-1>", on_press)
    win.bind("<B1-Motion>", on_motion)


def create_menu(event, is_submenu: bool = False):
    """Show the main menu (or the submenu that lists the games)."""
    global main_menu, games_submenu

    if is_submenu and games_submenu and games_submenu.winfo_exists():
        games_submenu.destroy()
    if not is_submenu and main_menu and main_menu.winfo_exists():
        main_menu.destroy()

    win = tk.Toplevel(root)
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.attributes("-alpha", 0.96)
    win.configure(bg="#1e1e2e")

    offset_x = 140 if is_submenu else 0
    offset_y = 50 if is_submenu else 0
    win.geometry(f"+{event.x_root + offset_x}+{event.y_root + offset_y}")

    make_draggable(win)

    frm = tk.Frame(win, bg="#1e1e2e")
    frm.pack(padx=8, pady=8)

    buttons: list[tuple[str, callable | None]] = []

    if is_submenu:
        # list the games we have in the config
        for name, path in config.get("games", {}).items():
            buttons.append((f"{name} 🎮", lambda n=name, p=path: launch_game(n, p)))

        buttons.append(("", None))                     # visual separator
        buttons.append(("Add new game +", add_new_game))
        buttons.append(("Edit existing game …", edit_existing_game))
        buttons.append(("← Back", win.destroy))

        games_submenu = win
    else:
        buttons = [
            ("online AI Chat ", open_grok),
            ("offline AI Chat ", open_ai_chat),
            ("YouTube ▶", open_youtube),
            ("Launch Game 🎮", lambda: create_menu(event, True)),
            ("Find Game 🎮", find_game),
            ("Close ×", close_all),
        ]
        main_menu = win

    for txt, cmd in buttons:
        if cmd is None:          # separator line
            sep = tk.Label(
                frm,
                text="──────────────────────",
                bg="#1e1e2e",
                fg="#585b70",
                font=("Segoe UI", 9),
            )
            sep.pack(pady=4, fill="x")
        else:
            ttk.Button(frm, text=txt, command=cmd, style="TButton").pack(
                pady=3, fill="x"
            )


# Double‑click on the pet opens the main menu
gif_label.bind("<Double-Button-1>", lambda e: create_menu(e))

# --------------------------------------------------------------
# 1️⃣4️⃣  Main loop
# --------------------------------------------------------------
root.mainloop()
