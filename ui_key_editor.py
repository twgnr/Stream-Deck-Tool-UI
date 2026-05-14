#--------------------------------------------------------------------
# Import packages
#--------------------------------------------------------------------
import os
import json
import shutil
import tkinter as tk
import matplotlib.font_manager

#--------------------------------------------------------------------
# Import sub-packages
#--------------------------------------------------------------------
from tkinter import filedialog, messagebox, colorchooser, simpledialog
from ttkbootstrap import ttk
from ttkbootstrap.tooltip import ToolTip
#--------------------------------------------------------------------
# Import local packages
#--------------------------------------------------------------------
from config_manager import ICON_FOLDER, save_config, generate_layer_name
from audio_utils import list_audio_devices

PAYLOAD_TOOLTIPS = {
    "execute": "The command or full path to the executable to run.\nExample: C:\\Windows\\System32\\calc.exe",
    "smart_open": "Focuses an app if running, otherwise launches it.\n\n"
                  "Syntax:\nlaunch_command [| process_name] [| window_title]\n\n"
                  "Example 1 (Simple): notepad.exe\n"
                  "Example 2 (Different Process Name): calc.exe | CalculatorApp.exe\n"
                  "Example 3 (Localized Window Title): calc.exe | CalculatorApp.exe | Rechner",
    "write": "The text to be typed out when the key is pressed.",
    "insert_text": "Pastes the text from the payload. This is very fast and preserves all line breaks and special characters.",
    "toggle_key": "Turns this key into a toggle for a modifier.\nFirst press holds the key down, second press releases it.\nExample payload: alt",
    "toggle_key_timer": "Holds the first key and taps the second key, then auto-releases after 2 seconds.\nSubsequent presses just tap the second key and reset the timer.\nPayload format: hold_key | tap_key\nExample: alt | tab",
    "hotkey":   "A keyboard shortcut combination, joined by '+'.\n\n"
                "Examples:\n"
                "• ctrl+c\n"
                "• alt+shift+f11\n"
                "• win+r\n\n"

                "--- Available Special Keys ---\n"
                "• Modifiers: ctrl, alt, shift, win\n"
                "• Function Keys: f1, f2, ... f12\n"
                "• Navigation: up, down, left, right, home, end, page_up, page_down\n"
                "• Editing: enter, space, backspace, delete, insert, tab, esc\n"
                "• Other: caps_lock, num_lock, print_screen",
    "delay": "The number of seconds to wait in a multi-action sequence.\nExample: 0.5",
    "http_request": "A JSON object defining the web request.\nSee documentation for the required format.",
    "set_audio_device": "The name (or a unique part of the name) of the audio playback device.\nExample: Speakers (Realtek)",
    "volume_up": "Optional: The amount to increase volume (0.0 to 1.0).\nDefault is 0.02 (2%). Example: 0.05",
    "volume_down": "Optional: The amount to decrease volume (0.0 to 1.0).\nDefault is 0.02 (2%). Example: 0.05",
    "cycle_windows": "The executable name of the application whose windows you want to cycle.\n\n"
                     "To cycle through multiple applications, separate their executable names with a pipe '|'.\n\n"
                     "Example (Single App): chrome.exe\n"
                     "Example (Multiple Apps): Code.exe | chrome.exe",
    "command_cycle": "A list of commands to cycle through, separated by '@@@@'.\nExample: Command 1@@@@Command 2",
    "toggle_state": "A JSON list of states. Each state can have its own label, icon, and action.",
    "window_title": "Part of the window title to match for window management actions.",
}

