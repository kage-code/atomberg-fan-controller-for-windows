r"""
Atomberg Fan Control - desktop remote.

Run:  double-click run.vbs  (or: pip install requests; python fan_control.py)

Config and call counters are stored in %APPDATA%\AtombergControl\.
"""

import json
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import requests

BASE_URL = "https://api.developer.atomberg-iot.com"
APP_NAME = "AtombergControl"
DAY_SECONDS = 24 * 60 * 60
DAILY_CAP = 100

APPDATA_DIR = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), APP_NAME)
os.makedirs(APPDATA_DIR, exist_ok=True)
CONFIG_PATH = os.path.join(APPDATA_DIR, "config.json")
COUNTS_PATH = os.path.join(APPDATA_DIR, "call_counts.json")

# When launched via pythonw.exe (no console attached), stdout/stderr are
# None. Redirect them to a log file so the SENDING/RESPONSE debug output
# isn't silently lost.
if sys.stdout is None:
    _log_path = os.path.join(APPDATA_DIR, "debug.log")
    sys.stdout = open(_log_path, "a", buffering=1)
    sys.stderr = sys.stdout

# ---- palette -------------------------------------------------------------
BG        = "#0f1115"
CARD      = "#181b22"
CARD_SOFT = "#20242e"
ACCENT    = "#4da3ff"
ACCENT_DK = "#2b6fb5"
GREEN     = "#3ddc84"
TEXT      = "#e8ebf0"
MUTED     = "#79839a"
DANGER    = "#ff6b6b"

F_TITLE = ("Segoe UI Semibold", 15)
F_BODY  = ("Segoe UI", 10)
F_SMALL = ("Segoe UI", 8)
F_PILL  = ("Segoe UI Semibold", 10)


# --------------------------------------------------------------------------
# Config (api key / refresh token) - editable from the Settings dialog
# --------------------------------------------------------------------------
def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {"api_key": "", "refresh_token": ""}
    with open(CONFIG_PATH) as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


# --------------------------------------------------------------------------
# Per-device call counters - each key gets its own rolling 24h window
# --------------------------------------------------------------------------
class CallCounter:
    def __init__(self):
        self.data = {}
        if os.path.exists(COUNTS_PATH):
            try:
                with open(COUNTS_PATH) as f:
                    self.data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.data = {}

    def _save(self):
        with open(COUNTS_PATH, "w") as f:
            json.dump(self.data, f, indent=2)

    def current(self, key):
        entry = self.data.get(key)
        if not entry:
            return 0
        if time.time() - entry["window_start"] >= DAY_SECONDS:
            return 0
        return entry["count"]

    def record(self, key):
        key = key or "_account"
        entry = self.data.get(key)
        now = time.time()
        if not entry or now - entry["window_start"] >= DAY_SECONDS:
            entry = {"count": 0, "window_start": now}
        entry["count"] += 1
        self.data[key] = entry
        self._save()

    def total_today(self):
        return sum(self.current(k) for k in self.data)


