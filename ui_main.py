# VERSION 3.0.0
# Tobias Wagner - GitHub twgnr
# Tested and compiled with Python 3.13.7
#--------------------------------------------------------------------
# Import packages
#--------------------------------------------------------------------
import os
import sys
import subprocess
import shutil
import threading
import time
import argparse
import tkinter as tk
import ttkbootstrap as tb
import pystray
import copy
import matplotlib.font_manager as fm
# try:
#     import pyperclip
# except ImportError as e:
#     print(f'PYClip Error: {e}')
#     pass
#--------------------------------------------------------------------
# Import sub-packages
#--------------------------------------------------------------------
from tkinter import messagebox, simpledialog
from ttkbootstrap import ttk
from ttkbootstrap.dialogs import Messagebox
from PIL import Image, ImageTk, ImageDraw, ImageFont
from tkinterdnd2 import TkinterDnD, DND_FILES, DND_ALL, COPY, DND_TEXT
from pystray import MenuItem as item
from StreamDeck.DeviceManager import DeviceManager

#--------------------------------------------------------------------
# Import local modules
#--------------------------------------------------------------------
from deck_driver import DeckDriver
from profile_monitor import profile_monitor_loop, CONTEXT_AWARE_ENABLED
from hot_reloader import start_reloader
from dynamic_keys import start_dynamic_key_updater, UI_DATA_CACHE
from config_manager import load_config, save_config, setup_logging, generate_layer_name, ICON_FOLDER, BASEPATH, FONT_PATH, app_settings, log
from ui_key_editor import KeyConfigWindow
from rendering import draw_active_border
from action_handler import UI_CMD_QUEUE
from ui_cycle_window import CycleWindow


class EditLayerDialog(tk.Toplevel):
    def __init__(self, parent, current_name, current_app):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Edit Layer")

        self.new_name = tk.StringVar(value=current_name)
        self.new_app = tk.StringVar(value=current_app)
        self.result = None

        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill="both", expand=True)

        ttk.Label(main_frame, text="Layer Name:").grid(row=0, column=0, sticky="w", pady=(0, 5))
        ttk.Entry(main_frame, textvariable=self.new_name).grid(row=1, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(main_frame, text="Associated Application (Optional, e.g., Teams.exe):").grid(row=2, column=0, sticky="w", pady=(0, 5))
        ttk.Entry(main_frame, textvariable=self.new_app).grid(row=3, column=0, sticky="ew", pady=(0, 15))
        
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, sticky="e")
        ttk.Button(button_frame, text="Save", command=self.save).pack(side="right", padx=(5,0))
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side="right")
        
        main_frame.columnconfigure(0, weight=1)


    def save(self):
        self.result = (self.new_name.get().strip(), self.new_app.get().strip())
        self.destroy()


