#--------------------------------------------------------------------
# Import packages
#--------------------------------------------------------------------
import tkinter as tk
import time

#--------------------------------------------------------------------
# Import sub-packages
#--------------------------------------------------------------------
from ttkbootstrap import ttk
from pynput import mouse, keyboard

#--------------------------------------------------------------------
# Class
#--------------------------------------------------------------------
class MacroRecorderWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Macro Recorder")
        self.geometry("400x200")
        self.resizable(False, False)

        self.recorded_actions = []
        self.last_event_time = None
        self.mouse_listener = None
        self.keyboard_listener = None
        
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill="both", expand=True)

        self.status_label = ttk.Label(main_frame, text="Press 'Start Recording' to begin.", font=("Arial", 12))
        self.status_label.pack(pady=(0, 15))

        instructions = "• Each key press, release, and mouse click will be recorded.\n" \
                       "• Delays between actions are also recorded.\n" \
                       "• Press the 'Esc' key to stop recording."
        ttk.Label(main_frame, text=instructions, justify="left").pack(pady=(0, 20))
        
        self.record_button = ttk.Button(main_frame, text="Start Recording", command=self.start_recording, style="success.TButton")
        self.record_button.pack(fill="x")

        # Bind the window closing event to stop the listeners
        self.protocol("WM_DELETE_WINDOW", self.stop_recording)


    def start_recording(self):
        self.record_button.config(state="disabled")
        self.status_label.config(text="🔴 Recording... Press 'Esc' to stop.")
        
        self.recorded_actions.clear()
        self.last_event_time = time.time()
        
        # Start listening to mouse and keyboard events
        self.mouse_listener = mouse.Listener(on_click=self.on_click, on_scroll=self.on_scroll)
        self.keyboard_listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        self.mouse_listener.start()
        self.keyboard_listener.start()


    def stop_recording(self):
        if self.mouse_listener and self.mouse_listener.is_alive():
            self.mouse_listener.stop()
        if self.keyboard_listener and self.keyboard_listener.is_alive():
            self.keyboard_listener.stop()
        
        # Ensure the window is not already destroyed
        if self.winfo_exists():
            self.destroy()


    def _add_delay(self):
        """Adds a delay action based on the time since the last event."""
        if self.last_event_time:
            delay = time.time() - self.last_event_time
            # Cap the max delay to 3 seconds to avoid long idle times
            if delay > 0.01:
                 self.recorded_actions.append({
                    "action_type": "delay",
                    "payload": round(min(delay, 3.0), 4)
                })
        self.last_event_time = time.time()


    def _get_key_name(self, key):
        """Gets a string representation of a key."""
        try:
            return key.char
        except AttributeError:
            return str(key).replace("Key.", "")


    # Listener Callback Methods
    def on_press(self, key):
        self._add_delay()
        self.recorded_actions.append({"action_type": "key_press", "payload": self._get_key_name(key)})


    def on_release(self, key):
        self._add_delay()
        self.recorded_actions.append({"action_type": "key_release", "payload": self._get_key_name(key)})
        if key == keyboard.Key.esc:
            # Marshal to the Tk main thread; calling destroy() from the pynput
            # listener thread crashes Tkinter, and stopping the listener from
            # within its own callback deadlocks pynput.
            self.after(0, self.stop_recording)


    def on_click(self, x, y, button, pressed):
        self._add_delay()
        self.recorded_actions.append({
            "action_type": "mouse_click",
            "payload": {"button": button.name, "pressed": pressed, "x": int(x), "y": int(y)}
        })


    def on_scroll(self, x, y, dx, dy):
        self._add_delay()
        self.recorded_actions.append({
            "action_type": "mouse_scroll",
            "payload": {"dx": dx, "dy": dy}
        })