#--------------------------------------------------------------------
# Class
#--------------------------------------------------------------------
class KeyConfigWindow(tk.Toplevel):
    def __init__(self, parent, key_index, config_dta, current_layer, on_save_callback):
        super().__init__(parent)
        self.parent_app = parent
        self.key_index = key_index
        self.current_layer = current_layer
        self.on_save_callback = on_save_callback
        self.transient(parent)
        self.grab_set()
        self.title(f"Configure Key {key_index} — Layer: {current_layer}")
        self.minsize(520, 750)
        self.geometry("720x850")
        
        raw = config_dta.get(current_layer, {}).get(str(key_index), {})
        self.current_config = dict(raw) if isinstance(raw, dict) else {}

        default_pos = self.current_config.get("label_pos", "bottom")
        self.label_pos_var = tk.StringVar(value=default_pos.capitalize())

        self.font_color_var = tk.StringVar(value=self.current_config.get("font_color", "#FFFFFF"))
        self.background_color_var = tk.StringVar(value=self.current_config.get("background", "#000000"))

        self.font_settings = self.current_config.get("font_settings", {})
        self.font_family_var = tk.StringVar(value=self.font_settings.get("family", ""))
        self.font_size_var = tk.StringVar(value=self.font_settings.get("size", ""))

        try:
            font_families = sorted(list(set(f.name for f in matplotlib.font_manager.fontManager.ttflist)))
            self.font_families = font_families
        except Exception as e:
            self.parent_app.log.warning(f"Could not load system fonts: {e}")
            self.font_families = ["Arial", "Courier New", "Times New Roman"] # Fallback

        self.hold_action_config = self.current_config.get("hold_action", {})
        self.hold_action_enabled_var = tk.BooleanVar(value=bool(self.hold_action_config))
        self.hold_action_types = ["execute", "write", "hotkey", "delay"]
        self.hold_action_type_var = tk.StringVar(value=self.hold_action_config.get("action_type", "write"))

        self.display_config = self.current_config.get("display", {})
        
        self.multi_action_list = list(self.current_config.get("payload", [])) if isinstance(self.current_config.get("payload", []), list) else []
        self.action_types = ["execute", "smart_open", "write", "insert_text", "hotkey", "toggle_key", "toggle_key_timer", "layer", "back", "back_to_main", "jump_to_layer", "exit", 
                             "sequence", "multi-action", "toggle_state", "window_management", 
                             "http_request", "set_audio_device", "media_play_pause", "media_next", 
                             "media_previous", "media_stop", "volume_up", "volume_down", "toggle_mute",
                             "cycle_windows", "command_cycle", "clipboard_history"]
        self.sub_action_types = [
            "execute", "smart_open", "write", "insert_text", "hotkey", "toggle_key", "toggle_key_timer", "delay", "window_management", "http_request",
            "key_press", "key_release", "mouse_move", "mouse_click", "mouse_scroll",
            "volume_up", "volume_down", "toggle_mute", "cycle_windows", "command_cycle",
            "clipboard_history",  "back", "back_to_main", "jump_to_layer"
        ]

        self.simple_actions = [
            "execute", "smart_open", "write", "insert_text", "hotkey", "toggle_key", "toggle_key_timer", "http_request",
            "set_audio_device", "volume_up", "volume_down", "toggle_mute",
            "media_play_pause", "media_next", "media_previous", "media_stop",
            "cycle_windows",  "back", "back_to_main", "jump_to_layer"
        ]

        self.second_action_enabled_var = tk.BooleanVar()
        self.second_action_type_var = tk.StringVar()
        self.second_action_type_var.trace_add("write", self.on_second_action_type_change)

        self._edit_widget = None
        self.payload_tooltip = None
        self.second_payload_tooltip = None

        main = ttk.Frame(self, padding=12)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(4, weight=1)

        # Row 0: Key Properties
        form_frame = ttk.LabelFrame(main, text="Key Properties", padding=10)
        form_frame.grid(row=0, column=0, sticky="ew", columnspan=2, pady=(0, 8))
        form_frame.columnconfigure(1, weight=1)

        # Row 1: Display Mode
        display_frame = ttk.LabelFrame(main, text="Display Mode", padding=10)
        display_frame.grid(row=1, column=0, sticky="ew", columnspan=2, pady=(0, 8))
        display_frame.columnconfigure(1, weight=1)

        # Row 3: The frame for the hold options (initially hidden)
        hold_action_frame = ttk.LabelFrame(main, text="Hold Action Configuration", padding=10)
        hold_action_frame.grid(row=3, column=0, sticky="ew", columnspan=2, pady=(0, 8))
        hold_action_frame.columnconfigure(1, weight=1)
        self.hold_options_frame = ttk.Frame(hold_action_frame)
        self.hold_options_frame.grid(row=0, column=0, columnspan=2, sticky="nsew")

        # Row 2: The Checkbox is now a direct child of the main frame
        enable_hold_cb = ttk.Checkbutton(
            hold_action_frame,
            text="Enable Hold Action",
            variable=self.hold_action_enabled_var,
            command=self._on_toggle_hold_action
        )
        enable_hold_cb.grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 10))

        self.create_hold_action_widgets(self.hold_options_frame)

        # Row 4: Main payload container
        self.payload_container = ttk.Frame(main, borderwidth=1, relief="solid", padding=10)
        self.payload_container.grid(row=4, column=0, columnspan=2, sticky="nsew")
        self.payload_container.rowconfigure(0, weight=1)
        self.payload_container.columnconfigure(0, weight=1)

        # Row 5: Save/Cancel buttons
        button_frame = ttk.Frame(main, borderwidth=1, relief="solid", padding=(10, 5))
        button_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        self.create_payload_widgets(self.payload_container)
        self.create_form_widgets(form_frame)
        self.create_display_widgets(display_frame)
        
        ttk.Button(button_frame, text="Save", command=self.save_changes).pack(side="right", padx=6)
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side="right")
        self.on_action_type_change()

        self._on_toggle_hold_action()


    def create_form_widgets(self, parent):
        ttk.Label(parent, text="Label:").grid(row=0, column=0, sticky="w", pady=4)
        self.label_widget = tk.Text(parent, height=3, wrap="word", relief="solid", bd=1)
        self.label_widget.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.label_widget.configure(bg="#222222", fg="white", insertbackground="white")
        self.label_widget.insert("1.0", self.current_config.get("label", ""))

        ttk.Label(parent, text="Label Position:").grid(row=4, column=0, sticky="w", pady=(8,0))
        self.label_pos_combo = ttk.Combobox(
            parent,
            textvariable=self.label_pos_var,
            values=["Top", "Middle", "Bottom"],
            state="readonly"
        )
        self.label_pos_combo.grid(row=4, column=1, sticky="ew", padx=(6, 0))

        ttk.Label(parent, text="Icon:").grid(row=4, column=3, sticky="w", pady=(8,0))
        self.icon_var = tk.StringVar(value=self.current_config.get("icon", ""))
        icon_frame = ttk.Frame(parent)
        icon_frame.grid(row=4, column=4, sticky="ew", pady=(8,0), padx=(6, 0))
        icon_frame.columnconfigure(0, weight=1)
        ttk.Entry(icon_frame, textvariable=self.icon_var).grid(row=4, column=0, sticky="ew")
        ttk.Button(icon_frame, text="...", width=3, command=self.browse_for_icon).grid(row=4, column=1, padx=(6, 0))

        # Font Color Chooser
        ttk.Label(parent, text="Font Color:").grid(row=0, column=3, sticky="w", pady=(8,0))
        color_frame = ttk.Frame(parent)
        color_frame.grid(row=0, column=4, sticky="ew", pady=(8,0), padx=(6, 0))
        color_frame.columnconfigure(0, weight=1)
        ttk.Entry(color_frame, textvariable=self.font_color_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(color_frame, text="...", width=3, command=self.choose_color).grid(row=0, column=1, padx=(6, 0))

        # Widget for per-key Font Path
        ttk.Label(parent, text="Font Family:").grid(row=1, column=0, sticky="w", pady=4)
        self.font_family_combo = ttk.Combobox(
            parent,
            textvariable=self.font_family_var,
            values=self.font_families
        )
        self.font_family_combo.grid(row=1, column=1, sticky="ew", padx=(6, 0))

        # Widget for per-key Font Size
        ttk.Label(parent, text="Font Size:").grid(row=1, column=3, sticky="w", pady=(8,0))
        ttk.Entry(parent, textvariable=self.font_size_var).grid(row=1, column=4, sticky="ew", pady=(8,0), padx=(6, 0))
  
        # Action Type Dropdown
        ttk.Label(parent, text="Action Type:").grid(row=6, column=0, sticky="w", pady=(20,0))
        self.action_type_var = tk.StringVar(value=self.current_config.get("action_type", "execute"))
        self.action_type_var.trace_add("write", lambda *a: self.on_action_type_change())
        ttk.OptionMenu(parent, self.action_type_var, self.action_type_var.get(), *self.action_types).grid(row=6, column=1, sticky="ew", pady=(20,0), padx=(6, 0))

        ttk.Label(parent, text="BG Color:").grid(row=6, column=3, sticky="w", pady=(8,0))
        bg_color_frame = ttk.Frame(parent)
        bg_color_frame.grid(row=6, column=4, sticky="ew", pady=(8,0), padx=(6, 0))
        bg_color_frame.columnconfigure(0, weight=1)
        ttk.Entry(bg_color_frame, textvariable=self.background_color_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(bg_color_frame, text="...", width=3, command=self.choose_background_color).grid(row=0, column=1, padx=(6, 0))


    def create_display_widgets(self, parent):
        ttk.Label(parent, text="Display Type:").grid(row=0, column=0, sticky="w", pady=4)
        self.display_type_var = tk.StringVar()
        display_types = ["Static", "Animated GIF", "Dynamic Data"]
        self.display_type_combo = ttk.Combobox(parent, textvariable=self.display_type_var, values=display_types, state="readonly")
        self.display_type_combo.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.display_type_combo.bind("<<ComboboxSelected>>", self._on_display_type_change)

        self.dynamic_options_frame = ttk.Frame(parent)
        self.dynamic_options_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(5,0))
        self.dynamic_options_frame.columnconfigure(1, weight=1)
        
        ttk.Label(self.dynamic_options_frame, text="Data Provider:").grid(row=0, column=0, sticky="w", pady=4)
        self.provider_var = tk.StringVar()
        providers = ["clock", "cpu_usage", "ram_usage", "disk_space", "network_speed", "gpu_info"]
        ttk.Combobox(self.dynamic_options_frame, textvariable=self.provider_var, values=providers, state="readonly").grid(row=0, column=1, sticky="ew", padx=(6, 0))

        ttk.Label(self.dynamic_options_frame, text="Update Interval (s):").grid(row=1, column=0, sticky="w", pady=4)
        self.interval_var = tk.StringVar()
        ttk.Entry(self.dynamic_options_frame, textvariable=self.interval_var).grid(row=1, column=1, sticky="ew", padx=(6, 0))

        ttk.Label(self.dynamic_options_frame, text="Provider Options:").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Label(self.dynamic_options_frame, text="(e.g., drive=C:/ or email=user@domain.com, folder_path=Inbox/MySubfolder)", font="TkDefaultFont 8").grid(row=3, column=0, sticky="w")
        self.provider_options_var = tk.StringVar()
        ttk.Entry(self.dynamic_options_frame, textvariable=self.provider_options_var).grid(row=2, column=1, rowspan=2, sticky="ew", padx=(6, 0))

        display_type = self.display_config.get("type")
        if display_type == "animated":
            self.display_type_var.set("Animated GIF")

        elif display_type == "dynamic":
            self.display_type_var.set("Dynamic Data")
            self.provider_var.set(self.display_config.get("provider", ""))
            self.interval_var.set(self.display_config.get("update_interval", ""))

            options = self.display_config.get("provider_options", {})
            options_str = ", ".join([f"{k}={v}" for k, v in options.items()])
            self.provider_options_var.set(options_str)
        else:
            self.display_type_var.set("Static")
        
        self._on_display_type_change()


    def create_hold_action_widgets(self, parent):
        """Creates the widgets for configuring the hold action."""
        parent.columnconfigure(1, weight=1)

        ttk.Label(parent, text="Action Type:").grid(row=0, column=0, sticky="w", pady=4)
        ttk.OptionMenu(parent, self.hold_action_type_var, self.hold_action_type_var.get(), *self.hold_action_types).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        
        ttk.Label(parent, text="Payload:").grid(row=1, column=0, sticky="nw", pady=4)
        self.hold_payload_txt = tk.Text(parent, height=4, wrap="word", relief="solid", bd=1)
        self.hold_payload_txt.grid(row=1, column=1, sticky="ew", padx=(6, 0))
        self.hold_payload_txt.configure(bg="#222222", fg="white", insertbackground="white")
        
        payload_val = self.hold_action_config.get("payload", "")
        self.hold_payload_txt.insert("1.0", str(payload_val or ""))


    def choose_background_color(self):
        initial_color = self.background_color_var.get()
        color_code = colorchooser.askcolor(title="Choose Background Color", initialcolor=initial_color or "#000000")
        if color_code and color_code[1]:
            self.background_color_var.set(color_code[1])


    def show_audio_devices(self):
        """Fetches and displays a list of available audio playback devices."""
        try:
            device_names = list_audio_devices()
            if not device_names:
                messagebox.showwarning("No Devices Found", "Could not find any audio playback devices.", parent=self)
                return

            message = "Found the following audio devices:\n\n- " + "\n- ".join(device_names)
            messagebox.showinfo("Available Audio Devices", message, parent=self)
        except Exception as e:
            messagebox.showerror("Error", f"Could not list audio devices: {e}", parent=self)
    

    def _on_toggle_hold_action(self):
        """Shows or hides the hold action configuration widgets."""
        if self.hold_action_enabled_var.get():
            self.hold_options_frame.grid()
        else:
            self.hold_options_frame.grid_remove()


    def choose_color(self):
        initial_color = self.font_color_var.get()
        color_code = colorchooser.askcolor(title="Choose Font Color", initialcolor=initial_color)
        if color_code and color_code[1]:
            self.font_color_var.set(color_code[1])


    def _on_display_type_change(self, event=None):
        if self.display_type_var.get() == "Dynamic Data":
            self.dynamic_options_frame.grid()
        else:
            self.dynamic_options_frame.grid_remove()


    def record_macro(self):
        """Opens the macro recorder and appends the recorded actions."""
        from ui_macro_recorder import MacroRecorderWindow

        recorder_dialog = MacroRecorderWindow(self)
        self.wait_window(recorder_dialog) # This pauses execution until the recorder is closed

        if recorder_dialog.recorded_actions:
            self.multi_action_list.extend(recorder_dialog.recorded_actions)
            self._refresh_tree()


    def create_payload_widgets(self, parent):
        # Frame for single-line or simple text payloads
        self.payload_frame_single = ttk.Frame(parent)
        ttk.Label(self.payload_frame_single, text="Payload (JSON or plain text):").pack(side="top", anchor="w")
        self.payload_txt = tk.Text(self.payload_frame_single, height=8, wrap="word")
        self.payload_txt.pack(fill="both", expand=True, padx=2, pady=(4, 2))
        
        # Aattach tooltip to the main payload widget.
        self.payload_tooltip = ToolTip(self.payload_txt, text="", bootstyle="info", delay=500)
        
        payload_val = self.current_config.get("payload", "")

        if isinstance(payload_val, (list, dict)):
            try: self.payload_txt.insert("1.0", json.dumps(payload_val, indent=2, ensure_ascii=False))
            except Exception: self.payload_txt.insert("1.0", str(payload_val))
        else: self.payload_txt.insert("1.0", str(payload_val or ""))
        
        # Frame for Multi-Action and Sequence payloads
        self.payload_frame_multi = ttk.Frame(parent)
        ttk.Label(self.payload_frame_multi, text="Actions Sequence (Double-click to edit):").pack(side="top", anchor="w")
        tree_area = ttk.Frame(self.payload_frame_multi)
        tree_area.pack(fill="both", expand=True, pady=6)
        tree_area.rowconfigure(0, weight=1)
        tree_area.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(tree_area, columns=("type", "payload"), show="headings", height=8)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(tree_area, orient="vertical", command=self.tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.heading("type", text="Action Type")
        self.tree.heading("payload", text="Payload")
        self.tree.column("type", width=120, stretch=False)
        self.tree.column("payload", width=300, stretch=True)

        ctrl_frame = ttk.Frame(self.payload_frame_multi)
        ctrl_frame.pack(side="top", fill="x", pady=(4,0))
        ttk.Button(ctrl_frame, text="Add Action", command=self.add_sub_action).pack(side="left", padx=2)
        ttk.Button(ctrl_frame, text="Record Macro", command=self.record_macro, style="primary.TButton").pack(side="left", padx=2)
        ttk.Button(ctrl_frame, text="Delete Action", command=self.delete_sub_action).pack(side="left", padx=2)
        ttk.Button(ctrl_frame, text="Move Up", command=lambda: self._move_action(-1)).pack(side="right", padx=2)
        ttk.Button(ctrl_frame, text="Move Down", command=lambda: self._move_action(1)).pack(side="right", padx=2)

        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self._refresh_tree()
        
        # Frame for Layer action (with secondary action)
        self.payload_frame_layer = ttk.Frame(parent)
        self.payload_frame_layer.columnconfigure(1, weight=1)

        # Primary Target Layer
        ttk.Label(self.payload_frame_layer, text="Target Layer:").grid(row=0, column=0, sticky="w", pady=(0,4))
        layer_select_frame = ttk.Frame(self.payload_frame_layer)
        layer_select_frame.grid(row=0, column=1, sticky="ew", pady=(0,10))
        self.layer_payload_var = tk.StringVar()
        self.layer_combobox = ttk.Combobox(layer_select_frame, textvariable=self.layer_payload_var, state="readonly")
        self.layer_combobox.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ttk.Button(layer_select_frame, text="Create New Layer", command=self._create_new_layer).pack(side="left")

        # Secondary Action
        ttk.Separator(self.payload_frame_layer, orient="horizontal").grid(row=1, column=0, columnspan=2, sticky="ew", pady=5)
        
        enable_second_cb = ttk.Checkbutton(
            self.payload_frame_layer,
            text="Add Secondary Action",
            variable=self.second_action_enabled_var,
            command=self._toggle_sec_action_widgets
        )
        enable_second_cb.grid(row=2, column=0, columnspan=2, sticky="w", pady=5)
        
        self.second_action_frame = ttk.Frame(self.payload_frame_layer)
        self.second_action_frame.grid(row=3, column=0, columnspan=2, sticky="nsew")
        self.second_action_frame.columnconfigure(1, weight=1)

        ttk.Label(self.second_action_frame, text="Action Type:").grid(row=0, column=0, sticky="w", pady=4)
        second_action_combo = ttk.Combobox(
            self.second_action_frame,
            textvariable=self.second_action_type_var,
            values=self.simple_actions,
            state="readonly"
        )
        second_action_combo.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        ttk.Label(self.second_action_frame, text="Payload:").grid(row=1, column=0, sticky="nw", pady=4)
        self.second_payload_txt = tk.Text(self.second_action_frame, height=4, wrap="word", relief="solid", bd=1)
        self.second_payload_txt.grid(row=1, column=1, sticky="ew", padx=(6, 0))
        self.second_payload_txt.configure(bg="#222222", fg="white", insertbackground="white")
        self.second_payload_tooltip = ToolTip(self.second_payload_txt, text="", bootstyle="info", delay=500)

        # Frame for window management payloads
        self.payload_frame_window = ttk.Frame(parent)
        self.payload_frame_window.columnconfigure(1, weight=1)
        
        ttk.Label(self.payload_frame_window, text="Command:").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.window_cmd_var = tk.StringVar()

        self.window_commands = ["focus", "move_to_next_monitor", "snap_left", "snap_right", "toggle_snap_left_right", "minimize_others"]
        self.window_combobox = ttk.Combobox(self.payload_frame_window, textvariable=self.window_cmd_var, values=self.window_commands, state="readonly")
        self.window_combobox.grid(row=0, column=1, sticky="ew")

        ttk.Label(self.payload_frame_window, text="Window Title (contains):").grid(row=1, column=0, sticky="w")
        self.window_title_var = tk.StringVar()
        window_title_entry = ttk.Entry(self.payload_frame_window, textvariable=self.window_title_var)
        window_title_entry.grid(row=1, column=1, sticky="ew", pady=(4,0))
        ToolTip(window_title_entry, text=PAYLOAD_TOOLTIPS.get("window_title", ""), bootstyle="info", delay=500)
    
        ttk.Label(self.payload_frame_window, text="Monitor Number (Optional):").grid(row=2, column=0, sticky="w", pady=(4,0))
        self.window_monitor_var = tk.StringVar()
        monitor_entry = ttk.Entry(self.payload_frame_window, textvariable=self.window_monitor_var)
        monitor_entry.grid(row=2, column=1, sticky="ew", pady=(4,0))
        ToolTip(monitor_entry, text="Enter a number (e.g., 1 or 2) to snap the window to a specific monitor.", bootstyle="info", delay=500)

        # Frame to display when no payload is needed
        self.payload_frame_none = ttk.Frame(parent)
        no_payload_label = ttk.Label(
            self.payload_frame_none,
            text="No payload parameter available for this action.",
            font="Arial 10 italic",
            bootstyle="secondary"
        )
        no_payload_label.pack(pady=20, padx=10)


    def _toggle_sec_action_widgets(self):
        if self.second_action_enabled_var.get():
            self.second_action_frame.grid()
        else:
            self.second_action_frame.grid_remove()


    def _refresh_tree(self):
        selection = self.tree.selection()
        for i in self.tree.get_children(): 
            self.tree.delete(i)

        for i, act in enumerate(self.multi_action_list):
            payload = act.get("payload", "")
            if isinstance(payload, (list, dict)):
                try: 
                    payload_str = json.dumps(payload, ensure_ascii=False)
                except: 
                    payload_str = str(payload)
            else: 
                payload_str = str(payload)

            self.tree.insert("", "end", iid=str(i), values=(act.get("action_type", ""), payload_str))
        if selection: 
            self.tree.selection_set(selection)


    def _on_tree_double_click(self, event):
        if self._edit_widget: 
            self._cancel_edit()

        item_id = self.tree.identify_row(event.y)
        column_id = self.tree.identify_column(event.x)
        if not item_id or not column_id: 
            return
        
        col_index = int(column_id.replace("#", "")) - 1
        row_index = int(item_id)

        if col_index == 0:  # Column is Action Type, use inline editor
            self.after(50, lambda: self._create_editor_at_event(event))
        
        elif col_index == 1:  # Column is Payload, use pop-up editor
            action_type = self.multi_action_list[row_index].get("action_type")
            current_payload = self.multi_action_list[row_index].get("payload")
            all_layers = sorted(list(self.parent_app.config_dta.keys()))

            dialog = SubActionEditor(self, action_type, current_payload, all_layers, self.window_commands)
            self.wait_window(dialog)

            if dialog.new_payload is not None:
                self.multi_action_list[row_index]["payload"] = dialog.new_payload
                self._refresh_tree()


    def _create_editor_at_event(self, event):
        item_id = self.tree.identify_row(event.y)
        column_id = self.tree.identify_column(event.x)
        if not item_id or not column_id: 
            return
        
        bbox = self.tree.bbox(item_id, column_id)
        if not bbox: 
            return
        
        x, y, w, h = bbox
        col_index = int(column_id.replace("#", "")) - 1
        value = self.tree.item(item_id, "values")[col_index]
        if self._edit_widget: 
            self._edit_widget.destroy()
            self._edit_widget = None

        if col_index == 0:
            edit_w = max(w, 180)
            edit_h = max(h, 30)
            self._edit_widget = ttk.Combobox(self.tree, values=self.sub_action_types, state="readonly", font=("Arial", 10))
            self._edit_widget.set(value)
            self._edit_widget.place(x=x, y=y, width=edit_w, height=edit_h)
            self._edit_widget.focus_set()
            self._edit_widget.bind("<FocusOut>", lambda e: self._save_edit(item_id, col_index))
            self._edit_widget.bind("<Return>", lambda e: self._save_edit(item_id, col_index))
            self._edit_widget.bind("<KP_Enter>", lambda e: self._save_edit(item_id, col_index))
            self._edit_widget.bind("<Escape>", self._cancel_edit)


    def _save_edit(self, item_id, col_index):
        if not self._edit_widget: 
            return
        
        editor = self._edit_widget
        self._edit_widget = None

        if isinstance(editor, ttk.Combobox): 
            new_value = editor.get()
        else: 
            new_value = editor.get("1.0", "end-1c").strip()

        editor.destroy()
        row_index = int(item_id)
        
        if col_index == 0:
            self.multi_action_list[row_index]["action_type"] = new_value
        else:
            try: 
                new_payload = json.loads(new_value) if new_value else ""
            except (json.JSONDecodeError, TypeError): 
                new_payload = new_value

            self.multi_action_list[row_index]["payload"] = new_payload
        self._refresh_tree()


    def _cancel_edit(self, event=None):
        if self._edit_widget: 
            self._edit_widget.destroy()
            self._edit_widget = None


    def browse_for_icon(self):
        filename = filedialog.askopenfilename(title="Select Icon", filetypes=[("Image Files","*.png;*.jpg;*.gif;*.bmp"),("All","*.*")])
        if filename:
            os.makedirs(ICON_FOLDER, exist_ok=True)
            basename = os.path.basename(filename)
            dest = os.path.join(ICON_FOLDER, basename)
            try:
                if os.path.abspath(filename) != os.path.abspath(dest):
                    if not os.path.exists(dest): 
                        shutil.copy2(filename, dest)
                self.icon_var.set(basename)
            except Exception as e: 
                messagebox.showerror("Error", f"Could not copy icon file: {e}")


    def on_second_action_type_change(self, *args):
        """Updates the tooltip for the secondary action's payload field."""
        if not self.second_payload_tooltip:
            return
        
        action_type = self.second_action_type_var.get()
        tooltip_text = PAYLOAD_TOOLTIPS.get(action_type, "")
        self.second_payload_tooltip.text = tooltip_text


    def on_action_type_change(self):
        if hasattr(self, 'audio_device_button'):
            self.audio_device_button.destroy()

        for widget in (self.payload_frame_single, self.payload_frame_multi, self.payload_frame_layer, self.payload_frame_window):
            widget.pack_forget()

        action_type = self.action_type_var.get()

        if self.payload_tooltip:
            tooltip_text = PAYLOAD_TOOLTIPS.get(action_type, "No payload parameter available for this action")
            self.payload_tooltip.text = tooltip_text

        # Define actions that do not require any payload input
        no_payload_actions = ["back", "exit", "media_play_pause", "media_next", "media_previous", 
                                "media_stop", "toggle_mute", "clipboard_history", "back_to_main"]

        if action_type in no_payload_actions:
            # For these actions, no payload frame is shown.
            pass
        elif action_type == "http_request":
            current_payload = self.payload_txt.get("1.0", "end-1c").strip()
            if not current_payload or current_payload in ['""', '{}']:
                default_payload_dta = {
                    "method": "POST",
                    "url": "https://example.com/trigger/EVENT/KEY",
                    "json": {
                        "value1": "",
                        "value2": "",
                        "value3": ""
                    },
                    "headers": {
                        "Content-Type": "application/json"
                    }
                }
                example_json = json.dumps(default_payload_dta, indent=2)
                self.payload_txt.delete("1.0", "end")
                self.payload_txt.insert("1.0", example_json)

        elif action_type == "toggle_state":
            current_payload = self.payload_txt.get("1.0", "end-1c").strip()

            if not current_payload or current_payload in ['""', '[]']:
                default_payload_dta = [
                  {
                    "label": "Mute Mic",
                    "icon": "mic-on.png",
                    "action": {
                      "action_type": "hotkey",
                      "payload": "ctrl+shift+m"
                    }
                  },
                  {
                    "label": "Unmute",
                    "icon": "mic-off.png",
                    "font_color": "#ff6666",
                    "action": {
                      "action_type": "hotkey",
                      "payload": "ctrl+shift+m"
                    }
                  }
                ]

                # Set the main icon to the icon from the first state of the toggle.
                self.icon_var.set(default_payload_dta[0]["icon"])

                example_json = json.dumps(default_payload_dta, indent=2)

                # insert the example string
                self.payload_txt.delete("1.0", "end")
                self.payload_txt.insert("1.0", example_json)

        if action_type in ["multi-action", "sequence"]:
            if action_type == "sequence":
                self.payload_frame_multi.children['!label'].config(text="Sequential Actions (Executed one per press):")
            else:
                self.payload_frame_multi.children['!label'].config(text="Actions Sequence (Double-click to edit):")
            self.payload_frame_multi.pack(fill="both", expand=True)

        elif action_type in ["layer", "jump_to_layer"]:
            self.payload_frame_layer.pack(fill="both", expand=True)
            layers = sorted([k for k in self.parent_app.config_dta.keys() if k not in ["settings", "context_aware_profiles"]])
            self.layer_combobox['values'] = layers
            
            payload = self.current_config.get("payload", "")

            if isinstance(payload, dict):
                self.layer_payload_var.set(payload.get("target", ""))
                sec_action = payload.get("secondary_action", {})
                if sec_action:
                    self.second_action_enabled_var.set(True)
                    self.second_action_type_var.set(sec_action.get("action_type", ""))
                    self.second_payload_txt.delete("1.0", "end")
                    self.second_payload_txt.insert("1.0", str(sec_action.get("payload", "")))
                else:
                    self.second_action_enabled_var.set(False)
            else:
                self.layer_payload_var.set(payload)
                self.second_action_enabled_var.set(False)

            self._toggle_sec_action_widgets()

        elif action_type == "window_management":
            self.payload_frame_window.pack(fill="both", expand=True, anchor="n", pady=5)
            payload = self.current_config.get("payload", "")
            
            # Handle both old (string) and (dict) payload formats
            if isinstance(payload, dict):
                command = payload.get("command", "")
                title = payload.get("window_title", "")
                monitor = payload.get("monitor", "") # Get the monitor number
            else:
                command = payload
                title = ""
                monitor = ""

            if command in self.window_commands:
                self.window_cmd_var.set(command)
            else:
                self.window_cmd_var.set("")
            self.window_title_var.set(title)
            self.window_monitor_var.set(monitor)
        else:
            self.payload_frame_single.pack(fill="both", expand=True)

            if action_type == "set_audio_device":
                self.audio_device_button = ttk.Button(self.payload_frame_single, text="List Audio Devices", command=self.show_audio_devices)
                self.audio_device_button.pack(side="bottom", fill="x", pady=(5,0), padx=2)

            elif action_type == "toggle_state":
                current_payload = self.payload_txt.get("1.0", "end-1c").strip()
                if not current_payload or current_payload in ['""', '[]']:
                    default_payload_dta = [
                      {
                        "label": "Mute Mic",
                        "icon": "mic-on.png",
                        "action": {
                          "action_type": "hotkey",
                          "payload": "ctrl+shift+m"
                        }
                      },
                      {
                        "label": "Unmute",
                        "icon": "mic-off.png",
                        "font_color": "#ff6666",
                        "action": {
                          "action_type": "hotkey",
                          "payload": "ctrl+shift+m"
                        }
                      }
                    ]
                    self.icon_var.set(default_payload_dta[0]["icon"])
                    example_json = json.dumps(default_payload_dta, indent=2)

                    self.payload_txt.delete("1.0", "end")
                    self.payload_txt.insert("1.0", example_json)


    def _create_new_layer(self):
        """Prompts the user for a new layer name and creates it, ensuring it's unique."""

        # Name for the new layer
        desired_name = simpledialog.askstring(
            "Create New Layer",
            "Enter a name for the new layer (leave blank for default):",
            parent=self
        )

        # Use provided name. Otherwise, use the default naming.
        if desired_name and desired_name.strip():
            base_name = desired_name.strip()
        else:
            base_name = f"{self.current_layer}-{self.key_index}-layer"
        
        # Aappending number if not unique.
        new_name = generate_layer_name(self.parent_app.config_dta, base_name)

        # Add the new layer to the active decks configuration data.
        self.parent_app.config_dta[new_name] = {"parent": self.current_layer}
        self.parent_app.log.info(f"Created new layer: '{new_name}' with parent '{self.current_layer}'")

        save_config(self.parent_app.full_config_dta)

        # Refresh the layer sidebar
        self.parent_app._populate_layers_tree()

        # Get list of layers (excluding settings keys) for the dropdown.
        layers = sorted([
            k for k in self.parent_app.config_dta.keys() 
            if k not in ["settings", "context_aware_profiles"]
        ])
        
        # Update combobox and set the new layer as the current selection.
        self.layer_combobox['values'] = layers
        self.layer_payload_var.set(new_name)


    def add_sub_action(self):
        self.multi_action_list.append({"action_type": "execute", "payload": ""})
        self._refresh_tree()
        last_item_id = str(len(self.multi_action_list) - 1)
        self.tree.selection_set(last_item_id)
        self.tree.see(last_item_id)


    def delete_sub_action(self):
        selected_ids = self.tree.selection()
        if not selected_ids:
            return

        index_to_delete = int(selected_ids[0])
        self.tree.selection_set(())

        del self.multi_action_list[index_to_delete]
        self._refresh_tree()

        # get next item
        new_selection_index = min(index_to_delete, len(self.multi_action_list) - 1)

        # if  list is not empty, select the new item
        if new_selection_index >= 0:
            new_item_id = str(new_selection_index)
            self.tree.selection_set(new_item_id)
            self.tree.see(new_item_id) # Scroll to the new selection


    def _move_action(self, direction):
        selected = self.tree.selection()
        if not selected: 
            return
        index = int(selected[0])
        new_index = index + direction
        if 0 <= new_index < len(self.multi_action_list):
            item = self.multi_action_list.pop(index)
            self.multi_action_list.insert(new_index, item)
            self._refresh_tree()
            new_item_id = str(new_index)
            self.tree.selection_set(new_item_id)
            self.tree.focus(new_item_id)


    def save_changes(self):
        if self._edit_widget: 
            self.focus_set()

        new_config = {
            "label": self.label_widget.get("1.0", "end-1c").strip(),
            "icon": self.icon_var.get().strip(),
            "action_type": self.action_type_var.get(),
            "label_pos": self.label_pos_var.get().lower(),
            "font_color": self.font_color_var.get().strip()
        }

        bg_color = self.background_color_var.get().strip()
        if bg_color:
            new_config["background"] = bg_color

        if self.hold_action_enabled_var.get():
            hold_payload_txt = self.hold_payload_txt.get("1.0", "end-1c").strip()
            new_config["hold_action"] = {
                "action_type": self.hold_action_type_var.get(),
                "payload": hold_payload_txt
            }
        else:
            # Ensure the key is not present if the action is disabled
            new_config.pop("hold_action", None)

        font_family = self.font_family_var.get().strip()
        font_size_str = self.font_size_var.get().strip()
        font_settings = {}

        if font_family:
            font_settings["family"] = font_family

        if font_size_str:
            try:
                font_settings["size"] = int(font_size_str)
            except ValueError:
                messagebox.showwarning("Warning", "Font size must be a whole number.")
                return

        if font_settings:
            new_config["font_settings"] = font_settings

        action_type = new_config["action_type"]
        payload = ""

        if action_type in ["multi-action", "sequence"]:
            payload = self.multi_action_list

        elif action_type in ["layer", "jump_to_layer"]:
            target = self.layer_payload_var.get()
            if not target:
                messagebox.showwarning("Warning", "No target layer selected.")
                return

            if action_type == "layer" and self.second_action_enabled_var.get():
                sec_type = self.second_action_type_var.get()
                sec_payload_raw = self.second_payload_txt.get("1.0", "end-1c").strip()
                
                try:
                    sec_payload = json.loads(sec_payload_raw) if sec_payload_raw else ""
                except json.JSONDecodeError:
                    sec_payload = sec_payload_raw
                
                if not sec_type:
                    messagebox.showwarning("Warning", "No secondary action type selected.")
                    return
                
                payload = {
                    "target": target,
                    "secondary_action": {
                        "action_type": sec_type,
                        "payload": sec_payload
                    }
                }
            else:
                payload = target
        elif action_type == "window_management":
            command = self.window_cmd_var.get()
            title = self.window_title_var.get().strip()
            monitor_str = self.window_monitor_var.get().strip()
            if not command:
                messagebox.showwarning("Warning", "No window command selected.")
                return

            # Build a dictionary payload if title or monitor are provided.
            if not title and not monitor_str:
                payload = command
            else:
                payload = {"command": command}
                if title:
                    payload["window_title"] = title
                if monitor_str:
                    try:
                        payload["monitor"] = int(monitor_str)
                    except ValueError:
                        messagebox.showerror("Invalid Input", "Monitor number must be a whole number (e.g., 1, 2).", parent=self)
                        return
        else:
            payload_txt = self.payload_txt.get("1.0", "end-1c").strip()
            try:
                payload = json.loads(payload_txt) if payload_txt else ""
            except json.JSONDecodeError:
                payload = payload_txt

        new_config["payload"] = payload

        display_dict = {}
        display_type = self.display_type_var.get()

        if display_type == "Animated GIF":
            display_dict = {"type": "animated"}

        elif display_type == "Dynamic Data":
            provider = self.provider_var.get()
            interval = self.interval_var.get()

            if not provider:
                messagebox.showwarning("Warning", "No data provider selected.")
                return
            display_dict = {"type": "dynamic", "provider": provider}

            if interval:
                try: 
                    display_dict["update_interval"] = float(interval)
                except ValueError:
                    messagebox.showwarning("Warning", "Update interval must be a number.")
                    return

            options_str = self.provider_options_var.get().strip()
            if options_str:
                try:
                    # Parse simple key=value pairs separated by commas
                    options_dict = dict(item.strip().split("=", 1) for item in options_str.split(",") if "=" in item)
                    display_dict["provider_options"] = options_dict
                except ValueError:
                    messagebox.showwarning("Warning", "Provider Options format is invalid. Use key=value, another=value2.")
                    return
                
        if display_dict:
            new_config["display"] = display_dict
        
        self.on_save_callback(self.current_layer, self.key_index, new_config)
        self.destroy()


class SubActionEditor(tk.Toplevel):
    """A dynamic pop-up dialog for editing a sub-action's payload."""
    def __init__(self, parent, action_type, current_payload, all_layers, window_commands):
        super().__init__(parent)
        self.action_type = action_type
        self.new_payload = None 

        self.transient(parent)
        self.grab_set()
        self.title(f"Edit Payload ({action_type})")
        self.minsize(400, 350)

        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(fill="both", expand=True)

        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill="both", expand=True)

        # Example payload for toggle_state if empty
        if self.action_type == "toggle_state":
            is_empty = not current_payload or current_payload == []
            if is_empty:
                current_payload = [
                  {
                    "label": "Mute Mic",
                    "icon": "mic-on.png",
                    "action": {
                      "action_type": "hotkey",
                      "payload": "ctrl+shift+m"
                    }
                  },
                  {
                    "label": "Unmute",
                    "icon": "mic-off.png",
                    "font_color": "#ff6666",
                    "action": {
                      "action_type": "hotkey",
                      "payload": "ctrl+shift+m"
                    }
                  }
                ]

        # Create dynamic widgets based on action_type
        if self.action_type == "layer":
            ttk.Label(content_frame, text="Target Layer:").pack(anchor="w", pady=(0, 5))
            self.layer_payload_var = tk.StringVar(value=current_payload)
            self.widget = ttk.Combobox(content_frame, textvariable=self.layer_payload_var, values=all_layers, state="readonly")
            self.widget.pack(fill="x", expand=True)

        elif self.action_type == "window_management":
            content_frame.columnconfigure(1, weight=1)
            ttk.Label(content_frame, text="Command:").grid(row=0, column=0, sticky="w", pady=(0, 6))
            self.window_cmd_var = tk.StringVar()
            self.widget = ttk.Combobox(content_frame, textvariable=self.window_cmd_var, values=window_commands, state="readonly")
            self.widget.grid(row=0, column=1, sticky="ew")

            ttk.Label(content_frame, text="Window Title (contains):").grid(row=1, column=0, sticky="w")
            self.window_title_var = tk.StringVar()
            self.title_widget = ttk.Entry(content_frame, textvariable=self.window_title_var)
            self.title_widget.grid(row=1, column=1, sticky="ew", pady=(4,0))
            
            if isinstance(current_payload, dict):
                self.window_cmd_var.set(current_payload.get("command", ""))
                self.window_title_var.set(current_payload.get("window_title", ""))
            else:
                self.window_cmd_var.set(current_payload)

        else: # Default for write, execute, hotkey, and a pre-filled toggle_state
            ttk.Label(content_frame, text="Payload (JSON or plain text):").pack(anchor="w", pady=(0, 5))
            self.widget = tk.Text(content_frame, height=6, width=40, wrap="word")
            self.widget.pack(fill="both", expand=True)
            if isinstance(current_payload, (list, dict)):
                self.widget.insert("1.0", json.dumps(current_payload, indent=2))
            else:
                self.widget.insert("1.0", str(current_payload or ""))
            self.widget.focus_set()

        # OK and Cancel Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(side="bottom", fill="x", pady=(15, 0))
        ttk.Button(btn_frame, text="OK", command=self.ok, style="Accent.TButton").pack(side="right")
        ttk.Button(btn_frame, text="Cancel", command=self.cancel).pack(side="right", padx=6)


    def ok(self):
        if self.action_type == "layer":
            self.new_payload = self.layer_payload_var.get()
        elif self.action_type == "window_management":
            cmd = self.window_cmd_var.get()
            title = self.window_title_var.get().strip()
            self.new_payload = {"command": cmd, "window_title": title} if title else cmd
        else:
            payload_txt = self.widget.get("1.0", "end-1c").strip()
            try:
                self.new_payload = json.loads(payload_txt) if payload_txt else ""
            except json.JSONDecodeError:
                self.new_payload = payload_txt
        
        self.destroy()

    def cancel(self):
        self.new_payload = None
        self.destroy()