# --------------------------------------------------------------------------
# API layer
# --------------------------------------------------------------------------
class AtombergAPI:
    def __init__(self, api_key, refresh_token, on_call=None):
        self.api_key = api_key
        self.refresh_token = refresh_token
        self.access_token = None
        self.on_call = on_call or (lambda device_id: None)

    def set_credentials(self, api_key, refresh_token):
        self.api_key = api_key
        self.refresh_token = refresh_token
        self.access_token = None

    def _headers(self, token):
        return {
            "Authorization": f"Bearer {token}",
            "x-api-key": self.api_key,
            "Accept": "application/json",
        }

    def _get_access_token(self):
        self.on_call(None)
        r = requests.get(f"{BASE_URL}/v1/get_access_token",
                         headers=self._headers(self.refresh_token), timeout=15)
        r.raise_for_status()
        self.access_token = r.json()["message"]["access_token"]
        return self.access_token

    def _request(self, method, path, device_id=None, **kwargs):
        if not self.access_token:
            self._get_access_token()

        def fire():
            self.on_call(device_id)
            return requests.request(method, f"{BASE_URL}{path}",
                                    headers=self._headers(self.access_token),
                                    timeout=15, **kwargs)

        resp = fire()
        if resp.status_code == 401:
            self._get_access_token()
            resp = fire()

        if resp.status_code == 403:
            raise RuntimeError("Developer Mode is off in the Atomberg app.")
        if resp.status_code == 429:
            raise RuntimeError("Daily API quota hit (100 calls/day).")
        resp.raise_for_status()
        return resp.json()

    def list_devices(self):
        return self._request("GET", "/v1/get_list_of_devices")["message"].get(
            "devices_list", [])

    def get_state(self, device_id):
        data = self._request("GET", "/v1/get_device_state", device_id=device_id,
                             params={"device_id": device_id})
        print("STATE RESPONSE:", json.dumps(data, indent=2))
        states = data["message"].get("device_state", [])
        return states[0] if states else {}

    def send_command(self, device_id, command):
        payload = {"device_id": device_id, "command": command}
        print("SENDING:", json.dumps(payload))
        data = self._request("POST", "/v1/send_command", device_id=device_id,
                             json=payload)
        print("RESPONSE:", json.dumps(data, indent=2))
        return data


# --------------------------------------------------------------------------
# Small drawn widgets (Tkinter has no rounded buttons natively)
# --------------------------------------------------------------------------
def rounded_rect(canvas, x1, y1, x2, y2, r, **kwargs):
    points = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r,
              x2, y2, x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r,
              x1, y1 + r, x1, y1]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class Pill(tk.Canvas):
    def __init__(self, parent, text, command, w=88, h=36, r=10,
                 bg=CARD, idle=CARD_SOFT, hover="#2a2f3b",
                 active=ACCENT, fg=TEXT, font=F_PILL):
        super().__init__(parent, width=w, height=h, bg=bg,
                         highlightthickness=0, bd=0)
        self.command = command
        self.idle, self.hover, self.active_col = idle, hover, active
        self.is_active = False
        self.shape = rounded_rect(self, 1, 1, w - 1, h - 1, r,
                                  fill=idle, outline="")
        self.label = self.create_text(w / 2, h / 2, text=text, fill=fg, font=font)
        self.bind("<Button-1>", lambda e: self.command())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.configure(cursor="hand2")

    def _on_enter(self, _):
        if not self.is_active:
            self.itemconfig(self.shape, fill=self.hover)

    def _on_leave(self, _):
        if not self.is_active:
            self.itemconfig(self.shape, fill=self.idle)

    def set_active(self, on, active_col=None):
        self.is_active = on
        col = active_col or self.active_col
        self.itemconfig(self.shape, fill=col if on else self.idle)
        self.itemconfig(self.label, fill="#0f1115" if on else TEXT)

    def set_text(self, text):
        self.itemconfig(self.label, text=text)


class PowerButton(tk.Canvas):
    SIZE = 116

    def __init__(self, parent, command, bg=CARD):
        s = self.SIZE
        super().__init__(parent, width=s, height=s, bg=bg,
                         highlightthickness=0, bd=0)
        self.command = command
        self.glow = self.create_oval(4, 4, s - 4, s - 4, fill=CARD_SOFT, outline="")
        self.ring = self.create_oval(14, 14, s - 14, s - 14, width=3,
                                     outline=MUTED, fill=CARD)
        self.arc = self.create_arc(36, 36, s - 36, s - 36, start=65, extent=410,
                                   style="arc", width=4, outline=MUTED)
        self.stem = self.create_line(s / 2, 30, s / 2, s / 2 - 4,
                                     width=4, fill=MUTED, capstyle="round")
        self.bind("<Button-1>", lambda e: self.command())
        self.configure(cursor="hand2")

    def set_state(self, on):
        col = GREEN if on else MUTED
        self.itemconfig(self.arc, outline=col)
        self.itemconfig(self.stem, fill=col)
        self.itemconfig(self.ring, outline=col)
        self.itemconfig(self.glow, fill="#17301f" if on else CARD_SOFT)


