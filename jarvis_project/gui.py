"""
gui.py — Jarvis Desktop GUI
Entry point: python gui.py

Requires:
    pip install customtkinter

All AI logic lives in main.py — this file handles presentation only.
Run this instead of main.py. main.py's __main__ block is never executed
when imported, so there is no conflict.
"""

import os
import sys
import threading
import datetime
import queue
import json
import traceback
import subprocess
import re

import customtkinter as ctk
from tkinter import messagebox, filedialog
import tkinter as tk

# ── Import core Jarvis engine ─────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import main as jarvis

# =============================================================================
# THEME & PALETTE (Sophisticated Dark Carbon / Cyberpunk Slate)
# =============================================================================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

C = {
    "bg":         "#08090b",   # Deepest void graphite
    "panel":      "#0e1117",   # Dark carbon panel
    "surface":    "#161b22",   # Elevated container surface
    "border":     "#21262d",   # Sleek structural border
    "accent":     "#3b82f6",   # Electric Blue (Interactive Highlight)
    "accent_dim": "#1d4ed8",   # Muted Blue (Secondary Indicators)
    "accent2":    "#8b5cf6",   # Cyber Purple (Specialized / Gemini)
    "green":      "#10b981",   # Vibrant Emerald Green (Ready State)
    "red":        "#ef4444",   # Crimson Red (Alert / Terminal Abort)
    "yellow":     "#f59e0b",   # Amber Gold (Processing Thread)
    "text":       "#f8fafc",   # Clean slate white
    "subtext":    "#64748b",   # Muted cool-grey subheadings
    "user_msg":   "#1e293b",   # Bubble color for User inputs
    "jarvis_msg": "#0f172a",   # Deep slate blue background for Jarvis responses
    "tool_bg":    "#020617",   # Absolute black-blue console terminal
    "tool_text":  "#38bdf8",   # Tech blue monospaced output
}

FONT_BODY  = ("Segoe UI",        12)
FONT_BOLD  = ("Segoe UI",        12, "bold")
FONT_ITALIC = ("Segoe UI",       12, "italic")
FONT_SMALL = ("Segoe UI",        11)
FONT_MONO  = ("Cascadia Code",   11)
FONT_TITLE = ("Segoe UI",        13, "bold")
FONT_HEAD  = ("Segoe UI",        16, "bold")

# =============================================================================
# REDIRECT stdout → GUI log
# =============================================================================
class _StdoutRedirector:
    """Capture everything that would go to the terminal and route it to the GUI."""
    def __init__(self, callback):
        self._cb  = callback
        self._old = sys.stdout

    def write(self, text):
        if text.strip():
            self._cb(text)

    def flush(self):
        pass

    def restore(self):
        sys.stdout = self._old

# =============================================================================
# JARVIS SESSION STATE (shared between GUI and engine thread)
# =============================================================================
class JarvisSession:
    def __init__(self):
        self.history          = []
        self.turn_counter     = 1
        self.system_prompt    = ""
        self.memory_injections = []
        self._lock            = threading.Lock()

    def initialise(self, system_prompt: str, memory_injections: list):
        with self._lock:
            self.system_prompt    = system_prompt
            self.memory_injections = memory_injections
            self.history = [{"role": "system", "content": system_prompt}]
            for inj in memory_injections:
                self.history.append({"role": "system", "content": inj})

    def reset(self):
        with self._lock:
            self.history = [{"role": "system", "content": self.system_prompt}]
            if self.memory_injections:
                self.history.append({"role": "system", "content": self.memory_injections[0]})
            self.turn_counter = 1

    def append(self, msg: dict):
        with self._lock:
            self.history.append(msg)

    def snapshot(self) -> list:
        with self._lock:
            return list(self.history)

# =============================================================================
# SLEEK MODAL DIALOGUES FOR FILE CREATION
# =============================================================================
class CreateKnowledgeDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_success_callback):
        super().__init__(parent)
        self.title("✚ Create Domain Knowledge Base")
        self.geometry("450x250")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.on_success = on_success_callback

        main_frame = ctk.CTkFrame(self, fg_color=C["panel"], corner_radius=0, border_width=1, border_color=C["border"])
        main_frame.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(main_frame, text="CREATE KNOWLEDGE BASE", font=FONT_TITLE, text_color=C["accent"]).pack(anchor="w", padx=16, pady=(16, 8))

        ctk.CTkLabel(main_frame, text="Name (snake_case, e.g. blender_commands):", font=FONT_SMALL, text_color=C["subtext"]).pack(anchor="w", padx=16, pady=(4, 0))
        self._entry_name = ctk.CTkEntry(main_frame, font=FONT_BODY, fg_color=C["surface"], text_color=C["text"], border_color=C["border"], corner_radius=0, height=32)
        self._entry_name.pack(fill="x", padx=16, pady=4)

        ctk.CTkLabel(main_frame, text="One-line Description:", font=FONT_SMALL, text_color=C["subtext"]).pack(anchor="w", padx=16, pady=(4, 0))
        self._entry_desc = ctk.CTkEntry(main_frame, font=FONT_BODY, fg_color=C["surface"], text_color=C["text"], border_color=C["border"], corner_radius=0, height=32)
        self._entry_desc.pack(fill="x", padx=16, pady=4)

        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.pack(fill="x", side="bottom", padx=16, pady=16)

        ctk.CTkButton(btn_frame, text="Cancel", width=80, fg_color=C["surface"], hover_color=C["border"], corner_radius=0, command=self.destroy).pack(side="left")
        ctk.CTkButton(btn_frame, text="Create", width=80, fg_color=C["accent"], hover_color="#1d4ed8", corner_radius=0, command=self._on_submit).pack(side="right")

        self.lift()
        self.focus_force()
        self.grab_set()

    def _on_submit(self):
        name = self._entry_name.get().strip()
        desc = self._entry_desc.get().strip()

        if not name:
            messagebox.showerror("Error", "Name field cannot be empty.")
            return
        if not desc:
            messagebox.showerror("Error", "Description field cannot be empty.")
            return

        self.on_success(name, desc)
        self.destroy()


class CreateSkillDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_success_callback):
        super().__init__(parent)
        self.title("✚ Create Custom Skill")
        self.geometry("450x300")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.on_success = on_success_callback

        main_frame = ctk.CTkFrame(self, fg_color=C["panel"], corner_radius=0, border_width=1, border_color=C["border"])
        main_frame.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(main_frame, text="CREATE CUSTOM SKILL", font=FONT_TITLE, text_color=C["accent"]).pack(anchor="w", padx=16, pady=(16, 8))

        ctk.CTkLabel(main_frame, text="Name (snake_case, e.g. render_scene):", font=FONT_SMALL, text_color=C["subtext"]).pack(anchor="w", padx=16, pady=(4, 0))
        self._entry_name = ctk.CTkEntry(main_frame, font=FONT_BODY, fg_color=C["surface"], text_color=C["text"], border_color=C["border"], corner_radius=0, height=32)
        self._entry_name.pack(fill="x", padx=16, pady=4)

        ctk.CTkLabel(main_frame, text="Domain (e.g. blender, windows, spotify):", font=FONT_SMALL, text_color=C["subtext"]).pack(anchor="w", padx=16, pady=(4, 0))
        self._entry_domain = ctk.CTkEntry(main_frame, font=FONT_BODY, fg_color=C["surface"], text_color=C["text"], border_color=C["border"], corner_radius=0, height=32)
        self._entry_domain.pack(fill="x", padx=16, pady=4)

        ctk.CTkLabel(main_frame, text="One-line Description:", font=FONT_SMALL, text_color=C["subtext"]).pack(anchor="w", padx=16, pady=(4, 0))
        self._entry_desc = ctk.CTkEntry(main_frame, font=FONT_BODY, fg_color=C["surface"], text_color=C["text"], border_color=C["border"], corner_radius=0, height=32)
        self._entry_desc.pack(fill="x", padx=16, pady=4)

        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.pack(fill="x", side="bottom", padx=16, pady=16)

        ctk.CTkButton(btn_frame, text="Cancel", width=80, fg_color=C["surface"], hover_color=C["border"], corner_radius=0, command=self.destroy).pack(side="left")
        ctk.CTkButton(btn_frame, text="Create", width=80, fg_color=C["accent"], hover_color="#1d4ed8", corner_radius=0, command=self._on_submit).pack(side="right")

        self.lift()
        self.focus_force()
        self.grab_set()

    def _on_submit(self):
        name = self._entry_name.get().strip()
        domain = self._entry_domain.get().strip()
        desc = self._entry_desc.get().strip()

        if not name:
            messagebox.showerror("Error", "Name field cannot be empty.")
            return
        if not domain:
            messagebox.showerror("Error", "Domain field cannot be empty.")
            return
        if not desc:
            messagebox.showerror("Error", "Description field cannot be empty.")
            return

        self.on_success(name, domain, desc)
        self.destroy()