class StreamDeckConfigurator(tb.Window, TkinterDnD.Tk):
    def __init__(self, start_driver=True):
        super().__init__(themename="darkly")
        self.title("Stream Deck Tool")
        self.minsize(800, 500)
        self.log = log

        streamdecks = DeviceManager().enumerate()
        if streamdecks:
            key_count = streamdecks[0].key_count()
            if key_count == 32:
                self.rows, self.cols = 4, 8
                self.geometry("1350x560")
            elif key_count == 15:
                self.rows, self.cols = 3, 5
                self.geometry("1060x500")
            else:
                self.rows, self.cols = 2, 3
                self.geometry("800x400")
        else:
            self.log.warning("No Stream Deck found on startup. Using default 4x8 layout.")
            self.rows, self.cols = 4, 8
            self.geometry("1350x560")
        
        self.keys = self.rows * self.cols

        self.shutdown_event = threading.Event()
        self.drivers = {}
        # Shared, mutable driver list: background services iterate this list live,
        # so decks added/removed at runtime are picked up without a restart.
        self.all_drivers_list = []
        self.active_deck_id = None
        self.reloader_observer = None
        self._profile_monitor_started = False
        self._dynamic_updater_started = False
        
        self.full_config_dta = load_config()
        setup_logging(self.full_config_dta)
        self.config_dta = {}

        self.current_layer = "main"
        self.layer_history = []
        self.key_buttons = {}
        self.blank_image = tk.PhotoImage(width=1, height=1)

        self._dnd_source_key = None
        self._style_clipboard = None
        self._key_clipboard = None
        self._click_timer = None
        self.logging_enabled_var = tk.BooleanVar() # for the menue checkbox to write logs to file
        self.context_profile_enabled_var = tk.BooleanVar()
        self.last_clipboard_content = ""

        self.create_menu()
        
        paned_window = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        sidebar_frame = ttk.Frame(paned_window, padding=5)
        self.main_content_frame = ttk.Frame(paned_window, padding=5)
        
        paned_window.add(sidebar_frame, weight=1)
        paned_window.add(self.main_content_frame, weight=4)

        self.main_content_frame.rowconfigure(1, weight=1)
        self.main_content_frame.columnconfigure(0, weight=1)

        self.create_sidebar(sidebar_frame)
        self.create_header(self.main_content_frame)
        self.create_key_grid(self.main_content_frame)

        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Copy Style", command=self.copy_key_style)
        self.context_menu.add_command(label="Paste Style", command=self.paste_key_style)
        self.context_menu.add_command(label="Copy Key", command=self.copy_key_full)
        self.context_menu.add_command(label="Paste Key", command=self.paste_key_full)
        self.context_menu.add_separator()
        self.apply_template_menu = tk.Menu(self.context_menu, tearoff=0)
        self.context_menu.add_cascade(label="Apply Template", menu=self.apply_template_menu)
        self.context_menu.add_command(label="Save as Template...", command=self.save_key_as_template)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Delete Key", command=self.delete_context_key)

        self.context_menu.add_separator()
        self.context_menu.add_command(label="Edit Key...", command=self.edit_context_key)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Delete Key", command=self.delete_context_key)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Execute", command=self.execute_context_action)

        self._context_key_index = None

        self.key_pixel_size = app_settings.DEFAULT_KEY_SIZE
        self.resize_job = None
        self.bind("<Configure>", self.on_root_config)
        
        self.enable_drag_and_drop()
        self.protocol('WM_DELETE_WINDOW', self.hide_window)
        self.setup_tray_icon()

        self.cycle_window = None

        if start_driver:
            threading.Thread(target=self.start_deck_driver, daemon=True).start()
            self.after(250, self.check_shutdown_event)
            self.after(1000, self.update_dynamic_previews)
            self.after(100, self.process_ui_queue)
            #self.after(500, self.poll_clipboard)
        else:
            self.log.warning("Running in UI-only mode. Stream Deck driver is not active.")
            self.active_deck_id = "default_ui"
            self.config_dta = self.full_config_dta.setdefault(self.active_deck_id, {"main": {}})
            self._populate_layers_tree()
            self.draw_layer("main", nav_type="initial")


    @property
    def active_driver(self):
        if self.active_deck_id:
            return self.drivers.get(self.active_deck_id)
        return None
    

    def create_sidebar(self, parent):
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        
        sidebar_labelframe = ttk.LabelFrame(parent, text="Layers")
        sidebar_labelframe.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        sidebar_labelframe.rowconfigure(0, weight=1)
        sidebar_labelframe.columnconfigure(0, weight=1)

        self.layers_tree = ttk.Treeview(sidebar_labelframe, columns=("layer", "app"), show="headings")
        self.layers_tree.heading("layer", text="Layer Name")
        self.layers_tree.heading("app", text="Application")
        self.layers_tree.column("layer", width=120)
        self.layers_tree.column("app", width=120)
        self.layers_tree.grid(row=0, column=0, sticky="nsew")
        self.layers_tree.bind("<<TreeviewSelect>>", self._on_layer_select)

        button_frame = ttk.Frame(parent)
        button_frame.grid(row=1, column=0, sticky="ew")
        
        add_btn = ttk.Button(button_frame, text="Add", command=self._add_layer)
        add_btn.pack(side="left", fill="x", expand=True, padx=(0, 2))
        
        edit_btn = ttk.Button(button_frame, text="Edit", command=self._edit_layer)
        edit_btn.pack(side="left", fill="x", expand=True, padx=2)
        
        del_btn = ttk.Button(button_frame, text="Delete", command=self._delete_layer, style="danger.TButton")
        del_btn.pack(side="left", fill="x", expand=True, padx=(2, 0))


    def _populate_layers_tree(self):
        if self.layers_tree.selection():
            self.layers_tree.selection_remove(self.layers_tree.selection())

        for i in self.layers_tree.get_children():
            self.layers_tree.delete(i)
        
        profiles = self.config_dta.get("context_aware_profiles", {}).get("profiles", {})
        app_map = {v: k for k, v in profiles.items()}
        
        ignored_keys = ["settings", "context_aware_profiles"]
        layer_names = sorted([k for k in self.config_dta.keys() if k not in ignored_keys])

        for name in layer_names:
            app_name = app_map.get(name, "")
            self.layers_tree.insert("", "end", values=(name, app_name), iid=name)

        if self.current_layer in layer_names:
            self.layers_tree.selection_set(self.current_layer)


    def _on_layer_select(self, event):
        selected_items = self.layers_tree.selection()
        if not selected_items:
            return
        
        selected_layer = selected_items[0]
        if self.current_layer != selected_layer and self.active_driver:
            self.active_driver.jump_to_layer(selected_layer)


    def _add_layer(self):       
        desired_name = simpledialog.askstring(
            "Create New Layer", "Enter a name for the new layer:", parent=self)
        
        if not desired_name:
            return
        
        unique_name = generate_layer_name(self.config_dta, desired_name)
        
        if unique_name != desired_name:
            Messagebox.show_info(
                title="Name Adjusted",
                message=f"The name '{desired_name}' was already in use.\nYour layer has been created as '{unique_name}'.",
                parent=self)
        
        self.config_dta[unique_name] = {}
        save_config(self.full_config_dta)
        self._populate_layers_tree()
        self.draw_layer(unique_name, nav_type="jump")


    def _edit_layer(self):
        selected_items = self.layers_tree.selection()
        if not selected_items:
            Messagebox.show_info("Please select a layer to edit.", "No Layer Selected")
            return
        
        old_name = selected_items[0]
        current_app = self.layers_tree.item(old_name, "values")[1]

        dialog = EditLayerDialog(self, old_name, current_app)
        self.wait_window(dialog)
        
        if dialog.result:
            desired_name, new_app = dialog.result
            new_app = new_app.strip().lower() 

            if not desired_name:
                Messagebox.show_error("Layer name cannot be empty.", "Invalid Name")
                return

            profiles = self.config_dta.setdefault("context_aware_profiles", {}).setdefault("profiles", {})

            if new_app:
                currently_associated_layer = profiles.get(new_app)
                if currently_associated_layer and currently_associated_layer != old_name:
                    Messagebox.show_error(
                        title="Association Conflict",
                        message=f"The application '{new_app}' is already linked to the '{currently_associated_layer}' layer.\n\nEach application can only be linked to one layer.",
                        parent=self)
                    return

            unique_name = generate_layer_name(self.config_dta, desired_name, original_name=old_name)

            if unique_name != desired_name:
                Messagebox.show_info(
                    title="Name Adjusted",
                    message=f"The name '{desired_name}' was already in use.\nThe layer has been renamed to '{unique_name}'.",
                    parent=self)

            for app, layer in list(profiles.items()):
                if layer == old_name:
                    del profiles[app]
            
            if new_app:
                profiles[new_app] = unique_name
            
            if unique_name != old_name:
                self.config_dta[unique_name] = self.config_dta.pop(old_name)
            
            save_config(self.full_config_dta)
            self._populate_layers_tree()
            self.current_layer = unique_name
            self.draw_layer(self.current_layer, nav_type="jump")


    def _delete_layer(self):
        selected_items = self.layers_tree.selection()
        if not selected_items:
            Messagebox.show_info("Please select a layer to delete.", "No Layer Selected")
            return
        
        layer_to_delete = selected_items[0]
        if layer_to_delete == "main":
            Messagebox.show_error("The 'main' layer cannot be deleted.", "Cannot Delete Main Layer")
            return
        
        if not Messagebox.yesno(f"Are you sure you want to permanently delete the layer '{layer_to_delete}'?", "Confirm Deletion"):
            return
            
        del self.config_dta[layer_to_delete]
        
        profiles = self.config_dta.get("context_aware_profiles", {}).get("profiles", {})
        for app, layer in list(profiles.items()):
            if layer == layer_to_delete:
                del profiles[app]
        
        save_config(self.full_config_dta)
        self._populate_layers_tree()
        self.draw_layer("main", nav_type="jump")


    def quit(self):
        self.exit_app()


    def start_deck_driver(self):
        self.log.info("Attempting to start Stream Deck drivers...")
        streamdecks = DeviceManager().enumerate()

        if not streamdecks:
            self.log.warning("No Stream Decks found. Drivers not started.")
            self.active_deck_id = "default_ui"
            self.config_dta = self.full_config_dta.setdefault(self.active_deck_id, {"main": {}})
            self.deck_selector['values'] = ["No Device (Default)"]
            self.deck_selector.set("No Device (Default)")
            self._populate_layers_tree()
            self.draw_layer("main", nav_type="initial")
            self._start_device_watcher()
            return

        deck_names = []
        for deck in streamdecks:
            deck.open()
            deck.reset()
            
            deck_id = deck.id()
            deck_type = deck.deck_type()
            deck_name = f"{deck_type} ({deck_id})"
            deck_names.append(deck_name)
            
            self.log.info(f"Opened '{deck_type}' device ({deck_id}).")
            deck.set_brightness(30)
            
            # initiate driver with all callbacks
            driver = DeckDriver(
                deck,
                self.full_config_dta,
                self.shutdown_event,
                ui_refresh_callback=self.refresh_ui_from_config,
                layer_change_callback=self.on_driver_layer_change,
                ui_visual_refresh_callback=self.refresh_all_button_visuals
            )
            self.drivers[deck_id] = driver
            self.all_drivers_list.append(driver)

            deck.set_key_callback(driver.key_change_callback)
            driver.draw_layer("main")

        self.deck_selector['values'] = deck_names
        if deck_names:
            first_deck_id = streamdecks[0].id()
            self.active_deck_id = first_deck_id
            self.deck_selector.set(deck_names[0])
            self.on_deck_selected()

        self._ensure_background_services()

        self.log.info(f"Stream Deck drivers are running for {len(self.drivers)} device(s).")
        self._start_device_watcher()


    def _ensure_background_services(self):
        """Starts global background services once. They operate on the shared
        driver list, so decks connected later are served without a restart."""
        if not self.all_drivers_list:
            return

        if not self._profile_monitor_started:
            any_deck_has_context_aware = any(
                d.config.get("context_aware_profiles", {}).get("enabled", False) for d in self.all_drivers_list
            )
            if CONTEXT_AWARE_ENABLED and any_deck_has_context_aware:
                threading.Thread(target=profile_monitor_loop, args=(self.all_drivers_list, self.shutdown_event), daemon=True).start()
                self._profile_monitor_started = True
                self.log.info("Context-aware profile monitor started for all devices.")

        if self.reloader_observer is None:
            any_deck_has_hot_reload = any(
                d.config.get("settings", {}).get("hot_reload_enabled", False) for d in self.all_drivers_list
            )
            if any_deck_has_hot_reload:
                self.reloader_observer = start_reloader(self.all_drivers_list)

        if not self._dynamic_updater_started:
            start_dynamic_key_updater(self.all_drivers_list, self.shutdown_event)
            self._dynamic_updater_started = True


    def _start_device_watcher(self):
        """Starts the background thread that auto-detects unplugged/replugged decks."""
        threading.Thread(target=self._device_watcher_loop, daemon=True).start()


    def _device_watcher_loop(self):
        """Periodically checks device connectivity and schedules an automatic
        rescan on the UI thread when a deck is plugged in or unplugged."""
        self.log.info("Automatic device detection started.")
        while not self.shutdown_event.wait(3):
            try:
                change_detected = False

                # A stale handle means the deck was unplugged. This also catches a
                # replugged deck that re-enumerates under the same device ID.
                for driver in list(self.drivers.values()):
                    try:
                        if not driver.deck.connected():
                            change_detected = True
                            break
                    except Exception:
                        change_detected = True
                        break

                if not change_detected:
                    found_ids = {d.id() for d in DeviceManager().enumerate()}
                    if found_ids != set(self.drivers.keys()):
                        change_detected = True

                if change_detected:
                    self.log.info("Device change detected. Triggering automatic rescan.")
                    self.after(0, lambda: self.rescan_devices(silent=True))
                    # Give the rescan time to run before checking again
                    self.shutdown_event.wait(3)
            except Exception as e:
                self.log.error(f"Error in device watcher: {e}")
        self.log.info("Device watcher shutting down.")


    def on_driver_layer_change(self, deck_id, new_layer_name, new_layer_history):
        """Callback for a driver to report that its active layer has changed."""
        # Update the UI only if a change happened
        if deck_id == self.active_deck_id:
            # 0 for UI updates on the main thread
            self.after(0, self.sync_ui_to_driver_state, new_layer_name, new_layer_history)


    def sync_ui_to_driver_state(self, new_layer_name, new_layer_history):
        """Directly sets the UI's state to match the drivers and redraws everything."""
        self.log.info(f"Syncing UI to hardware state: Layer '{new_layer_name}'")
        self.current_layer = new_layer_name
        self.layer_history = new_layer_history

        self.layer_history = new_layer_history.copy()
        
        UI_DATA_CACHE.clear()

        self.update_breadcrumbs()
        if self.layer_history:
            self.back_button.grid()
        else:
            self.back_button.grid_remove()
        
        # Redraw all the key buttons for the new layer
        for i in range(self.keys):
            self.update_button_visuals(i)

        self._populate_layers_tree()


    def refresh_ui_from_config(self, new_full_config):
        self.log.info("Hot-reload detected by driver, refreshing UI...")
        self.full_config_dta = new_full_config
        self.config_dta = self.full_config_dta.get(self.active_deck_id, {"main": {}})
        self._populate_layers_tree()
        self.after(0, self.draw_layer, self.current_layer, "jump")


    def setup_tray_icon(self):
        icon_path = os.path.join(BASEPATH, "sde.png")
        if not os.path.exists(icon_path):
            self.log.error(f"App icon not found at '{icon_path}'. Tray icon will not work.")
            return
            
        image = Image.open(icon_path)
        menu = (item('Show', self.show_window, default=True), item('Exit', self.exit_app))
        self.tray_icon = pystray.Icon("StreamDeckConfigurator", image, "Stream Deck Tool", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()


    def hide_window(self):
        self.withdraw()


    def show_window(self, icon, item):
        self.deiconify()
        self.lift()


    def check_shutdown_event(self):
        if self.shutdown_event.is_set():
            self.exit_app()
        else:
            self.after(250, self.check_shutdown_event)


    def exit_app(self, icon=None, item=None):
        self.log.info("Exit requested. Shutting down...")
        self.shutdown_event.set()
        time.sleep(0.2)
        if hasattr(self, 'reloader_observer') and self.reloader_observer and self.reloader_observer.is_alive():
            self.reloader_observer.stop()
            self.reloader_observer.join()

        if self.drivers:
            self.log.info("Resetting all Stream Deck devices.")
            for driver in self.drivers.values():
                try:
                    driver.deck.reset()
                    driver.deck.close()
                except Exception as e:
                    self.log.error(f"Error during deck cleanup for {driver.deck.id()}: {e}")

        if hasattr(self, 'tray_icon'):
            self.tray_icon.stop()
        self.destroy()


    def create_header(self, parent):
        header = ttk.Frame(parent)
        header.grid(row=0, column=0, pady=(0, 10), sticky="ew")
        header.columnconfigure(1, weight=1)

        self.back_button = ttk.Button(header, text="← Back", command=self.go_back)
        self.back_button.grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.back_button.grid_remove()

        self.breadcrumb_bar = ttk.Frame(header)
        self.breadcrumb_bar.grid(row=0, column=1, sticky="w", padx=10)

        ttk.Label(header, text="Device:").grid(row=0, column=2, sticky="w", padx=(10, 2))
        self.deck_selector_var = tk.StringVar()
        self.deck_selector = ttk.Combobox(header, textvariable=self.deck_selector_var, state="readonly", width=30)
        self.deck_selector.grid(row=0, column=3, sticky="e", padx=(5, 0))
        self.deck_selector.bind("<<ComboboxSelected>>", self.on_deck_selected)


    def create_key_grid(self, parent):
        self.grid_frame = ttk.Frame(parent)
        self.grid_frame.grid(row=1, column=0, sticky="nsew")

        for r in range(self.rows):
            self.grid_frame.rowconfigure(r, weight=1)
        for c in range(self.cols):
            self.grid_frame.columnconfigure(c, weight=1)

        for key_index in range(self.keys):
            row = key_index // self.cols
            col = key_index % self.cols

            btn = tk.Label(
                self.grid_frame, image=self.blank_image,
                width=app_settings.DEFAULT_KEY_SIZE, height=app_settings.DEFAULT_KEY_SIZE,
                borderwidth=2, relief="groove"
            )
            btn.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
            btn.key_index = key_index

            btn.bind("<ButtonPress-1>", self._on_widget_press)
            btn.bind("<ButtonRelease-1>", self._on_widget_release)
            btn.bind("<Double-Button-1>", self._on_button_double_click)
            btn.bind("<Button-3>", self.show_context_menu)
            
            self.key_buttons[key_index] = btn
            btn._blank_image_ref = self.blank_image


    def create_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.config(postcommand=self.update_file_menu_state)
        
        file_menu.add_command(label="Save", command=self.save_config_action)
        file_menu.add_separator()
        file_menu.add_checkbutton(
            label="Activate Logging",
            variable=self.logging_enabled_var,
            command=self.toggle_file_logging
        )
        file_menu.add_separator()
        file_menu.add_command(label='Refresh Devices', command=self.rescan_devices)
        #file_menu.add_command(label='Restart', command=self.restart_app) # Currently removed
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)
        
        menubar.add_cascade(
            label="System", 
            menu=file_menu
        )

        # Profiles menu
        profiles_menu = tk.Menu(menubar, tearoff=0)
        profiles_menu.config(postcommand=self.update_profiles_menu_state)
        profiles_menu.add_checkbutton(
            label="Auto Switch Profiles",
            variable=self.context_profile_enabled_var,
            command=self.toggle_context_profiles
        )
        menubar.add_cascade(label="Profiles", menu=profiles_menu)



    # Currently removed !!!
    # def restart_app(self, icon=None, item=None):
    #     """Restarts the current application by launching a new process and exiting."""
    #     self.log.info("Restarting application...")
        
    #     try:
    #         # Launch a new instance of the script with the same arguments
    #         subprocess.Popen([sys.executable] + sys.argv, env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})
    #     except Exception as e:
    #         self.log.error(f"Failed to launch new process on restart: {e}")
    #         Messagebox.show_error("Could not restart the application. Please restart it manually.", "Restart Failed", parent=self)
    #         return

    #     self.exit_app()


    def rescan_devices(self, icon=None, item=None, silent=False):
        """Scans for newly connected or disconnected Stream Decks and updates drivers."""
        self.log.info("Re-scanning for Stream Deck devices...")

        try:
            new_decks_list = DeviceManager().enumerate()
        except Exception as e:
            self.log.error(f"Device enumeration failed: {e}")
            return

        new_deck_ids = {d.id() for d in new_decks_list}

        # Shut down drivers for decks that disappeared or whose handle went stale.
        # A replugged deck usually re-enumerates under the SAME ID, so the ID
        # comparison alone is not enough - the old handle must also be checked.
        disconnected_ids = []
        for deck_id, driver in list(self.drivers.items()):
            still_alive = deck_id in new_deck_ids
            if still_alive:
                try:
                    still_alive = driver.deck.connected()
                except Exception:
                    still_alive = False
            if still_alive:
                continue

            self.log.info(f"Stream Deck disconnected: {deck_id}. Shutting down its driver.")
            disconnected_ids.append(deck_id)
            self.drivers.pop(deck_id)
            if driver in self.all_drivers_list:
                self.all_drivers_list.remove(driver)
            try:
                driver.deck.reset()
                driver.deck.close()
            except Exception as e:
                self.log.warning(f"Cleanup of disconnected deck {deck_id} failed (device likely already gone): {e}")

        # Start drivers for connected decks
        newly_connected_decks = [d for d in new_decks_list if d.id() not in self.drivers]
        for deck in newly_connected_decks:
            deck_id = deck.id()
            self.log.info(f"New Stream Deck detected: {deck.deck_type()} ({deck_id}). Starting driver.")
            try:
                deck.open()
                deck.reset()
                deck.set_brightness(30)

                # Initialize the new driver with all necessary callbacks
                driver = DeckDriver(
                    deck,
                    self.full_config_dta,
                    self.shutdown_event,
                    ui_refresh_callback=self.refresh_ui_from_config,
                    layer_change_callback=self.on_driver_layer_change,
                    ui_visual_refresh_callback=self.refresh_all_button_visuals
                )
                self.drivers[deck_id] = driver
                self.all_drivers_list.append(driver)
                deck.set_key_callback(driver.key_change_callback)
                driver.draw_layer("main")
            except Exception as e:
                # The device may not be ready right after replugging;
                # the device watcher will retry on its next cycle.
                self.log.error(f"Error initializing new deck {deck_id}: {e}")

        # Update the UI dropdown
        self._update_deck_selector()
        self._ensure_background_services()

        if not silent and (disconnected_ids or newly_connected_decks):
            Messagebox.show_info(
                title="Devices Refreshed",
                message="Device list updated.",
                parent=self
            )


    def _update_deck_selector(self):
        """Refreshes the device dropdown list based on currently active drivers."""
        deck_names = []
        if self.drivers:
            for deck_id, driver in self.drivers.items():
                deck_type = driver.deck.deck_type()
                deck_names.append(f"{deck_type} ({deck_id})")
        
        self.deck_selector['values'] = deck_names
        
        # select the first deck available
        if self.active_deck_id not in self.drivers:
            if deck_names:
                self.deck_selector.set(deck_names[0])
                self.on_deck_selected() # Trigger a refresh for the selected deck
            else:
                # last device was disconnected
                self.deck_selector.set('')
                self.active_deck_id = "default_ui"
                self.config_dta = self.full_config_dta.setdefault(self.active_deck_id, {"main": {}})
                self._populate_layers_tree()
                self.sync_ui_to_driver_state("main", [])


    def update_file_menu_state(self):
        """Reads the current config and sets the checkbutton state accordingly."""
        if not self.config_dta:
            return
        is_logging = self.config_dta.get("settings", {}).get("log_to_file", False)
        self.logging_enabled_var.set(is_logging)


    def update_profiles_menu_state(self):
        """Sets the state of the context profile checkbox before the menu is shown."""
        if not self.config_dta:
            return
        
        is_enabled = self.config_dta.get("context_aware_profiles", {}).get("enabled", True)
        self.context_profile_enabled_var.set(is_enabled)


    def toggle_file_logging(self):
        """Updates the config file when the logging checkbutton is toggled."""
        if not self.config_dta:
            return
            
        new_state = self.logging_enabled_var.get()
        settings = self.config_dta.setdefault("settings", {})
        settings["log_to_file"] = new_state
        
        save_config(self.full_config_dta)
        self.log.info(f"File logging for device '{self.active_deck_id}' set to {new_state}.")
        
        # reload the config
        if self.active_driver:
            self.active_driver.reload_config()


    def toggle_context_profiles(self):
        """Updates the config when the context profile checkbox is toggled."""
        if not self.config_dta:
            return
            
        new_state = self.context_profile_enabled_var.get()
        
        # Get or create the context_aware_profiles section for the current deck
        profile_config = self.config_dta.setdefault("context_aware_profiles", {})
        profile_config["enabled"] = new_state
        
        save_config(self.full_config_dta)
        self.log.info(f"Context Aware Profiles for device '{self.active_deck_id}' set to {new_state}.")


    def save_config_action(self):
        try:
            save_config(self.full_config_dta)
            Messagebox.show_info("Success", "Configuration saved successfully.", parent=self)
        except Exception as e:
            Messagebox.show_error("Error", f"Could not save config file: {e}", parent=self)


    def on_deck_selected(self, event=None):
        selected_name = self.deck_selector_var.get()
        
        if "No Device" in selected_name:
            new_deck_id = "default_ui"
        else:
            new_deck_id = selected_name.split('(')[-1][:-1]

        if new_deck_id == self.active_deck_id and self.config_dta:
            return

        self.log.info(f"UI switched to configure deck: {new_deck_id}")
        self.active_deck_id = new_deck_id
        
        active_drv = self.active_driver
        if active_drv:
            self._rebuild_grid_for_deck(active_drv.deck)

        self.config_dta = self.full_config_dta.setdefault(self.active_deck_id, {"main": {}})
        
        self._populate_layers_tree()

        layer_to_draw = active_drv.current_layer if active_drv else "main"
        self.draw_layer(layer_to_draw, nav_type="jump")
        

    def _rebuild_grid_for_deck(self, deck_object):
        """Reconfigures the UI grid for the specified deck's layout."""
        key_count = deck_object.key_count()

        new_rows, new_cols = (3, 5)
        if key_count == 32:
            new_rows, new_cols = 4, 8
            self.geometry("1350x560")
        elif key_count == 15:
            new_rows, new_cols = 3, 5
            self.geometry("1060x500")
        elif key_count == 6:
            new_rows, new_cols = 2, 3
            self.geometry("800x400")
        else:
            new_rows, new_cols = 3, 5
            self.geometry("1060x500")

        if new_rows == self.rows and new_cols == self.cols:
            self.log.info("Selected deck has the same layout. No grid rebuild needed.")
            return

        self.log.info(f"Rebuilding UI grid for new layout: {new_rows}x{new_cols}")
        
        self.rows = new_rows
        self.cols = new_cols
        self.keys = key_count
        self.key_buttons.clear()

        if hasattr(self, 'grid_frame'):
            self.grid_frame.destroy()

        self.create_key_grid(self.main_content_frame)
        self.enable_drag_and_drop()


    def refresh_all_button_visuals(self):
        """Schedules a refresh of all key previews on the UI grid."""
        # 0 for the main UI thread.
        self.after(0, self._do_refresh_all_button_visuals)


    def _do_refresh_all_button_visuals(self):
        """The actual refresh logic that updates every button."""
        self.log.info("Refreshing all UI button visuals from driver callback...")
        for i in range(self.keys):
            self.update_button_visuals(i)


    def _get_key_style_info(self, key_config, key_index):
        action_type = key_config.get("action_type")
        
        default_bg = "#000000"
        if action_type is None and not key_config:
            default_bg = "#2E2E2E"
        elif action_type == "back":
            default_bg = "#2A446F"

        style = {
            "bg": key_config.get("background", default_bg),
            "relief": "sunken" if (action_type is None and not key_config) else "groove"
        }

        return style


    def _render_key_image_for_ui(self, size, bg_color, icon_name, label_text, label_pos_config, font_color, font_settings, is_layer_key=False, is_dynamic_key=False, is_active_toggle=False):
        image = Image.new("RGB", size, bg_color)
        draw = ImageDraw.Draw(image)

        if icon_name:
            icon_path = os.path.join(ICON_FOLDER, icon_name)
            try:
                icon = Image.open(icon_path).convert("RGBA")
                icon.thumbnail(size)
                icon_pos = ((size[0] - icon.width) // 2, (size[1] - icon.height) // 2)
                image.paste(icon, icon_pos, icon)
            except Exception as e:
                self.log.warning(f"Could not load icon '{icon_path}': {e}")
        
        if label_text:
            font_to_use = None
            font_size_scaled = max(12, int(size[0] / 6.5))
            
            if font_settings:
                font_size_scaled = font_settings.get("size", font_size_scaled)
                font_family = font_settings.get("family")
                try:
                    if font_family:
                        font_file = fm.findfont(fm.FontProperties(family=font_family))
                        font_to_use = ImageFont.truetype(font_file, font_size_scaled)
                except Exception:
                    self.log.warning(f"Could not load custom font '{font_family}'.")

            if not font_to_use:
                try:
                    font_to_use = ImageFont.truetype(FONT_PATH, font_size_scaled)
                except IOError:
                    font_to_use = ImageFont.load_default()

            w, h = size
            margin = h * 0.07

            if '\n' in label_text:
                bbox = draw.multiline_textbbox((0, 0), label_text, font=font_to_use, align="center")
                text_h = bbox[3] - bbox[1]
                x = w / 2
                if label_pos_config == "top": y = margin
                elif label_pos_config == "middle": y = (h - text_h) / 2
                else: y = h - text_h - margin
                draw.multiline_text((x, y), label_text, font=font_to_use, fill=font_color, align="center", anchor="ma", stroke_width=1, stroke_fill="black")
            else:
                if label_pos_config == "top": anchor, pos = "mt", (w/2, margin)
                elif label_pos_config == "middle": anchor, pos = "mm", (w/2, h/2)
                else: anchor, pos = "ms", (w/2, h - margin)
                draw.text(pos, label_text, font=font_to_use, anchor=anchor, fill=font_color, stroke_width=1, stroke_fill="black")

        if is_dynamic_key:
            corner_size = int(size[0] * 0.3)
            p1 = (0, 0)
            p2 = (corner_size, 0)
            p3 = (0, corner_size)
            draw.polygon([p1, p2, p3], fill="#00C853")
            draw.line([(corner_size, 0), (0, corner_size)], fill=(0, 0, 0, 77), width=1)

        if is_layer_key:
            corner_size = int(size[0] * 0.3)
            p1 = (size[0] - corner_size, 0)
            p2 = (size[0], 0)
            p3 = (size[0], corner_size)
            draw.polygon([p1, p2, p3], fill="#FFD700")
            draw.line([(size[0] - corner_size, 0), (size[0], corner_size)], fill=(0, 0, 0, 77), width=1)

        if is_active_toggle:
            draw_active_border(draw, size)
        return image


    def draw_layer(self, layer_name, nav_type="forward"):
        UI_DATA_CACHE.clear()
        if nav_type == "forward":
            if self.current_layer:
                self.layer_history.append(self.current_layer)
        elif nav_type == "jump":
            self.layer_history.clear()
        
        self.current_layer = layer_name
        if self.current_layer not in self.config_dta:
            self.current_layer = "main"

        self.update_breadcrumbs()

        if self.layer_history:
            self.back_button.grid()
        else:
            self.back_button.grid_remove()

        for i in range(self.keys):
            self.update_button_visuals(i)


    def update_button_visuals(self, key_index, live_dta=None):
        button = self.key_buttons.get(key_index)
        if not button: 
            return

        key_cfg_dict = self.config_dta.get(self.current_layer, {}).get(str(key_index), {})
        style_info = self._get_key_style_info(key_cfg_dict, key_index)
        
        icon_name = key_cfg_dict.get("icon", "")
        label_text = live_dta if live_dta is not None else key_cfg_dict.get("label", "")
        label_pos = key_cfg_dict.get("label_pos", "bottom")
        font_color = key_cfg_dict.get("font_color", "white")
        font_settings = key_cfg_dict.get("font_settings")
        action_type = key_cfg_dict.get("action_type")

        is_active_toggle = False
        if action_type in ("toggle_key", "toggle_key_timer"):
            active_driver = self.active_driver
            if active_driver:
                state_key = (active_driver.deck.id(), key_index)
                if state_key in active_driver.toggled_keys or state_key in active_driver.timed_toggles:
                    is_active_toggle = True

        is_layer_key = (action_type == "layer")
        is_dynamic_key = key_cfg_dict.get("display", {}).get("type") == "dynamic"
        key_size_tuple = (self.key_pixel_size, self.key_pixel_size)
        
        pil_image = self._render_key_image_for_ui(
            size=key_size_tuple, 
            bg_color=style_info['bg'], 
            icon_name=icon_name,
            label_text=label_text, 
            label_pos_config=label_pos, 
            font_color=font_color,
            font_settings=font_settings, 
            is_layer_key=is_layer_key, 
            is_dynamic_key=is_dynamic_key, 
            is_active_toggle=is_active_toggle
        )

        photo_image = ImageTk.PhotoImage(pil_image)
        button.config(image=photo_image, text="", relief=style_info['relief'])
        button.image = photo_image


    def _on_widget_press(self, event):
        event.widget.config(relief="sunken")
        self._on_button_press_logic(event)


    def _on_widget_release(self, event):
        key_index = event.widget.key_index
        key_cfg_dict = self.config_dta.get(self.current_layer, {}).get(str(key_index), {})
        style_info = self._get_key_style_info(key_cfg_dict, key_index)
        event.widget.config(relief=style_info['relief'])


    def _on_button_press_logic(self, event):
        key_index = getattr(event.widget, "key_index", None)
        if key_index is None or self._click_timer is not None: 
            return
        self._click_timer = self.after(app_settings.DOUBLE_CLICK_DELAY_MS, lambda: self.handle_single_click(key_index))


    def _on_button_double_click(self, event):
        if self._click_timer is not None:
            self.after_cancel(self._click_timer)
            self._click_timer = None
        key_index = getattr(event.widget, "key_index", None)
        if key_index is not None:
            self.handle_double_click(key_index)


    def handle_single_click(self, key_index):
        self._click_timer = None
        KeyConfigWindow(
            parent=self, key_index=key_index, config_dta=self.config_dta,
            current_layer=self.current_layer, on_save_callback=self.save_and_refresh
        )


    def handle_double_click(self, key_index):
        key_config = self.config_dta.get(self.current_layer, {}).get(str(key_index), {})

        if key_config.get("action_type") == "layer":
            payload = key_config.get("payload")
            target_layer = None
            
            # Check if the payload is a dictionary (for layers with secondary actions) or a simple string
            if isinstance(payload, dict):
                target_layer = payload.get("target")
            else:
                target_layer = payload
            
            if target_layer and self.active_driver:
                self.active_driver.change_layer_forward(target_layer)
        else:
            # empty key, any action that is not layer, use single-click to  open the config window
            self.handle_single_click(key_index)


    def go_back(self):
        if self.active_driver:
            self.active_driver.change_layer_back()


    def go_to_layer(self, target_layer):
        if target_layer == self.current_layer: return
        if self.active_driver:
            try:
                # Find the target in the current history and truncate the history
                target_index = self.layer_history.index(target_layer)
                # Manually set the drivers history before the jump
                self.active_driver.layer_history = self.layer_history[:target_index]
                self.active_driver.jump_to_layer(target_layer)
            except ValueError:
                self.log.warning(f"Attempted to jump to layer '{target_layer}' not in history.")


    def update_breadcrumbs(self):
        for widget in self.breadcrumb_bar.winfo_children():
            widget.destroy()

        path = self.layer_history + [self.current_layer]

        for i, layer_name in enumerate(path):
            if i < len(path) - 1:
                link = ttk.Button(
                    self.breadcrumb_bar, text=layer_name.capitalize(),
                    style="Link.TButton", command=lambda ln=layer_name: self.go_to_layer(ln))
                link.pack(side="left")
                ttk.Label(self.breadcrumb_bar, text=" > ").pack(side="left")
            else:
                ttk.Label(self.breadcrumb_bar, text=layer_name.capitalize(), font=("Arial", 12, "bold")).pack(side="left")


    def save_and_refresh(self, layer_name, key_index, new_config):
        if layer_name not in self.config_dta:
            self.config_dta[layer_name] = {}
        self.config_dta[layer_name][str(key_index)] = new_config

        save_config(self.full_config_dta)

        for driver in self.drivers.values():
            driver.reload_config()

        self.update_button_visuals(key_index)


    def on_root_config(self, event):
        if self.resize_job:
            self.after_cancel(self.resize_job)
        self.resize_job = self.after(80, self._recalc_key_sizes)


    def _recalc_key_sizes(self):
        self.resize_job = None
        self.main_content_frame.update_idletasks()
        gw = max(100, self.main_content_frame.winfo_width())
        gh = max(100, self.main_content_frame.winfo_height())
        header_height = self.breadcrumb_bar.winfo_height()
        available_h = gh - header_height
        
        cell_w = (gw // self.cols) - 12
        cell_h = (available_h // self.rows) - 12
        new_size = max(48, min(220, min(cell_w, cell_h)))

        if abs(new_size - getattr(self, "key_pixel_size", app_settings.DEFAULT_KEY_SIZE)) >= 4:
            self.key_pixel_size = new_size
            for btn in self.key_buttons.values():
                btn.config(width=self.key_pixel_size, height=self.key_pixel_size)
            for i in range(self.keys):
                self.update_button_visuals(i)


    def show_context_menu(self, event):
        btn = event.widget
        self._context_key_index = getattr(btn, "key_index", None)
        if self._context_key_index is None:
            return

        # Enable or disable the "Execute" menu item
        key_config = self.config_dta.get(self.current_layer, {}).get(str(self._context_key_index))
        templates = self.full_config_dta.get("key_templates", {})

        # Enable/disable menu items based on whether the key is configured
        if key_config:
            self.context_menu.entryconfig("Execute", state="normal")
            self.context_menu.entryconfig("Save as Template...", state="normal")
            self.context_menu.entryconfig("Apply Template", state="disabled")
            self.context_menu.entryconfig("Copy Key", state="normal")
        else:
            self.context_menu.entryconfig("Execute", state="disabled")
            self.context_menu.entryconfig("Save as Template...", state="disabled")
            # Only enable "Apply Template" if there are templates to apply
            self.context_menu.entryconfig("Apply Template", state="normal" if templates else "disabled")
            self.context_menu.entryconfig("Copy Key", state="disabled")

        # Dynamically populate the "Apply Template" submenu
        self.apply_template_menu.delete(0, "end")
        if templates:
            for name in sorted(templates.keys()):
                self.apply_template_menu.add_command(
                    label=name,
                    command=lambda n=name: self.apply_template(n)
                )

        self.context_menu.entryconfig("Paste Style", state="normal" if self._style_clipboard else "disabled")
        # Enable "Paste Key" only if there's a key in the clipboard
        self.context_menu.entryconfig("Paste Key", state="normal" if self._key_clipboard else "disabled")

        self.context_menu.tk_popup(event.x_root, event.y_root)


    def copy_key_style(self):
        if self._context_key_index is None:
            return
        key_config = self.config_dta.get(self.current_layer, {}).get(str(self._context_key_index), {})
        style_keys = ["icon", "label", "label_pos", "font_color", "font_settings"]
        self._style_clipboard = {k: key_config[k] for k in style_keys if k in key_config}
        self.log.info(f"Copied style from key {self._context_key_index}: {self._style_clipboard}")


    def paste_key_style(self):
        if self._context_key_index is None or not self._style_clipboard:
            return
        layer_conf = self.config_dta.setdefault(self.current_layer, {})
        key_conf = layer_conf.setdefault(str(self._context_key_index), {})
        key_conf.update(self._style_clipboard)
        self.log.info(f"Pasted style to key {self._context_key_index}")
        self.update_button_visuals(self._context_key_index)
        save_config(self.full_config_dta)
        if self.active_driver:
            self.active_driver.reload_config()


    def copy_key_full(self):
        """Copies the entire configuration of the right-clicked key."""
        if self._context_key_index is None:
            return
        key_config = self.config_dta.get(self.current_layer, {}).get(str(self._context_key_index))
        if key_config:
            self._key_clipboard = copy.deepcopy(key_config)
            self.log.info(f"Copied full key configuration from key {self._context_key_index}.")


    def paste_key_full(self):
        """Pastes the copied key configuration to the right-clicked key."""
        if self._context_key_index is None or not self._key_clipboard:
            return
        
        layer_conf = self.config_dta.setdefault(self.current_layer, {})
        layer_conf[str(self._context_key_index)] = copy.deepcopy(self._key_clipboard)
        
        self.log.info(f"Pasted full key configuration to key {self._context_key_index}.")
        
        save_config(self.full_config_dta)
        self.update_button_visuals(self._context_key_index)
        if self.active_driver:
            self.active_driver.reload_config()


    def edit_context_key(self):
        if self._context_key_index is not None:
            if self._click_timer is not None:
                self.after_cancel(self._click_timer)
                self._click_timer = None
            self.handle_single_click(self._context_key_index)


    # Methods for saving and applying templates
    def save_key_as_template(self):
        """Saves the configuration of the right-clicked key as a new template."""
        if self._context_key_index is None:
            return
        
        key_config = self.config_dta.get(self.current_layer, {}).get(str(self._context_key_index))
        if not key_config:
            return

        template_name = simpledialog.askstring("Save Template", "Enter a name for this template:", parent=self)
        if not template_name or not template_name.strip():
            return
        
        templates = self.full_config_dta.setdefault("key_templates", {})
        templates[template_name] = copy.deepcopy(key_config)
        save_config(self.full_config_dta)
        self.log.info(f"Saved key {self._context_key_index} as template '{template_name}'.")


    def apply_template(self, template_name):
        """Applies a saved template to the right-clicked empty key."""
        if self._context_key_index is None:
            return

        template_config = self.full_config_dta.get("key_templates", {}).get(template_name)
        if not template_config:
            self.log.error(f"Template '{template_name}' not found.")
            return
        
        # Apply the config to the current deck's layer
        layer_conf = self.config_dta.setdefault(self.current_layer, {})
        layer_conf[str(self._context_key_index)] = copy.deepcopy(template_config)
        
        save_config(self.full_config_dta)
        
        # Refresh visuals and hardware
        self.update_button_visuals(self._context_key_index)
        if self.active_driver:
            self.active_driver.reload_config()
        
        self.log.info(f"Applied template '{template_name}' to key {self._context_key_index}.")


    def delete_context_key(self):
            if self._context_key_index is None:
                return

            if not Messagebox.yesno(
                f"Are you sure you want to permanently delete the configuration for Key {self._context_key_index} on the current layer ('{self.current_layer}')?",
                "Confirm Deletion", parent=self):
                return

            layer_conf = self.config_dta.get(self.current_layer)
            key_index_str = str(self._context_key_index)

            if layer_conf and key_index_str in layer_conf:
                del layer_conf[key_index_str]
                self.log.info(f"Deleted key {key_index_str} from layer '{self.current_layer}'")
                save_config(self.full_config_dta)
                self.update_button_visuals(self._context_key_index)
                if self.active_driver:
                    self.active_driver.reload_config()


    def execute_context_action(self):
        """Executes the action for the currently right-clicked key."""
        if self._context_key_index is None:
            return
        
        if self.active_driver:
            self.active_driver.execute_key_action(self._context_key_index)
        else:
            self.log.warning("Cannot execute key action: No active driver.")


    def enable_drag_and_drop(self):
        for key_index, btn in self.key_buttons.items():
            btn.drop_target_register(DND_FILES, DND_ALL)
            btn.dnd_bind('<<Drop>>', lambda e, idx=key_index: self.on_drop(e, idx))
            btn.drag_source_register(DND_ALL)
            btn.dnd_bind('<<DragInitCmd>>', lambda e, idx=key_index: self.on_drag_start(e, idx))
            btn.dnd_bind('<<DragEndCmd>>', self.on_drag_end)


    def on_drag_start(self, event, key_index):
        if self._click_timer is not None:
            self.after_cancel(self._click_timer)
            self._click_timer = None
        self._dnd_source_key = key_index
        return (COPY, DND_TEXT, 'internal_key_drag')


    def on_drag_end(self, event):
        self._dnd_source_key = None


    def on_drop(self, event, target_key_index):
        if event.data == 'internal_key_drag':
            self.on_internal_drop(event, target_key_index)
        else:
            self.handle_icon_drop(event, target_key_index)


    def on_internal_drop(self, event, target_key_index):
        source_index = self._dnd_source_key
        if source_index is None or source_index == target_key_index:
            return

        source_index_str, target_index_str = str(source_index), str(target_key_index)
        layer_conf = self.config_dta.get(self.current_layer, {})
        source_cfg = layer_conf.get(source_index_str, {})
        is_copy = any("Control" in m for m in event.modifiers)

        self.log.info(f"DnD: {'Copying' if is_copy else 'Moving'} key {source_index_str} to {target_index_str}")
        if is_copy:
            layer_conf[target_index_str] = copy.deepcopy(source_cfg)
        else:
            target_cfg = layer_conf.get(target_index_str, {})
            layer_conf[target_index_str] = source_cfg
            layer_conf[source_index_str] = target_cfg

        self.update_button_visuals(source_index)
        self.update_button_visuals(target_key_index)
        save_config(self.full_config_dta)
        if self.active_driver:
            self.active_driver.reload_config()


    def handle_icon_drop(self, event, key_index):
        files = self.tk.splitlist(event.data)
        if not files: return
        file_path = files[0]
        if not os.path.exists(file_path): return

        os.makedirs(ICON_FOLDER, exist_ok=True)
        basename = os.path.basename(file_path)
        dest = os.path.join(ICON_FOLDER, basename)

        try:
            if os.path.abspath(file_path) != os.path.abspath(dest):
                if not os.path.exists(dest): shutil.copy2(file_path, dest)
            self.config_dta.setdefault(self.current_layer, {})
            key_cfg = self.config_dta[self.current_layer].get(str(key_index), {})
            key_cfg["icon"] = basename
            self.config_dta[self.current_layer][str(key_index)] = key_cfg
            save_config(self.full_config_dta)
            self.update_button_visuals(key_index)
            if self.active_driver:
                self.active_driver.reload_config()  
        except Exception as e:
            messagebox.showerror("Error", f"Could not assign dropped icon: {e}")


    def update_dynamic_previews(self):
        """Periodically checks the cache and updates UI keys with live data."""
        for key_index, button in self.key_buttons.items():
            cache_key = (self.active_deck_id, self.current_layer, key_index)
            if cache_key in UI_DATA_CACHE:
                live_text = UI_DATA_CACHE[cache_key]
                self.update_button_visuals(key_index, live_dta=live_text)
        
        self.after(1000, self.update_dynamic_previews)


    def process_ui_queue(self):
        """Processes commands from the UI_CMD_QUEUE to update UI from background threads."""
        try:
            while not UI_CMD_QUEUE.empty():
                msg = UI_CMD_QUEUE.get_nowait()
                command = msg.get("command")

                if command == "show_cycle_window":
                    if self.cycle_window:
                        self.cycle_window.destroy()
                    self.cycle_window = CycleWindow(msg.get("items"))
                
                elif command == "update_cycle_selection":
                    if self.cycle_window:
                        self.cycle_window.update_selection(msg.get("index"))

                elif command == "hide_cycle_window":
                    if self.cycle_window:
                        self.cycle_window.destroy()
                        self.cycle_window = None

        except Exception as e:
            self.log.error(f"Error processing UI queue: {e}")
        finally:
            # Reschedule the checker to run again
            self.after(100, self.process_ui_queue)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stream Deck Tool UI")
    parser.add_argument(
        '--without-driver',
        action='store_true',
        help="Run the UI only, without initializing the Stream Deck driver."
    )
    args = parser.parse_args()
    os.makedirs(ICON_FOLDER, exist_ok=True)
    app = StreamDeckConfigurator(start_driver=not args.without_driver)
    app.mainloop()