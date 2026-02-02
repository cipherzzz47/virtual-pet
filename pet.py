#!/usr/bin/env python
# -*- coding: utf-8 -*-

# --------------------------------------------------------------
# 1️⃣  Imports
# --------------------------------------------------------------
import sys
import os
import json
import subprocess
import winreg
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from pathlib import Path
from PIL import Image, ImageTk, ImageSequence

# --------------------------------------------------------------
# 2️⃣  Cesty a konfigurace
# --------------------------------------------------------------
def get_base_path() -> Path:
    """Cesta k adresáři s artefakty (běh jako .exe nebo .py)."""
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
}


def load_config() -> dict:
    """Načte config.json, nebo vytvoří výchozí."""
    if not CONFIG_PATH.is_file():
        CONFIG_PATH.write_text(
            json.dumps(DEFAULT_CONFIG, indent=4, ensure_ascii=False), encoding="utf-8"
        )
        return DEFAULT_CONFIG.copy()

    try:
        user_cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        cfg = DEFAULT_CONFIG.copy()
        cfg.update(user_cfg)
        return cfg
    except Exception as exc:
        print(f"Config error: {exc} – using defaults")
        return DEFAULT_CONFIG.copy()


def save_config(cfg: dict) -> None:
    """Uloží config na disk."""
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(cfg, indent=4, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as exc:
        messagebox.showerror("Uložení configu", f"Nepodařilo se uložit config:\n{exc}")


config = load_config()

# --------------------------------------------------------------
# 3️⃣  Pomocné funkce (prohlížeč, AI, hry)
# --------------------------------------------------------------
def find_edge_path() -> Path | None:
    """Z registru získá cestu k msedge.exe."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
        )
        path = winreg.QueryValue(key, None)
        winreg.CloseKey(key)
        return Path(path)
    except OSError:
        return None


EDGE_PATH = find_edge_path()


def ask_ai(prompt: str) -> str:
    """Jednoduché volání Ollama – pokud selže, vrátí chybovou zprávu."""
    try:
        result = subprocess.run(
            ["ollama", "run", "llama3.1"],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return result.stdout.strip()
    except Exception as exc:
        return f"AI error: {exc}"


def launch_game(game_name: str, game_path: str) -> None:
    """
    Spustí hru nebo (pokud cesta neexistuje) nabídne doplnění.
    Po doplnění se položka v configu přejmenuje na *stem* souboru.
    """
    path_obj = Path(game_path)

    # -------------------- existuje --------------------
    if path_obj.is_file():
        try:
            subprocess.Popen([str(path_obj)])
        except Exception as exc:
            messagebox.showerror("Spuštění hry", f"Při spouštění hry nastala chyba:\n{exc}")
        return

    # -------------------- chybí --------------------
    if not messagebox.askyesno(
        "Hra nenalezena",
        f"Cesta k hře „{game_name}“ neexistuje:\n{game_path}\n\nChcete ji doplnit?",
    ):
        return

    new_path = filedialog.askopenfilename(
        title=f"Vyberte spustitelný soubor pro {game_name}",
        filetypes=[("Spustitelné soubory", "*.exe"), ("Všechny soubory", "*.*")],
        initialdir=str(Path.home()),
    )
    if not new_path:
        return

    new_key = Path(new_path).stem                     # např. "SuperMario"
    config["games"][new_key] = new_path
    if new_key != game_name and game_name in config["games"]:
        del config["games"][game_name]                 # starý neplatný klíč
    save_config(config)

    try:
        subprocess.Popen([new_path])
    except Exception as exc:
        messagebox.showerror("Spuštění hry", f"Při spouštění hry nastala chyba:\n{exc}")

# ---- vytvoříme root (interpreter) a ihned ho skryjeme ----
root = tk.Tk()
root.withdraw()                     # <‑‑ to MUSÍ být HNED, před všemi ostatními widgety

# --------------------------------------------------------------
# 4️⃣  UI – primární (skryté) okno a okno mazlíčka
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



# ---- okno mazlíčka (jediné viditelné) -----------------
TRANSPARENT_COLOR = "#ff00ff"

pet_win = tk.Toplevel(root)                # rodič = root (skrytý)
pet_win.overrideredirect(True)             # žádný rám, žádná lišta
pet_win.attributes("-topmost", True)       # vždy nahoře
pet_win.geometry("480x720+200+50")
pet_win.configure(bg=TRANSPARENT_COLOR)
pet_win.wm_attributes("-transparentcolor", TRANSPARENT_COLOR)

# ---- načtení animovaného GIF‑u -------------------------
gif_file = config["gif_path"]
if not Path(gif_file).is_absolute():
    gif_file = BASE_PATH / gif_file

if not Path(gif_file).is_file():
    messagebox.showerror("GIF error", f"Nepodařilo se najít GIF: {gif_file}")
    sys.exit(1)

pil_img = Image.open(gif_file)

# **DŮLEŽITÉ** – předáme master=pet_win, aby obrázek patřil k tomu oknu
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
gif_label.place(x=0, y=0, relwidth=1, relheight=1)


def animate(i: int = 0) -> None:
    gif_label.configure(image=frames[i % len(frames)])
    pet_win.after(pil_img.info.get("duration", 100), animate, i + 1)


animate()

# ---- drag & drop (přetahování mazlíčka) ---------------
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
# 5️⃣  Kontextové kill‑menu (pravé tlačítko)
# --------------------------------------------------------------
kill_menu = None


def show_kill_menu(event):
    """Malé okno s tlačítky „Kill Pet“ a „Cancel“."""
    global kill_menu
    if kill_menu and kill_menu.winfo_exists():
        kill_menu.destroy()

    kill_menu = tk.Toplevel(pet_win)          # rodič – mazlíček
    kill_menu.overrideredirect(True)
    kill_menu.attributes("-topmost", True)
    kill_menu.attributes("-alpha", 0.96)
    kill_menu.configure(bg="#1e1e2e")
    kill_menu.geometry(f"+{event.x_root + 20}+{event.y_root + 20}")

    frm = tk.Frame(kill_menu, bg="#1e1e2e")
    frm.pack(padx=8, pady=8)

    ttk.Button(frm, text="Kill Pet ×", command=root.destroy).pack(fill="x", pady=3)
    ttk.Button(frm, text="Cancel", command=kill_menu.destroy).pack(fill="x", pady=3)


gif_label.bind("<Button-3>", show_kill_menu)

# --------------------------------------------------------------
# 6️⃣  Hlavní a pod‑menu (správa her)
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
    """Otevře URL v Edge (nebo v default prohlížeči)."""
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
    """Okno offline AI chat (Ollama)."""
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
        txt.delete("end-2l", "end-1l")      # smaže „přemýšlím…“
        txt.insert("end", f"AI: {reply}\n\n")
        txt.see("end")
        txt.config(state="disabled")

    entry.bind("<Return>", send)


# ------------------- Správa her (Add / Edit) -----------------
def add_new_game():
    """Přidá novou hru (název + cesta)."""
    new_name = simpledialog.askstring("Nová hra", "Zadejte název nové hry:")
    if not new_name:
        return
    new_name = new_name.strip()
    if new_name in config["games"]:
        messagebox.showerror("Chyba", f"Hra s názvem „{new_name}“ už existuje.")
        return

    exe_path = filedialog.askopenfilename(
        title=f"Vyberte spustitelný soubor pro {new_name}",
        filetypes=[("Spustitelné soubory", "*.exe"), ("Všechny soubory", "*.*")],
        initialdir=str(Path.home()),
    )
    if not exe_path:
        return

    config["games"][new_name] = exe_path
    save_config(config)
    close_submenu()


def edit_existing_game():
    """Umožní uživateli změnit cestu u existující hry."""
    if not config["games"]:
        messagebox.showinfo("Úprava hry", "Žádná hra není definovaná.")
        return

    win = tk.Toplevel(root)
    win.title("Upravit hru")
    win.geometry("300x380+200+200")
    win.configure(bg="#1e1e2e")
    win.attributes("-topmost", True)

    tk.Label(win, text="Vyberte hru:", bg="#1e1e2e", fg="#cdd6f4").pack(pady=6)

    lb = tk.Listbox(win, bg="#31334a", fg="#cdd6f4", selectbackground="#89b4fa")
    for name in sorted(config["games"]):
        lb.insert(tk.END, name)
    lb.pack(fill="both", expand=True, padx=8, pady=8)

    def do_edit():
        sel = lb.curselection()
        if not sel:
            return
        cur_name = lb.get(sel[0])

        new_path = filedialog.askopenfilename(
            title=f"Vyberte nový spustitelný soubor pro {cur_name}",
            filetypes=[("Spustitelné soubory", "*.exe"), ("Všechny soubory", "*.*")],
            initialdir=str(Path.home()),
        )
        if not new_path:
            return

        config["games"][cur_name] = new_path
        save_config(config)
        win.destroy()
        close_submenu()

    ttk.Button(win, text="Upravit", command=do_edit).pack(pady=4)
    ttk.Button(win, text="Zavřít", command=win.destroy).pack(pady=2)


# ------------------- Vytváření hlavního a pod‑menu ----------
def create_menu(event, is_submenu: bool = False):
    """Vytvoří hlavní menu nebo pod‑menu (seznam her)."""
    global main_menu, games_submenu

    if is_submenu and games_submenu and games_submenu.winfo_exists():
        games_submenu.destroy()
    if not is_submenu and main_menu and main_menu.winfo_exists():
        main_menu.destroy()

    win = tk.Toplevel(root)                     # rodič = root (skrytý)
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.attributes("-alpha", 0.96)
    win.configure(bg="#1e1e2e")

    offset_x = 140 if is_submenu else 0
    offset_y = 50  if is_submenu else 0
    win.geometry(f"+{event.x_root + offset_x}+{event.y_root + offset_y}")

    frm = tk.Frame(win, bg="#1e1e2e")
    frm.pack(padx=8, pady=8)

    buttons: list[tuple[str, callable | None]] = []

    if is_submenu:
        # ---- seznam her -------------------------------------------------
        buttons = [
            (f"{name} 🎮", lambda n=name, p=path: launch_game(n, p))
            for name, path in config.get("games", {}).items()
        ]

        # oddělovač (neklikací)
        buttons.append(("", None))

        # správa her
        buttons.append(("Add new game +", add_new_game))
        buttons.append(("Edit existing game …", edit_existing_game))

        # zpět
        buttons.append(("← Back", win.destroy))

        games_submenu = win
    else:
        # ---- hlavní menu -------------------------------------------------
        buttons = [
            ("online AI Chat ", open_grok),
            ("offline AI Chat ", open_ai_chat),
            ("YouTube ▶", open_youtube),
            ("Launch Game 🎮", lambda: create_menu(event, True)),
            ("Close ×", close_all),
        ]
        main_menu = win

    # ---- vytvoření widgetů (button / separator) ---------------------------
    for txt, cmd in buttons:
        if cmd is None:                         # separator
            sep = tk.Label(
                frm,
                text="──────────────────────",
                bg="#1e1e2e",
                fg="#585b70",
                font=("Segoe UI", 9),
            )
            sep.pack(pady=4, fill="x")
            continue

        btn = ttk.Button(frm, text=txt, command=cmd, style="TButton")
        btn.pack(pady=3, fill="x")


# dvojklik → otevře hlavní menu
gif_label.bind("<Double-Button-1>", lambda e: create_menu(e))

# --------------------------------------------------------------
# 7️⃣  Hlavní smyčka
# --------------------------------------------------------------
root.mainloop()