# =============================================================================
# MAIN WINDOW
# =============================================================================
class JarvisGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Jarvis Control Center")
        self.geometry("1600x950")
        self.minsize(1200, 750)
        self.configure(fg_color=C["bg"])

        self._session      = JarvisSession()
        self._thinking     = False
        self._log_queue    = queue.Queue()   # stdout lines from engine
        self._reply_queue  = queue.Queue()   # (reply, tool_outputs) from engine

        # File selection paths tracking
        self._sys_core_active_file = None
        self._knowledge_active_file = None
        self._skills_active_file = None

        # Redirect stdout
        self._stdout_redir = _StdoutRedirector(self._log_queue.put)
        sys.stdout = self._stdout_redir

        # Setup base directory trackers
        self._base_work_dir = r"D:\\"
        if not os.path.exists(self._base_work_dir):
            self._base_work_dir = os.path.expanduser("~/Documents")

        self._build_layout()
        self._startup()
        self._poll()

    # ──────────────────────────────────────────────────────────────────────────
    # STARTUP INITIALIZATION
    # ──────────────────────────────────────────────────────────────────────────
    def _startup(self):
        """Perform initial workspace scanning and state initialization."""
        self._scan_workspace_directory()
        self._refresh_status()

        # 1. Ensure core directories and files exist
        jarvis._bootstrap_all_files()
        
        # 2. Fetch master system prompt from the engine
        try:
            sys_prompt = jarvis.get_system_prompt()
        except AttributeError:
            # Fallback if get_system_prompt hasn't been merged into main.py yet
            sys_prompt = "You are Jarvis. Rules:\n- Proceed safely."

        # 3. Load general core memories safely (bypass CLI input loops)
        memories = []
        master_ctx = jarvis.load_memory_into_context(jarvis.MASTER_MEMORY, "master")
        if master_ctx: 
            memories.append(master_ctx)
        
        session_ctx = jarvis.load_memory_into_context(jarvis.SESSION_MEMORY, "session (continued)")
        if session_ctx: 
            memories.append(session_ctx)
            
        try:
            with open(jarvis.INSTRUCTIONS_FILE, "r", encoding="utf-8") as f:
                _instr = f.read().strip()
            if _instr: 
                memories.append("[JARVIS INSTRUCTIONS — always active]\n" + _instr)
        except Exception:
            pass

        # 4. Inject prompt and memories into the active GUI session
        self._session.initialise(sys_prompt, memories)

    # ──────────────────────────────────────────────────────────────────────────
    # LAYOUT DESIGN WITH DYNAMIC RESIZABLE PANES & FLAT CORNERS
    # ──────────────────────────────────────────────────────────────────────────
    def _build_layout(self):
        # Top Command Control Bar
        self._topbar = ctk.CTkFrame(self, fg_color=C["panel"], height=60, corner_radius=0, border_width=1, border_color=C["border"])
        self._topbar.pack(fill="x", side="top")
        self._topbar.pack_propagate(False)

        # Visual indicator element container
        indicator_frame = ctk.CTkFrame(self._topbar, fg_color="transparent")
        indicator_frame.pack(side="left", padx=20, fill="y")

        ctk.CTkLabel(indicator_frame, text="⚡  JARVIS ENGINE",
                     font=FONT_HEAD, text_color=C["accent"]).pack(side="left")

        # Sharp flat indicator status dot
        self._status_dot = ctk.CTkFrame(indicator_frame, width=8, height=8, corner_radius=0, fg_color=C["yellow"])
        self._status_dot.pack(side="left", padx=(15, 5))

        self._status_label = ctk.CTkLabel(indicator_frame, text="Initializing workspace state...",
                                          font=FONT_SMALL, text_color=C["subtext"])
        self._status_label.pack(side="left", padx=5)

        # Control triggers aligned right
        self._abort_btn = ctk.CTkButton(
            self._topbar, text="⛔ Abort Execution", width=145, height=34,
            fg_color=C["red"], hover_color="#991b1b", font=FONT_SMALL,
            corner_radius=0, command=self._abort)
        self._abort_btn.pack(side="right", padx=15, pady=10)

        ctk.CTkButton(
            self._topbar, text="🔄 Clear Session", width=130, height=34,
            fg_color=C["surface"], hover_color=C["border"], font=FONT_SMALL,
            border_width=1, border_color=C["border"], corner_radius=0,
            command=self._new_session).pack(side="right", padx=5, pady=10)

        # Outer Layout Container
        self._main = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        self._main.pack(fill="both", expand=True)

        # Horizontal Paned Window for fully draggable/resizable columns
        self._paned_container = tk.PanedWindow(
            self._main, orient=tk.HORIZONTAL, bg=C["bg"], bd=0, 
            sashwidth=5, sashpad=2, opaqueresize=True
        )
        self._paned_container.pack(fill="both", expand=True, padx=4, pady=4)

        # Build Subsections as modular panels
        self._build_sidebar_panel()
        self._build_chat_panel()
        self._build_activity_panel()
        self._build_dashboard_panel()

        # Add panes dynamically with initial target widths
        self._paned_container.add(self._sidebar, minsize=260)
        self._paned_container.add(self._chat_panel_frame, minsize=400)
        self._paned_container.add(self._activity_panel_frame, minsize=300)
        self._paned_container.add(self._dashboard_panel_frame, minsize=320)

    # ── Sidebar Project Manager (Column 0 Pane) ───────────────────────────────
    def _build_sidebar_panel(self):
        self._sidebar = ctk.CTkFrame(self._paned_container, fg_color=C["panel"], corner_radius=0, border_width=1, border_color=C["border"])
        self._sidebar.grid_columnconfigure(0, weight=1)
        self._sidebar.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(self._sidebar, text="WORKSPACE EXPLORER", font=FONT_TITLE,
                     text_color=C["text"]).grid(row=0, column=0, sticky="w", padx=14, pady=(15, 8))

        # Project Selection Dropdown Setup
        self._project_dropdown = ctk.CTkOptionMenu(
            self._sidebar, values=["Scanning Workspace..."],
            command=self._on_project_switched,
            fg_color=C["surface"], button_color=C["border"],
            button_hover_color=C["accent"], dropdown_fg_color=C["surface"],
            dropdown_hover_color=C["border"], text_color=C["text"], font=FONT_SMALL,
            corner_radius=0
        )
        self._project_dropdown.grid(row=1, column=0, sticky="ew", padx=12, pady=5)

        # Project Creation controls
        actions_frame = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        actions_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=5)
        actions_frame.grid_columnconfigure(0, weight=1)
        actions_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            actions_frame, text="✚ New Project", height=28, font=FONT_SMALL,
            fg_color=C["surface"], hover_color=C["border"], border_width=1, border_color=C["border"],
            corner_radius=0, command=self._create_project_dialog
        ).grid(row=0, column=0, sticky="ew", padx=(0, 2))

        ctk.CTkButton(
            actions_frame, text="📂 Scan Dir", height=28, font=FONT_SMALL,
            fg_color=C["surface"], hover_color=C["border"], border_width=1, border_color=C["border"],
            corner_radius=0, command=self._change_base_work_directory
        ).grid(row=0, column=1, sticky="ew", padx=(2, 0))

        # File Listing View inside Project
        self._file_list_box = ctk.CTkTextbox(
            self._sidebar, font=FONT_MONO, fg_color=C["bg"],
            text_color=C["subtext"], wrap="none", corner_radius=0, state="disabled",
            border_width=1, border_color=C["border"]
        )
        self._file_list_box.grid(row=3, column=0, sticky="nsew", padx=12, pady=8)

        # Workspace Actions Quick shortcuts & Safe Shutdown Trigger
        quick_actions = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        quick_actions.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 15))
        quick_actions.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            quick_actions, text="💻 Open in VS Code", height=32, font=FONT_SMALL,
            fg_color=C["accent"], hover_color="#1d4ed8", corner_radius=0,
            command=self._open_project_in_vscode
        ).grid(row=0, column=0, sticky="ew", pady=(0, 4))

        ctk.CTkButton(
            quick_actions, text="🐚 Open Terminal Here", height=32, font=FONT_SMALL,
            fg_color=C["surface"], hover_color=C["border"], border_width=1, border_color=C["border"],
            corner_radius=0, command=self._open_project_terminal
        ).grid(row=1, column=0, sticky="ew", pady=(0, 4))

        # Master AI Core Shutdown safety switch
        ctk.CTkButton(
            quick_actions, text="🔌 Shutdown Core Engine", height=34, font=FONT_BOLD,
            fg_color=C["red"], hover_color="#991b1b", corner_radius=0,
            command=self._shutdown_engine
        ).grid(row=2, column=0, sticky="ew", pady=(4, 0))

    # ── Chat Frame (Column 1 Pane) ────────────────────────────────────────────
    def _build_chat_panel(self):
        self._chat_panel_frame = ctk.CTkFrame(self._paned_container, fg_color=C["panel"], corner_radius=0, border_width=1, border_color=C["border"])
        self._chat_panel_frame.grid_rowconfigure(1, weight=1)
        self._chat_panel_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self._chat_panel_frame, text="CHAT INTELLIGENCE", font=FONT_TITLE,
                     text_color=C["text"]).grid(row=0, column=0, sticky="w", padx=14, pady=(15, 8))

        self._chat_scroll = ctk.CTkScrollableFrame(
            self._chat_panel_frame, fg_color=C["surface"],
            corner_radius=0, border_width=1, border_color=C["border"])
        self._chat_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 6))
        self._chat_scroll.grid_columnconfigure(0, weight=1)

        input_frame = ctk.CTkFrame(self._chat_panel_frame, fg_color="transparent")
        input_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        input_frame.grid_columnconfigure(0, weight=1)

        self._input = ctk.CTkEntry(
            input_frame, placeholder_text="Specify objectives to execute...",
            font=FONT_BODY, fg_color=C["surface"],
            text_color=C["text"], border_color=C["border"],
            height=42, corner_radius=0)
        self._input.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._input.bind("<Return>",       self._send)

        self._send_btn = ctk.CTkButton(
            input_frame, text="SEND", width=85, height=42,
            fg_color=C["accent"], hover_color="#1d4ed8",
            font=FONT_BOLD, corner_radius=0, command=self._send)
        self._send_btn.grid(row=0, column=1)

    # ── Execution Activity Logs (Column 2 Pane) ───────────────────────────────
    def _build_activity_panel(self):
        self._activity_panel_frame = ctk.CTkFrame(self._paned_container, fg_color=C["panel"], corner_radius=0, border_width=1, border_color=C["border"])
        self._activity_panel_frame.grid_rowconfigure(1, weight=1)
        self._activity_panel_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self._activity_panel_frame, text="SYSTEM EXECUTION ENGINE", font=FONT_TITLE,
                     text_color=C["text"]).grid(row=0, column=0, sticky="w", padx=14, pady=(15, 8))

        self._activity_box = ctk.CTkTextbox(
            self._activity_panel_frame, font=FONT_MONO, fg_color=C["tool_bg"],
            text_color=C["tool_text"], wrap="word",
            state="disabled", corner_radius=0, border_width=1, border_color=C["border"])
        self._activity_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 6))
        self._activity_box._textbox.configure(spacing1=3, spacing2=2, padx=10, pady=10)

        ctk.CTkButton(
            self._activity_panel_frame, text="Clear Logs", width=90, height=28,
            fg_color=C["surface"], hover_color=C["border"], border_width=1, border_color=C["border"],
            font=FONT_SMALL, corner_radius=0,
            command=lambda: self._clear_box(self._activity_box)
        ).grid(row=2, column=0, sticky="e", padx=10, pady=(0, 8))

    # ── Dashboard & Memory Tab Frame (Column 3 Pane) ──────────────────────────
    def _build_dashboard_panel(self):
        self._dashboard_panel_frame = ctk.CTkFrame(self._paned_container, fg_color=C["panel"], corner_radius=0, border_width=1, border_color=C["border"])
        self._dashboard_panel_frame.grid_rowconfigure(1, weight=1)
        self._dashboard_panel_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self._dashboard_panel_frame, text="SYSTEM DATA CORE", font=FONT_TITLE,
                     text_color=C["text"]).grid(row=0, column=0, sticky="w", padx=14, pady=(15, 8))

        self._tabs = ctk.CTkTabview(self._dashboard_panel_frame, fg_color=C["surface"],
                                     segmented_button_fg_color=C["border"],
                                     segmented_button_selected_color=C["accent"],
                                     segmented_button_selected_hover_color="#1d4ed8",
                                     corner_radius=0)
        self._tabs.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))

        for tab in ("Parameters", "System Core", "Knowledge Bases", "Skills", "Manual Tools"):
            self._tabs.add(tab)

        self._build_status_tab()
        self._build_system_core_tab()
        self._build_knowledge_bases_tab()
        self._build_skills_tab()
        self._build_manual_tools_tab()

    # ── Status / System Parameters Tab ────────────────────────────────────────
    def _build_status_tab(self):
        tab = self._tabs.tab("Parameters")
        tab.grid_columnconfigure(0, weight=1)

        def _row(parent, label, row):
            ctk.CTkLabel(parent, text=label, font=FONT_SMALL,
                         text_color=C["subtext"]).grid(
                row=row, column=0, sticky="w", padx=12, pady=(8, 0))
            val = ctk.CTkLabel(parent, text="—", font=FONT_SMALL,
                               text_color=C["text"], wraplength=260, justify="left")
            val.grid(row=row+1, column=0, sticky="w", padx=12, pady=(0, 4))
            return val

        self._lbl_model    = _row(tab, "Cognitive Model",         0)
        self._lbl_goal     = _row(tab, "Active Execution Goal",   2)
        self._lbl_project  = _row(tab, "Workspace Path Context", 4)
        self._lbl_gemini   = _row(tab, "Gemini Research Core",   6)
        self._lbl_ocr      = _row(tab, "Screen OCR Subsystem",    8)
        self._lbl_uia      = _row(tab, "Windows UI Automation",  10)
        self._lbl_turns    = _row(tab, "Interaction Turns",      12)

        ctk.CTkButton(
            tab, text="↻ Hard Refresh State", height=32, font=FONT_SMALL,
            fg_color=C["surface"], hover_color=C["border"], border_width=1, border_color=C["border"],
            corner_radius=0, command=self._refresh_status
        ).grid(row=14, column=0, padx=12, pady=15, sticky="ew")

    # ── Unified System Core Tab (All System Files Editable) ───────────────────
    def _build_system_core_tab(self):
        tab = self._tabs.tab("System Core")
        tab.grid_rowconfigure(1, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        control_frame = ctk.CTkFrame(tab, fg_color="transparent")
        control_frame.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 2))
        control_frame.grid_columnconfigure(0, weight=1)

        self._sys_core_dropdown = ctk.CTkOptionMenu(
            control_frame, values=["Master Memory", "Session Memory", "Instructions", "Paths", "Active Project", "Scratchpad"],
            command=self._on_sys_core_selected,
            fg_color=C["surface"], button_color=C["border"],
            button_hover_color=C["accent"], dropdown_fg_color=C["surface"],
            dropdown_hover_color=C["border"], text_color=C["text"], font=FONT_SMALL,
            corner_radius=0
        )
        self._sys_core_dropdown.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        ctk.CTkButton(
            control_frame, text="💾 Save", width=80, height=28, font=FONT_SMALL,
            fg_color=C["accent"], hover_color="#1d4ed8", corner_radius=0,
            command=self._save_sys_core_file
        ).grid(row=0, column=1, padx=2)

        self._sys_core_box = ctk.CTkTextbox(
            tab, font=FONT_MONO, fg_color=C["tool_bg"],
            text_color=C["text"], wrap="word", corner_radius=0,
            border_width=1, border_color=C["border"]
        )
        self._sys_core_box.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        self._sys_core_box._textbox.configure(spacing1=3, spacing2=2, padx=8, pady=8)

        # Load master memory as default selected
        self._on_sys_core_selected("Master Memory")

    def _get_sys_core_path(self, selection: str) -> str:
        mapping = {
            "Master Memory": jarvis.MASTER_MEMORY,
            "Session Memory": jarvis.SESSION_MEMORY,
            "Instructions": jarvis.INSTRUCTIONS_FILE,
            "Paths": jarvis.PATHS_FILE,
            "Active Project": jarvis._active_project_memory_path,
            "Scratchpad": jarvis.RESPONSE_MEMORY
        }
        return mapping.get(selection)

    def _on_sys_core_selected(self, selected_label: str):
        path = self._get_sys_core_path(selected_label)
        self._sys_core_active_file = path
        if path:
            self._load_file_into_box(self._sys_core_box, path)
        else:
            self._sys_core_box.configure(state="normal")
            self._sys_core_box.delete("1.0", "end")
            self._sys_core_box.insert("end", "(No active file associated with selection)")

    def _save_sys_core_file(self):
        if not self._sys_core_active_file:
            messagebox.showwarning("Save Blocked", "No active target resolved for saving.")
            return
        self._save_box_to_file(self._sys_core_box, self._sys_core_active_file)

    # ── Custom Knowledge Bases Tab (Read, Write & Create) ────────────────────
    def _build_knowledge_bases_tab(self):
        tab = self._tabs.tab("Knowledge Bases")
        tab.grid_rowconfigure(1, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        control_frame = ctk.CTkFrame(tab, fg_color="transparent")
        control_frame.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 2))
        control_frame.grid_columnconfigure(0, weight=1)

        self._knowledge_dropdown = ctk.CTkOptionMenu(
            control_frame, values=["Loading..."],
            command=self._on_knowledge_selected,
            fg_color=C["surface"], button_color=C["border"],
            button_hover_color=C["accent"], dropdown_fg_color=C["surface"],
            dropdown_hover_color=C["border"], text_color=C["text"], font=FONT_SMALL,
            corner_radius=0
        )
        self._knowledge_dropdown.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        ctk.CTkButton(
            control_frame, text="💾 Save", width=70, height=28, font=FONT_SMALL,
            fg_color=C["accent"], hover_color="#1d4ed8", corner_radius=0,
            command=self._save_knowledge_file
        ).grid(row=0, column=1, padx=2)

        ctk.CTkButton(
            control_frame, text="✚ New", width=70, height=28, font=FONT_SMALL,
            fg_color=C["surface"], hover_color=C["border"], border_width=1, border_color=C["border"],
            corner_radius=0, command=self._create_knowledge_dialog
        ).grid(row=0, column=2, padx=2)

        self._knowledge_box = ctk.CTkTextbox(
            tab, font=FONT_MONO, fg_color=C["tool_bg"],
            text_color=C["text"], wrap="word", corner_radius=0,
            border_width=1, border_color=C["border"]
        )
        self._knowledge_box.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        self._knowledge_box._textbox.configure(spacing1=3, spacing2=2, padx=8, pady=8)

        self._refresh_knowledge_dropdown()

    def _refresh_knowledge_dropdown(self, select_name=None):
        try:
            files = []
            if os.path.exists(jarvis.STORAGE_DIR):
                for f in os.listdir(jarvis.STORAGE_DIR):
                    if f.endswith(".md") and os.path.isfile(os.path.join(jarvis.STORAGE_DIR, f)):
                        # Exclude system files from custom list
                        if f.lower() not in ("master_memory.md", "session_memory.md", "instructions.md", "paths.md", "response_memory.md"):
                            files.append(f)
            files.sort()
            
            if not files:
                files = ["No custom bases found"]
                self._knowledge_active_file = None
                self._knowledge_dropdown.configure(values=files)
                self._knowledge_dropdown.set(files[0])
                self._knowledge_box.configure(state="normal")
                self._knowledge_box.delete("1.0", "end")
                self._knowledge_box.insert("end", "(Create a new Knowledge Base to begin writing)")
                self._knowledge_box.configure(state="disabled")
            else:
                self._knowledge_dropdown.configure(values=files)
                target = select_name if select_name in files else files[0]
                self._knowledge_dropdown.set(target)
                self._on_knowledge_selected(target)
        except Exception as e:
            self._activity_append(f"⚠️ Knowledge scan failed: {e}\n")

    def _on_knowledge_selected(self, filename: str):
        if filename == "No custom bases found":
            return
        path = os.path.join(jarvis.STORAGE_DIR, filename)
        self._knowledge_active_file = path
        self._load_file_into_box(self._knowledge_box, path)

    def _save_knowledge_file(self):
        if not self._knowledge_active_file:
            messagebox.showwarning("Save Blocked", "No active knowledge base selected.")
            return
        self._save_box_to_file(self._knowledge_box, self._knowledge_active_file)

    def _create_knowledge_dialog(self):
        CreateKnowledgeDialog(self, self._execute_create_knowledge)

    def _execute_create_knowledge(self, name, description):
        try:
            result = jarvis.create_domain_knowledge(name, description)
            self._activity_append(f"⚙️ {result}\n")
            
            safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', name.strip().lower())
            expected_file = f"{safe_name}.md"
            self._refresh_knowledge_dropdown(select_name=expected_file)
            
            # Sync metadata changes dynamically
            self._load_file_into_box(self._sys_core_box, self._sys_core_active_file)
        except Exception as e:
            messagebox.showerror("Error", f"Failed creating knowledge base: {e}")

    # ── Custom Skills Tab (Read, Write & Create) ──────────────────────────────
    def _build_skills_tab(self):
        tab = self._tabs.tab("Skills")
        tab.grid_rowconfigure(1, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        control_frame = ctk.CTkFrame(tab, fg_color="transparent")
        control_frame.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 2))
        control_frame.grid_columnconfigure(0, weight=1)

        self._skills_dropdown = ctk.CTkOptionMenu(
            control_frame, values=["Loading..."],
            command=self._on_skill_selected,
            fg_color=C["surface"], button_color=C["border"],
            button_hover_color=C["accent"], dropdown_fg_color=C["surface"],
            dropdown_hover_color=C["border"], text_color=C["text"], font=FONT_SMALL,
            corner_radius=0
        )
        self._skills_dropdown.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        ctk.CTkButton(
            control_frame, text="💾 Save", width=70, height=28, font=FONT_SMALL,
            fg_color=C["accent"], hover_color="#1d4ed8", corner_radius=0,
            command=self._save_skill_file
        ).grid(row=0, column=1, padx=2)

        ctk.CTkButton(
            control_frame, text="✚ New", width=70, height=28, font=FONT_SMALL,
            fg_color=C["surface"], hover_color=C["border"], border_width=1, border_color=C["border"],
            corner_radius=0, command=self._create_skill_dialog
        ).grid(row=0, column=2, padx=2)

        self._skills_box = ctk.CTkTextbox(
            tab, font=FONT_MONO, fg_color=C["tool_bg"],
            text_color=C["text"], wrap="word", corner_radius=0,
            border_width=1, border_color=C["border"]
        )
        self._skills_box.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        self._skills_box._textbox.configure(spacing1=3, spacing2=2, padx=8, pady=8)

        self._refresh_skills_dropdown()

    def _refresh_skills_dropdown(self, select_name=None):
        try:
            files = []
            if os.path.exists(jarvis.SKILLS_DIR):
                for f in os.listdir(jarvis.SKILLS_DIR):
                    if f.endswith(".md") and os.path.isfile(os.path.join(jarvis.SKILLS_DIR, f)):
                        files.append(f)
            files.sort()

            if not files:
                files = ["No custom skills found"]
                self._skills_active_file = None
                self._skills_dropdown.configure(values=files)
                self._skills_dropdown.set(files[0])
                self._skills_box.configure(state="normal")
                self._skills_box.delete("1.0", "end")
                self._skills_box.insert("end", "(Create a new Skill to begin writing custom logic)")
                self._skills_box.configure(state="disabled")
            else:
                self._skills_dropdown.configure(values=files)
                target = select_name if select_name in files else files[0]
                self._skills_dropdown.set(target)
                self._on_skill_selected(target)
        except Exception as e:
            self._activity_append(f"⚠️ Skills scan failed: {e}\n")

    def _on_skill_selected(self, filename: str):
        if filename == "No custom skills found":
            return
        path = os.path.join(jarvis.SKILLS_DIR, filename)
        self._skills_active_file = path
        self._load_file_into_box(self._skills_box, path)

    def _save_skill_file(self):
        if not self._skills_active_file:
            messagebox.showwarning("Save Blocked", "No active skill selected.")
            return
        self._save_box_to_file(self._skills_box, self._skills_active_file)

    def _create_skill_dialog(self):
        CreateSkillDialog(self, self._execute_create_skill)

    def _execute_create_skill(self, name, domain, description):
        try:
            initial_content = (
                f"## Summary\n"
                f"Instructions to execute custom skill workflow on {domain}.\n\n"
                f"## Action Checklist\n"
                f"1. [ ] State objective details.\n"
                f"2. [ ] Invoke terminal execution calls.\n"
            )
            result = jarvis.create_domain_skill(name, domain, description, initial_content)
            self._activity_append(f"⚙️ {result}\n")

            safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', name.strip().lower())
            expected_file = f"{safe_name}.md"
            self._refresh_skills_dropdown(select_name=expected_file)
            
            # Sync indexes dynamically
            self._load_file_into_box(self._sys_core_box, self._sys_core_active_file)
        except Exception as e:
            messagebox.showerror("Error", f"Failed creating custom skill: {e}")

    # ── Manual Tools Tab (Execute Sandbox) ────────────────────────────────────
    def _build_manual_tools_tab(self):
        tab = self._tabs.tab("Manual Tools")
        tab.grid_rowconfigure(2, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        control_frame = ctk.CTkFrame(tab, fg_color="transparent")
        control_frame.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 2))
        control_frame.grid_columnconfigure(0, weight=1)

        # Retrieve and sort available tool names directly from Jarvis schema
        tool_names = [t["function"]["name"] for t in jarvis.tools]
        tool_names.sort()

        self._manual_tool_dropdown = ctk.CTkOptionMenu(
            control_frame, values=tool_names,
            command=self._on_manual_tool_selected,
            fg_color=C["surface"], button_color=C["border"],
            button_hover_color=C["accent"], dropdown_fg_color=C["surface"],
            dropdown_hover_color=C["border"], text_color=C["text"], font=FONT_SMALL,
            corner_radius=0
        )
        self._manual_tool_dropdown.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        ctk.CTkButton(
            control_frame, text="▶ Execute Tool", width=120, height=28, font=FONT_SMALL,
            fg_color=C["accent"], hover_color="#1d4ed8", corner_radius=0,
            command=self._execute_manual_tool
        ).grid(row=0, column=1, padx=2)

        # Dynamic parameter entries area
        self._manual_args_frame = ctk.CTkScrollableFrame(
            tab, fg_color=C["surface"], height=140,
            corner_radius=0, border_width=1, border_color=C["border"]
        )
        self._manual_args_frame.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        self._manual_args_frame.grid_columnconfigure(1, weight=1)

        self._manual_arg_entries = {}

        # Safe execution output sink
        self._manual_output_box = ctk.CTkTextbox(
            tab, font=FONT_MONO, fg_color=C["tool_bg"],
            text_color=C["tool_text"], wrap="word", corner_radius=0,
            border_width=1, border_color=C["border"]
        )
        self._manual_output_box.grid(row=2, column=0, sticky="nsew", padx=4, pady=4)
        self._manual_output_box._textbox.configure(spacing1=3, spacing2=2, padx=8, pady=8)

        # Initial trigger
        if tool_names:
            self._manual_tool_dropdown.set(tool_names[0])
            self._on_manual_tool_selected(tool_names[0])

    def _on_manual_tool_selected(self, tool_name: str):
        # Destroy old argument inputs
        for widget in self._manual_args_frame.winfo_children():
            widget.destroy()
        self._manual_arg_entries.clear()

        # Locate tool schema to build arguments dynamically
        schema = next((t["function"] for t in jarvis.tools if t["function"]["name"] == tool_name), None)
        if not schema:
            return

        props = schema.get("parameters", {}).get("properties", {})
        required = schema.get("parameters", {}).get("required", [])

        row = 0
        for arg_name, arg_details in props.items():
            req_str = " *" if arg_name in required else ""
            desc = arg_details.get("description", "")
            
            lbl = ctk.CTkLabel(self._manual_args_frame, text=f"{arg_name}{req_str}", font=FONT_BOLD, text_color=C["subtext"])
            lbl.grid(row=row, column=0, sticky="ne", padx=(5, 10), pady=(5, 5))

            entry = ctk.CTkEntry(self._manual_args_frame, font=FONT_BODY, fg_color=C["bg"], text_color=C["text"], border_color=C["border"], corner_radius=0)
            entry.grid(row=row, column=1, sticky="ew", padx=(0, 5), pady=(5, 5))
            
            if desc:
                entry.configure(placeholder_text=desc)

            self._manual_arg_entries[arg_name] = entry
            row += 1
            
        if not props:
            ctk.CTkLabel(self._manual_args_frame, text="No arguments required for this tool.", font=FONT_SMALL, text_color=C["subtext"]).grid(row=0, column=0, pady=10)

    def _execute_manual_tool(self):
        tool_name = self._manual_tool_dropdown.get()
        # Collect parameters, filtering out empty entries
        args = {name: entry.get() for name, entry in self._manual_arg_entries.items() if entry.get().strip()}
        
        self._manual_output_box.configure(state="normal")
        self._manual_output_box.delete("1.0", "end")
        self._manual_output_box.insert("end", f"[Executing tool sandbox call: {tool_name}...]\n")
        self._manual_output_box.configure(state="disabled")

        def run_tool_background():
            try:
                out = ""
                # Dispatch explicitly via specific patterns found in main.py
                if tool_name in ["read_aggregated_text", "query_gemini_app", "manage_gemini_chat"]:
                    if jarvis._UIA_AVAILABLE and hasattr(jarvis, 'ui_navigator') and jarvis.ui_navigator:
                        func = getattr(jarvis.ui_navigator, tool_name)
                        out = func(**args)
                    else:
                        out = "UI Automation is currently unavailable."
                
                # Path resolution utilities that require processing before calling
                elif tool_name == "read_local_file":
                    res, _ = jarvis.resolve_file_path(args.get("path", ""))
                    out = jarvis.read_local_file(res)
                elif tool_name == "write_local_file":
                    res, _ = jarvis.resolve_file_path(args.get("path", ""))
                    out = jarvis.write_local_file(res, args.get("content", ""))
                elif tool_name == "append_local_file":
                    res, _ = jarvis.resolve_file_path(args.get("path", ""))
                    out = jarvis.append_local_file(res, args.get("content", ""))
                
                # Image data needs to be truncated to avoid completely freezing the textbox
                elif tool_name == "fallback_view_screen":
                    out = jarvis.capture_screen_to_ram()
                    if len(out) > 1000 and not out.startswith("Error"):
                        out = f"Screenshot successfully captured to RAM ({len(out)} bytes of Base64 Data).\n\n(Raw Base64 string is hidden here to prevent GUI lag, but tool is functional.)"

                elif tool_name == "execute_terminal_command":
                    out = jarvis.execute_terminal_command(args.get("command", ""), args.get("working_directory", ""))
                
                # Standard Direct Mapping
                else:
                    if hasattr(jarvis, tool_name):
                        func = getattr(jarvis, tool_name)
                        # Coerce datatypes safely mapping schema definition (e.g. string to int for coords)
                        schema = next((t["function"] for t in jarvis.tools if t["function"]["name"] == tool_name), None)
                        if schema:
                            props = schema.get("parameters", {}).get("properties", {})
                            for k, v in args.items():
                                if props.get(k, {}).get("type") == "integer":
                                    try: args[k] = int(v)
                                    except ValueError: pass
                                elif props.get(k, {}).get("type") == "number":
                                    try: args[k] = float(v)
                                    except ValueError: pass
                        
                        out = func(**args)
                    else:
                        out = f"Error: Function '{tool_name}' not mapped directly in Jarvis namespace."

                self.after(0, self._update_manual_output, str(out))
            except Exception as e:
                self.after(0, self._update_manual_output, f"Tool Exception Caught:\n{str(e)}\n\nTraceback:\n{traceback.format_exc()}")

        # Ensure UI does not freeze during tool execution (like waiting on Gemini or terminal)
        threading.Thread(target=run_tool_background, daemon=True).start()

    def _update_manual_output(self, text: str):
        self._manual_output_box.configure(state="normal")
        self._manual_output_box.delete("1.0", "end")
        self._manual_output_box.insert("end", text)
        self._manual_output_box.configure(state="disabled")

    # ──────────────────────────────────────────────────────────────────────────
    # INTERACTIVE WORKSPACE ENGINE & SIDEBAR MECHANICS
    # ──────────────────────────────────────────────────────────────────────────
    def _scan_workspace_directory(self):
        """Scans the designated workspace directory for active project profiles."""
        self._set_status("Scanning workspace directories...", C["yellow"])
        
        if not os.path.exists(self._base_work_dir):
            os.makedirs(self._base_work_dir, exist_ok=True)

        try:
            # Enumerate folders inside base workspace
            subdirs = [
                d for d in os.listdir(self._base_work_dir) 
                if os.path.isdir(os.path.join(self._base_work_dir, d))
            ]
            
            project_list = []
            for subdir in subdirs:
                project_list.append(subdir)

            project_list.sort()
            
            if not project_list:
                project_list = ["Create first project..."]

            # Update option dropdown cleanly on main thread
            self.after(0, lambda: self._project_dropdown.configure(values=project_list))
            
            # Select first available workspace cleanly
            if project_list and project_list[0] != "Create first project...":
                self.after(0, lambda: self._project_dropdown.set(project_list[0]))
                self.after(0, lambda: self._on_project_switched(project_list[0]))
            else:
                self.after(0, lambda: self._set_status("Workspace Empty", C["subtext"]))

        except Exception as e:
            self._activity_append(f"⚠️ Scan failed: {e}\n")

    def _on_project_switched(self, selected_project: str):
        """Dispatches configuration changes, updates relative memory variables, and switches contexts."""
        if selected_project == "Create first project...":
            return

        project_dir = os.path.join(self._base_work_dir, selected_project)
        project_file = os.path.join(project_dir, "project_memory.md")
        jarvis._active_project_memory_path = project_file

        # Auto-create active memory if it is missing
        if not os.path.exists(project_file):
            try:
                os.makedirs(project_dir, exist_ok=True)
                jarvis.write_local_file(
                    project_file,
                    f"# Project Memory: {selected_project}\n"
                    f"Created: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                )
            except Exception as e:
                self._activity_append(f"⚠️ Memory Write failure: {e}\n")

        # Pull contents dynamically into the active conversational context
        try:
            content = open(project_file, encoding="utf-8").read().strip()
            if content:
                # Flush old project memory and append newly updated profile
                self._session.memory_injections = [
                    inj for inj in self._session.memory_injections 
                    if not inj.startswith("[JARVIS PROJECT MEMORY")
                ]
                self._session.memory_injections.append(
                    f"[JARVIS PROJECT MEMORY — {selected_project}]\n{content}"
                )
                
                # Rebuild current live session context
                self._session.history = [
                    msg for msg in self._session.history 
                    if not (msg.get("role") == "system" and msg.get("content", "").startswith("[JARVIS PROJECT MEMORY"))
                ]
                self._session.history.append({
                    "role": "system",
                    "content": f"[JARVIS PROJECT MEMORY — {selected_project}]\n{content}"
                })
        except Exception as e:
            self._activity_append(f"⚠️ Context injection failure: {e}\n")

        # Log updates
        jarvis.update_memory("master", f"Active project context switched to: {selected_project} ({project_dir})")
        self._chat_append("system", f"[Workspace context switched to: {selected_project}]\n")
        
        self._set_status("Ready", C["green"])
        self._refresh_status()
        self._refresh_file_list(project_dir)

        # Force active load if dropdown is currently viewing "Active Project"
        if self._sys_core_active_file == jarvis._active_project_memory_path or self._sys_core_dropdown.get() == "Active Project":
            self._on_sys_core_selected("Active Project")

    def _refresh_file_list(self, directory: str):
        """Displays direct physical folders and files contained in the active workspace sidebar."""
        self._file_list_box.configure(state="normal")
        self._file_list_box.delete("1.0", "end")
        
        try:
            if os.path.exists(directory):
                files = os.listdir(directory)
                files.sort(key=lambda x: os.path.isdir(os.path.join(directory, x)), reverse=True)
                
                self._file_list_box.insert("end", f"📁 {os.path.basename(directory)}\n")
                for f in files:
                    icon = "📁 " if os.path.isdir(os.path.join(directory, f)) else "📄 "
                    self._file_list_box.insert("end", f"  {icon}{f}\n")
            else:
                self._file_list_box.insert("end", "Empty Directory Context")
        except Exception as e:
            self._file_list_box.insert("end", f"Error scanning files: {e}")
            
        self._file_list_box.configure(state="disabled")

    def _create_project_dialog(self):
        """Launches a sleek, non-blocking window input dialog to generate a new project context."""
        dialog = ctk.CTkInputDialog(text="Enter new Project/Workspace name:", title="✚ New Project")
        p_name = dialog.get_input()
        
        if p_name and p_name.strip():
            clean_name = p_name.strip()
            project_dir = os.path.join(self._base_work_dir, clean_name)
            
            if os.path.exists(project_dir):
                messagebox.showerror("Conflict", "A directory with this name already exists inside current base path.")
                return
                
            os.makedirs(project_dir, exist_ok=True)
            project_file = os.path.join(project_dir, "project_memory.md")
            jarvis.write_local_file(
                project_file,
                f"# Project Memory: {clean_name}\n"
                f"Created: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"Base Execution context initialized successfully.\n"
            )
            
            # Recalibrate workspace directory values
            self._scan_workspace_directory()
            self._project_dropdown.set(clean_name)
            self._on_project_switched(clean_name)

    def _change_base_work_directory(self):
        """Modifies physical folder context pointing the base scanning workspace."""
        new_dir = filedialog.askdirectory(title="Select Base Scan Workspace Directory")
        if new_dir:
            self._base_work_dir = os.path.abspath(new_dir)
            self._chat_append("system", f"[Base scan directory moved to: {self._base_work_dir}]\n")
            self._scan_workspace_directory()

    def _open_project_in_vscode(self):
        """Shortcut action that directly deploys the active workspace inside Visual Studio Code."""
        proj = jarvis._active_project_memory_path
        if proj:
            dir_path = os.path.dirname(proj)
            try:
                subprocess.Popen(f'code "{dir_path}"', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self._activity_append(f"⚙️ VS Code deployed on: {dir_path}\n")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to execute VS Code command alias: {e}")
        else:
            messagebox.showwarning("Context Missing", "No active workspace is selected.")

    def _open_project_terminal(self):
        """Shortcut command launching a detached PowerShell window directly focused on the active workspace."""
        proj = jarvis._active_project_memory_path
        if proj:
            dir_path = os.path.dirname(proj)
            try:
                subprocess.Popen(f'powershell -NoExit -Command "cd \'{dir_path}\'"', shell=True)
                self._activity_append(f"⚙️ PowerShell launched focused on: {dir_path}\n")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to launch shell console: {e}")
        else:
            messagebox.showwarning("Context Missing", "No active workspace is selected.")

    # ──────────────────────────────────────────────────────────────────────────
    # SEND & RECEIVE INTERACTIVE MANAGEMENT
    # ──────────────────────────────────────────────────────────────────────────
    def _send(self, event=None):
        if self._thinking:
            return

        user_input = self._input.get().strip()
        if not user_input:
            return

        self._input.delete(0, "end")
        self._chat_append("user", user_input)

        # Format execution instruction payload
        approval_kw = ["yes", "grant", "approve", "run it", "go ahead", "y"]
        if any(kw in user_input.lower() for kw in approval_kw):
            payload = f"{user_input} [USER MANUALLY GRANTED BYPASS]"
        else:
            payload = (
                f"{user_input}\n\n"
                "[SYSTEM]: For any multi-step task or document processing: "
                "call write_response_memory with a numbered plan FIRST, then execute. "
                "If this requires a shell command, call execute_terminal_command. "
                "If it requires interacting with an app window, call click_ui_element "
                "(UI Automation) — do not use screen/OCR tools unless explicitly asked."
            )

        self._session.append({"role": "user", "content": payload})

        # Launch background engine thread
        self._thinking = True
        self._set_status("Executing turns...", C["yellow"])
        self._send_btn.configure(state="disabled")
        self._abort_btn.configure(fg_color=C["red"])

        t = threading.Thread(
            target=self._run_turn,
            args=(list(self._session.snapshot()),),
            daemon=True
        )
        t.start()

    def _run_turn(self, history_snapshot: list):
        try:
            jarvis._abort_event.clear()
            reply, tool_outputs = jarvis.process_chat_turn(history_snapshot)

            with self._session._lock:
                self._session.history = history_snapshot
                self._session.turn_counter += 1

            self._reply_queue.put(("ok", reply, tool_outputs))
        except Exception as e:
            self._reply_queue.put(("err", str(e), []))

    # ──────────────────────────────────────────────────────────────────────────
    # MAIN THREAD POLLING & DYNAMIC REFRESH LOOP (Every 80 ms)
    # ──────────────────────────────────────────────────────────────────────────
    def _poll(self):
        # Flush standard output stream lines to UI Activity monitor
        while not self._log_queue.empty():
            try:
                line = self._log_queue.get_nowait()
                self._activity_append(line)
            except queue.Empty:
                break

        # Render responses when tool execution finishes
        if not self._reply_queue.empty():
            try:
                status, reply, tool_outputs = self._reply_queue.get_nowait()
            except queue.Empty:
                status = None

            if status == "ok":
                self._chat_append("jarvis", reply)
                self._set_status("Ready", C["green"])
                
                # Dynamic memory updates
                threading.Thread(
                    target=jarvis.python_trigger_memory_update,
                    args=(tool_outputs, reply),
                    daemon=True
                ).start()
                
                # Auto-refresh active loaded boxes representing state files on disk
                if hasattr(self, "_sys_core_active_file") and self._sys_core_active_file:
                    self._load_file_into_box(self._sys_core_box, self._sys_core_active_file)
                if hasattr(self, "_knowledge_active_file") and self._knowledge_active_file:
                    self._load_file_into_box(self._knowledge_box, self._knowledge_active_file)
                if hasattr(self, "_skills_active_file") and self._skills_active_file:
                    self._load_file_into_box(self._skills_box, self._skills_active_file)
                
                proj = jarvis._active_project_memory_path
                if proj:
                    self._refresh_file_list(os.path.dirname(proj))
                
                self._refresh_status()

            elif status == "err":
                self._chat_append("error", f"[Engine error: {reply}]\n")
                self._set_status("Error Exception", C["red"])

            self._thinking = False
            self._send_btn.configure(state="normal")
            self._abort_btn.configure(fg_color=C["red"]) # Reset abort color if successful

        self.after(80, self._poll)

    # ──────────────────────────────────────────────────────────────────────────
    # CORE CONTROLLER ACTIONS
    # ──────────────────────────────────────────────────────────────────────────
    def _abort(self):
        jarvis._abort_event.set()
        self._set_status("Aborted", C["red"])
        self._activity_append("🛑 Execution pipeline aborted by user (Ctrl+Q)\n")

    def _new_session(self):
        if self._thinking:
            messagebox.showwarning("Active Session Execution", "Please wait for current run to finish or click Abort first.")
            return
        if not messagebox.askyesno("Confirm Clear", "Clear current session context and reset memories?"):
            return

        try:
            if os.path.exists(jarvis.SESSION_MEMORY):
                os.remove(jarvis.SESSION_MEMORY)
            jarvis._current_goal = None
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            jarvis.write_local_file(
                jarvis.SESSION_MEMORY,
                f"# Jarvis Session Memory\nSession started: {ts}\n\n"
                f"{jarvis.GOAL_SECTION_HEADER}\n_No active goal._\n\n"
                f"{jarvis.GOAL_SECTION_END}\n"
            )
            self._session.reset()
            self._clear_chat()
            self._chat_append("system", "[Session wiped, starting fresh context]\n")
            self._refresh_status()
            self._set_status("Ready", C["green"])
        except Exception as e:
            messagebox.showerror("Error resetting session", str(e))

    def _shutdown_engine(self):
        """Safely stops model threads, flushes logging streams, and terminates application gracefully."""
        if self._thinking:
            if not messagebox.askyesno("Engine Busy", "A processing cycle is currently executing. Force shut down?"):
                return
            jarvis._abort_event.set()
        
        self._activity_append("🔌 Shutting down Jarvis Engine Core...\n")
        self._set_status("Shutting Down", C["red"])
        self.after(500, self._complete_shutdown)

    def _complete_shutdown(self):
        # Restore stream handlers cleanly
        self._stdout_redir.restore()
        self.destroy()

    # ──────────────────────────────────────────────────────────────────────────
    # DASHBOARD HELPERS & RENDERERS
    # ──────────────────────────────────────────────────────────────────────────
    def _refresh_status(self):
        self._lbl_model.configure(text=jarvis.MODEL_NAME)
        self._lbl_goal.configure(
            text=jarvis._current_goal or "None active",
            text_color=C["accent"] if jarvis._current_goal else C["subtext"]
        )
        proj = jarvis._active_project_memory_path
        self._lbl_project.configure(
            text=os.path.dirname(proj) if proj else "No project selected",
            text_color=C["green"] if proj else C["subtext"]
        )
        self._lbl_gemini.configure(
            text="✅ System Connected" if jarvis._GEMINI_AVAILABLE else "⚠️  Unconnected",
            text_color=C["green"] if jarvis._GEMINI_AVAILABLE else C["yellow"]
        )
        self._lbl_ocr.configure(
            text="✅ System Connected" if jarvis._TESSERACT_AVAILABLE else "⚠️  Unconnected",
            text_color=C["green"] if jarvis._TESSERACT_AVAILABLE else C["yellow"]
        )
        self._lbl_uia.configure(
            text="✅ System Connected" if jarvis._UIA_AVAILABLE else "⚠️  Unconnected",
            text_color=C["green"] if jarvis._UIA_AVAILABLE else C["yellow"]
        )
        self._lbl_turns.configure(
            text=str(self._session.turn_counter)
        )

    def _refresh_skills(self):
        self._refresh_skills_dropdown()

    def _load_file_into_box(self, box, filepath):
        box.configure(state="normal")
        box.delete("1.0", "end")
        try:
            if filepath and os.path.exists(filepath):
                content = open(filepath, encoding="utf-8").read()
                box.insert("end", content)
            else:
                box.insert("end", f"(File empty or pending setup on disk)")
        except Exception as e:
            box.insert("end", f"Read Error: {e}")

    def _save_box_to_file(self, box, filepath):
        if not filepath:
            messagebox.showwarning("Save Stopped", "No valid file target path is resolved.")
            return
        content = box.get("1.0", "end-1c") # Remove trailing newline added by tkinter
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            self._activity_append(f"💾 Updated context file: {filepath}\n")
        except Exception as e:
            messagebox.showerror("Failed to write parameters to disk", str(e))

    # ──────────────────────────────────────────────────────────────────────────
    # CORE INTERACTIVE GRAPHICAL HELPERS & RICH MARKDOWN RENDERING
    # ──────────────────────────────────────────────────────────────────────────
    def _chat_append(self, tag: str, text: str):
        """Compiles raw markdown blocks and appends them in beautifully sized real message bubbles."""
        # Ensure scroll container updates geometry
        self._chat_scroll.update_idletasks()

        if tag in ("system", "error"):
            message_frame = ctk.CTkFrame(self._chat_scroll, fg_color="transparent")
            message_frame.pack(fill="x", padx=12, pady=6)
            
            lbl_text = f"── {text} ──" if tag == "system" else f"── [ Engine Error ] ──\n{text}"
            color = C["subtext"] if tag == "system" else C["red"]
            
            lbl = ctk.CTkLabel(message_frame, text=lbl_text, font=FONT_SMALL, text_color=color, justify="center")
            lbl.pack(anchor="center")
            
            self.after(50, self._scroll_to_bottom)
            return

        # Prepare individual speaker bubbles
        message_frame = ctk.CTkFrame(self._chat_scroll, fg_color="transparent")
        
        if tag == "user":
            message_frame.pack(fill="x", anchor="e", padx=(60, 10), pady=6)
            header_text = "You"
            header_anchor = "e"
            bubble_bg = C["user_msg"]
            bubble_anchor = "e"
        else:
            message_frame.pack(fill="x", anchor="w", padx=(10, 60), pady=6)
            header_text = "Jarvis"
            header_anchor = "w"
            bubble_bg = C["jarvis_msg"]
            bubble_anchor = "w"

        # Display speaker header labels
        header_lbl = ctk.CTkLabel(message_frame, text=header_text, font=FONT_SMALL, text_color=C["subtext"])
        header_lbl.pack(anchor=header_anchor, padx=12, pady=(0, 2))

        # Core container bubble frame with modern padding and rounded corners
        bubble_frame = ctk.CTkFrame(
            message_frame, 
            fg_color=bubble_bg, 
            corner_radius=12, 
            border_width=1, 
            border_color=C["border"]
        )
        bubble_frame.pack(anchor=bubble_anchor)

        # Compute sensible character columns dynamically based on line lengths
        raw_lines = text.splitlines()
        max_line_len = max(len(l) for l in raw_lines) if raw_lines else 0
        optimal_width = min(65, max(25, max_line_len))

        # Use an embedded select/copy enabled borderless text component
        text_box = tk.Text(
            bubble_frame,
            font=FONT_BODY,
            bg=bubble_bg,
            fg=C["text"],
            bd=0,
            highlightthickness=0,
            wrap="word",
            padx=12,
            pady=10,
            width=optimal_width,
            insertbackground=C["text"]
        )
        text_box.pack(fill="both", expand=True)

        # Style compilation selectors
        text_box.tag_config("md_bold", font=FONT_BOLD, foreground=C["text"])
        text_box.tag_config("md_italic", font=FONT_ITALIC, foreground=C["text"])
        text_box.tag_config("md_code_block", font=FONT_MONO, background=C["tool_bg"], foreground=C["tool_text"])
        text_box.tag_config("md_inline_code", font=FONT_MONO, background=C["surface"], foreground=C["tool_text"])
        text_box.tag_config("md_header", font=FONT_HEAD, foreground=C["accent"])
        text_box.tag_config("md_bullet", foreground=C["accent2"])

        in_code_block = False
        for line in raw_lines:
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                text_box.insert("end", "─" * (optimal_width - 4) + "\n")
                continue

            if in_code_block:
                text_box.insert("end", f"{line}\n", "md_code_block")
                continue

            if line.startswith("#"):
                clean_header = line.lstrip("#").strip()
                text_box.insert("end", f"{clean_header}\n", "md_header")
                continue

            bullet_prefix = ""
            if line.strip().startswith("- ") or line.strip().startswith("* "):
                bullet_prefix = " • "
                line = line.strip()[2:]

            segments = re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)", line)
            
            if bullet_prefix:
                text_box.insert("end", bullet_prefix, "md_bullet")
            
            for segment in segments:
                if not segment:
                    continue
                if segment.startswith("**") and segment.endswith("**"):
                    text_box.insert("end", segment[2:-2], "md_bold")
                elif segment.startswith("*") and segment.endswith("*"):
                    text_box.insert("end", segment[1:-1], "md_italic")
                elif segment.startswith("`") and segment.endswith("`"):
                    text_box.insert("end", segment[1:-1], "md_inline_code")
                else:
                    text_box.insert("end", segment)
            
            text_box.insert("end", "\n")

        # Trim last newline safely
        if text_box.get("end-2c", "end-1c") == "\n":
            text_box.delete("end-2c", "end-1c")

        text_box.configure(state="disabled")

        # Set exact widget height based on total displaylines
        text_box.update_idletasks()
        try:
            display_lines = text_box.count("1.0", "end", "displaylines")[0]
        except Exception:
            display_lines = int(text_box.index("end-1c").split(".")[0])
        
        text_box.configure(height=max(1, display_lines))

        # Push the scrollbar automatically down to reveal the newest content block
        self.after(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        """Forces the scroll container layout to slide smoothly to reveal new turns."""
        try:
            if hasattr(self._chat_scroll, "_parent_canvas"):
                self._chat_scroll._parent_canvas.yview_moveto(1.0)
            elif hasattr(self._chat_scroll, "_canvas"):
                self._chat_scroll._canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _clear_chat(self):
        """Removes all packed chat bubble frames from the viewport."""
        for widget in self._chat_scroll.winfo_children():
            widget.destroy()

    def _activity_append(self, text: str):
        self._activity_box.configure(state="normal")
        self._activity_box.insert("end", text)
        self._activity_box.configure(state="disabled")
        self._activity_box.see("end")

    def _clear_box(self, box):
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.configure(state="disabled")

    def _set_status(self, text: str, colour: str = C["subtext"]):
        self._status_label.configure(text=text, text_color=colour)
        # Match flat indicator state dot visually (no anti-aliasing notches)
        if colour == C["green"]:
            self._status_dot.configure(fg_color=C["green"])
        elif colour == C["yellow"]:
            self._status_dot.configure(fg_color=C["yellow"])
        else:
            self._status_dot.configure(fg_color=C["red"])

    def _bind_keys(self):
        self.bind_all("<Control-q>", lambda e: self._abort())

    def on_close(self):
        self._shutdown_engine()

# =============================================================================
# ENTRYPOINT DETECTORS
# =============================================================================
if __name__ == "__main__":
    app = JarvisGUI()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app._bind_keys()
    app.mainloop()