# --------------------------------------------------------------------------
# Settings dialog
# --------------------------------------------------------------------------
class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, cfg, on_save):
        super().__init__(parent)
        self.title("Settings")
        self.configure(bg=CARD)
        self.geometry("380x300")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.on_save = on_save

        pad = {"padx": 22, "pady": 6}

        tk.Label(self, text="Atomberg credentials", font=F_TITLE,
                 bg=CARD, fg=TEXT).pack(anchor="w", padx=22, pady=(20, 4))
        tk.Label(self, text="From the Atomberg app: Profile → Developer Options",
                 font=F_SMALL, bg=CARD, fg=MUTED,
                 wraplength=330, justify="left").pack(anchor="w", padx=22)

        tk.Label(self, text="API Key", font=F_BODY, bg=CARD,
                 fg=TEXT).pack(anchor="w", **pad)
        self.api_key_var = tk.StringVar(value=cfg.get("api_key", ""))
        self._entry(self.api_key_var)

        tk.Label(self, text="Refresh Token", font=F_BODY, bg=CARD,
                 fg=TEXT).pack(anchor="w", **pad)
        self.refresh_var = tk.StringVar(value=cfg.get("refresh_token", ""))
        self._entry(self.refresh_var)

        self.error_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.error_var, font=F_SMALL, bg=CARD,
                 fg=DANGER, wraplength=330, justify="left").pack(
            anchor="w", padx=22, pady=(4, 0))

        btn_row = tk.Frame(self, bg=CARD)
        btn_row.pack(pady=20)
        Pill(btn_row, "Save", self._save, w=100, h=38).pack(side="left", padx=6)
        Pill(btn_row, "Cancel", self.destroy, w=100, h=38,
             active=CARD_SOFT).pack(side="left", padx=6)

    def _entry(self, var):
        e = tk.Entry(self, textvariable=var, bg=CARD_SOFT, fg=TEXT,
                    insertbackground=TEXT, relief="flat", font=F_BODY)
        e.pack(fill="x", padx=22, ipady=6)

    def _save(self):
        api_key = self.api_key_var.get().strip()
        refresh_token = self.refresh_var.get().strip()
        if not api_key or not refresh_token:
            self.error_var.set("Both fields are required.")
            return
        cfg = {"api_key": api_key, "refresh_token": refresh_token}
        save_config(cfg)
        self.on_save(cfg)
        self.destroy()


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------
class FanApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.counter = CallCounter()
        cfg = load_config()
        self.api = AtombergAPI(cfg.get("api_key", ""), cfg.get("refresh_token", ""),
                               on_call=self.counter.record)

        self.devices = []
        self.last_speed = None
        self.power_on = False
        self.led_on = False

        self.title("Atomberg")
        self.geometry("420x640")
        self.resizable(False, False)
        self.configure(bg=BG)

        self._build_header()
        self._build_card()
        self._build_footer()

        if not cfg.get("api_key") or not cfg.get("refresh_token"):
            self.after(200, self.open_settings)
        else:
            self.run_async(self.load_devices)

    # ---- layout ----------------------------------------------------------
    def _build_header(self):
        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", padx=24, pady=(22, 10))

        title_col = tk.Frame(head, bg=BG)
        title_col.pack(side="left")
        tk.Label(title_col, text="Fan Control", font=F_TITLE, bg=BG,
                 fg=TEXT).pack(anchor="w")
        tk.Label(title_col, text="Atomberg cloud", font=F_SMALL, bg=BG,
                 fg=MUTED).pack(anchor="w")

        Pill(head, "Settings", self.open_settings, w=90, h=32,
             active=CARD_SOFT).pack(side="right", pady=6)

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Dark.TCombobox", fieldbackground=CARD_SOFT,
                        background=CARD_SOFT, foreground=TEXT,
                        arrowcolor=MUTED, bordercolor=CARD_SOFT,
                        lightcolor=CARD_SOFT, darkcolor=CARD_SOFT)
        self.device_box = ttk.Combobox(self, state="readonly", width=34,
                                       style="Dark.TCombobox", font=F_BODY)
        self.device_box.pack(padx=24, pady=(6, 0), fill="x")
        self.device_box.bind("<<ComboboxSelected>>", lambda e: self.on_device_change())

    def _build_card(self):
        card = tk.Frame(self, bg=CARD)
        card.pack(fill="both", expand=True, padx=24, pady=16)

        self.power_btn = PowerButton(card, self.toggle_power)
        self.power_btn.pack(pady=(26, 6))
        self.power_label = tk.Label(card, text="OFF", font=F_PILL,
                                    bg=CARD, fg=MUTED)
        self.power_label.pack()

        tk.Label(card, text="SPEED", font=F_SMALL, bg=CARD,
                 fg=MUTED).pack(anchor="w", padx=22, pady=(24, 6))
        speed_row = tk.Frame(card, bg=CARD)
        speed_row.pack(padx=18)
        self.speed_pills = {}
        for s in range(1, 7):
            p = Pill(speed_row, str(s), lambda s=s: self.set_speed(s), w=48, h=44)
            p.pack(side="left", padx=3)
            self.speed_pills[s] = p

        tk.Label(card, text="LIGHT", font=F_SMALL, bg=CARD,
                 fg=MUTED).pack(anchor="w", padx=22, pady=(24, 6))
        led_row = tk.Frame(card, bg=CARD)
        led_row.pack(padx=18, anchor="w")
        self.led_pill = Pill(led_row, "LED OFF", self.toggle_led, w=140, h=40)
        self.led_pill.pack(side="left", padx=4)

        self.refresh_pill = Pill(card, "Refresh state", self.refresh_state,
                                 w=160, h=38)
        self.refresh_pill.pack(pady=(30, 10))

    def _build_footer(self):
        foot = tk.Frame(self, bg=BG)
        foot.pack(fill="x", padx=24, pady=(0, 18))

        row = tk.Frame(foot, bg=BG)
        row.pack(fill="x")
        self.dot = tk.Canvas(row, width=10, height=10, bg=BG,
                             highlightthickness=0)
        self.dot_id = self.dot.create_oval(1, 1, 9, 9, fill=MUTED, outline="")
        self.dot.pack(side="left", pady=(3, 0))
        self.status = tk.StringVar(value="Loading fans...")
        tk.Label(row, textvariable=self.status, font=F_BODY, bg=BG, fg=TEXT,
                 wraplength=350, justify="left").pack(side="left", padx=8)

        self.quota_this = tk.StringVar(value="")
        tk.Label(foot, textvariable=self.quota_this, font=F_SMALL, bg=BG,
                 fg=MUTED).pack(anchor="w", pady=(6, 0))
        self.quota_total = tk.StringVar(value="")
        tk.Label(foot, textvariable=self.quota_total, font=F_SMALL, bg=BG,
                 fg=MUTED).pack(anchor="w")

    # ---- helpers ---------------------------------------------------------
    def set_status(self, text, color=TEXT, dot=ACCENT):
        self.status.set(text)
        self.dot.itemconfig(self.dot_id, fill=dot)

    def refresh_quota_labels(self):
        dev = self.current_device_id()
        if dev:
            this = self.counter.current(dev)
            self.quota_this.set(f"This fan: {this} calls today")
        else:
            self.quota_this.set("")
        total = self.counter.total_today()
        self.quota_total.set(
            f"All devices combined: {total}/{DAILY_CAP} calls today")

    def run_async(self, fn, *args):
        def worker():
            try:
                fn(*args)
            except Exception as e:
                print("ERROR:", repr(e))
                self.after(0, lambda: self.set_status(f"{e}", dot=DANGER))
            finally:
                self.after(0, self.refresh_quota_labels)
        threading.Thread(target=worker, daemon=True).start()

    def current_device_id(self):
        i = self.device_box.current()
        return self.devices[i]["device_id"] if i >= 0 else None

    def paint_state(self):
        self.power_btn.set_state(self.power_on)
        self.power_label.configure(text="ON" if self.power_on else "OFF",
                                   fg=GREEN if self.power_on else MUTED)
        for s, pill in self.speed_pills.items():
            pill.set_active(s == self.last_speed)
        self.led_pill.set_text("LED ON" if self.led_on else "LED OFF")
        self.led_pill.set_active(self.led_on, active_col=ACCENT_DK)

    def open_settings(self):
        cfg = load_config()

        def on_save(new_cfg):
            self.api.set_credentials(new_cfg["api_key"], new_cfg["refresh_token"])
            self.set_status("Credentials saved. Loading fans...", dot=ACCENT)
            self.run_async(self.load_devices)

        SettingsDialog(self, cfg, on_save)

    def on_device_change(self):
        self.last_speed = None
        self.power_on = False
        self.led_on = False
        self.paint_state()
        self.refresh_quota_labels()
        self.refresh_state()

    # ---- actions ---------------------------------------------------------
    def load_devices(self):
        self.devices = self.api.list_devices()
        if not self.devices:
            self.after(0, lambda: self.set_status("No fans on this account.",
                                                  dot=DANGER))
            return
        names = [f"{d.get('name', 'Fan')}  ·  {d.get('model', '?')}"
                 for d in self.devices]

        def apply():
            self.device_box["values"] = names
            self.device_box.current(0)
            self.set_status("Reading fan state...", dot=ACCENT)
            self.refresh_quota_labels()
            self.refresh_state()
        self.after(0, apply)

    def refresh_state(self):
        dev = self.current_device_id()
        if not dev:
            return
        self.set_status("Reading fan...", dot=ACCENT)

        def work():
            st = self.api.get_state(dev)
            speed = st.get("last_recorded_speed", st.get("speed"))
            if isinstance(speed, int):
                self.last_speed = speed
            self.power_on = bool(st.get("power"))
            self.led_on = bool(st.get("led"))
            online = "Online" if st.get("is_online") else "Offline"

            def apply():
                self.paint_state()
                self.set_status(f"{online}  ·  speed {speed}",
                                dot=GREEN if st.get("is_online") else DANGER)
            self.after(0, apply)
        self.run_async(work)

    def toggle_power(self):
        dev = self.current_device_id()
        if not dev:
            return
        target = not self.power_on
        self.power_on = target
        self.paint_state()
        self.cmd({"power": target})

    def toggle_led(self):
        dev = self.current_device_id()
        if not dev:
            return
        target = not self.led_on
        self.led_on = target
        self.paint_state()
        self.cmd({"led": target})

    def set_speed(self, target):
        dev = self.current_device_id()
        if not dev:
            return
        self.last_speed = target
        self.paint_state()
        self.set_status(f"Setting speed {target}...", dot=ACCENT)

        def work():
            self.api.send_command(dev, {"speed": target})
            self.after(0, lambda: self.set_status(
                f"Sent speed {target}. Refresh to confirm.", dot=GREEN))
        self.run_async(work)

    def cmd(self, command):
        dev = self.current_device_id()
        if not dev:
            return

        def work():
            self.api.send_command(dev, command)
            self.after(0, lambda: self.set_status(f"Sent {command}", dot=GREEN))
        self.run_async(work)


# --------------------------------------------------------------------------
if __name__ == "__main__":
    app = FanApp()
    app.mainloop()