#--------------------------------------------------------------------
# Import packages
#--------------------------------------------------------------------
import subprocess
import time
import requests
import traceback
import os
import sys
import psutil
import threading
import win32clipboard
import pygetwindow as gw 

if sys.platform == "win32":
    import win32gui
    import win32process
    import pywintypes
    import ctypes
    from ctypes import wintypes

    # structures and constants for SendInput
    PUL = ctypes.POINTER(wintypes.ULONG)
    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD),
                    ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", PUL)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG),
                    ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", PUL)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD),
                    ("wParamL", wintypes.WORD),
                    ("wParamH", wintypes.WORD)]

    class INPUT_I(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT),
                    ("mi", MOUSEINPUT),
                    ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD),
                    ("ii", INPUT_I)]

    # Define virtual key codes for media keys
    VK_MEDIA_PLAY_PAUSE = 0xB3
    VK_MEDIA_NEXT_TRACK = 0xB0
    VK_MEDIA_PREV_TRACK = 0xB1
    VK_MEDIA_STOP = 0xB2
    KEYEVENTF_KEYUP = 0x0002
    INPUT_KEYBOARD = 1

    def _send_media_key(vk_code):
        """Helper function to send a hardware-level media key press using SendInput."""
        # Key down
        x = INPUT(type=INPUT_KEYBOARD,
                  ii=INPUT_I(ki=KEYBDINPUT(wVk=vk_code, wScan=0, dwFlags=0, time=0, dwExtraInfo=None)))
        ctypes.windll.user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))

        time.sleep(0.05)

        # Key up
        x = INPUT(type=INPUT_KEYBOARD,
                  ii=INPUT_I(ki=KEYBDINPUT(wVk=vk_code, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=None)))
        ctypes.windll.user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))

from pynput.keyboard import Key, Controller as KeyboardController
from pynput.mouse import Button, Controller as MouseController
from screeninfo import get_monitors
from collections import deque
from queue import Queue

#--------------------------------------------------------------------
# Import local packages
#--------------------------------------------------------------------
from config_manager import log
from audio_utils import set_default_audio_device, volume_up, volume_down, toggle_mute

CLIPBOARD_HISTORY = deque(maxlen=15)
WINDOW_SNAP_STATES = {}     # last snap state of windows
CYCLE_WINDOW_INDEX = {}     # last-used index for window cycling
UI_CMD_QUEUE = Queue()      # queue for the commands action

keyboard = KeyboardController()
mouse = MouseController()

class ClipboardManager:
    """Manages the state of the clipboard history pop-up window."""
    def __init__(self):
        self.is_active = False
        self.items = []
        self.current_index = 0
        self.timeout_timer = None
        self.trigger_key_info = None


    @staticmethod
    def set_clipboard(text):
        try:
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text or "", win32clipboard.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()


    @staticmethod
    def get_clipboard():
        txt = None
        try:
            win32clipboard.OpenClipboard()
            txt = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        except TypeError:
            # no content
            pass
        finally:
            win32clipboard.CloseClipboard()
        return txt
    

    def _commit(self):
        """Called by the timer to paste the selected clipboard item."""
        if not self.items or self.items[self.current_index] in [
            "[Clipboard History is Empty]",
            "[ Exit ]"
        ]:
            self.close()
            return
        selected_item = self.items[self.current_index]
        log.info(f"Clipboard Manager committing selection.")
        
        try:
            self.set_clipboard(selected_item)
            time.sleep(0.1)
            execute_hotkey("ctrl+v")
        except Exception as e:
            log.error(f"Clipboard Manager failed to paste: {e}")
        
        self.close()


    def start(self, trigger_key_info):
        """Gets the current clipboard history and shows the window."""
        if self.is_active:
            self.close()

        # Start with a clean list for the items to display
        display_items = []        
        CLIPBOARD_HISTORY.appendleft(self.get_clipboard())
        display_items.extend(list(CLIPBOARD_HISTORY))
        
        # add the Exit item to the final list
        display_items.append("[ Exit ]")
        self.items = display_items

        self.trigger_key_info = trigger_key_info
        self.is_active = True
        self.current_index = 0
        
        UI_CMD_QUEUE.put({'command': 'show_cycle_window', 'items': self.items})

        self.timeout_timer = threading.Timer(3.0, self._commit)
        self.timeout_timer.daemon = True
        self.timeout_timer.start()


    def cycle(self):
        """Cycles to the next item and resets the timeout."""
        if not self.is_active:
            return

        if self.timeout_timer:
            self.timeout_timer.cancel()

        self.current_index = (self.current_index + 1) % len(self.items)
        UI_CMD_QUEUE.put({'command': 'update_cycle_selection', 'index': self.current_index})

        self.timeout_timer = threading.Timer(3.0, self._commit)
        self.timeout_timer.daemon = True
        self.timeout_timer.start()


    def close(self):
        """Closes the window and resets the state."""
        if not self.is_active:
            return
        if self.timeout_timer:
            self.timeout_timer.cancel()
        UI_CMD_QUEUE.put({'command': 'hide_cycle_window'})
        self.is_active = False
        self.items = []
        self.current_index = 0
        self.timeout_timer = None
        self.trigger_key_info = None


CLIPBOARD_MANAGER = ClipboardManager()

class CommandCycleManager:
    """Manages the state of the command cycle pop-up window."""
    def __init__(self):
        self.is_active = False
        self.items = []
        self.current_index = 0
        self.timeout_timer = None
        self.trigger_key_info = None


    def _commit(self):
        """Called by the timer to execute the selected action."""
        selected_item = self.items[self.current_index]
        
        # Only type the text if it is not the exit command
        if selected_item != "[ Exit ]":
            try:
                time.sleep(0.1) # Give focus a moment to return
                keyboard.type(selected_item)
            except Exception as e:
                log.error(f"Command Cycle failed to type text: {e}")
        
        self.close()


    def start(self, payload, trigger_key_info):
        """Parses payload and shows the window for the first time."""
        if self.is_active:
            self.close()

        # Parse payload and add the required Exit item
        self.items = [item.strip() for item in payload.split('@@@@') if item.strip()]
        if not self.items:
            return
        self.items.append("[ Exit ]")

        self.trigger_key_info = trigger_key_info
        self.is_active = True
        self.current_index = 0
        
        # Command the UI thread to create the window
        UI_CMD_QUEUE.put({'command': 'show_cycle_window', 'items': self.items})
        
        # Start the two second timeout
        self.timeout_timer = threading.Timer(2.0, self._commit)
        self.timeout_timer.daemon = True
        self.timeout_timer.start()


    def cycle(self):
        """Cycles to the next item and resets the timeout."""
        if not self.is_active:
            return

        # Cancel the previous timer
        if self.timeout_timer:
            self.timeout_timer.cancel()

        # next item
        self.current_index = (self.current_index + 1) % len(self.items)

        # Command the UI thread to update the selection highlight
        UI_CMD_QUEUE.put({'command': 'update_cycle_selection', 'index': self.current_index})

        self.timeout_timer = threading.Timer(2.0, self._commit)
        self.timeout_timer.daemon = True
        self.timeout_timer.start()


    def close(self):
        """Closes the window and resets the state."""
        if not self.is_active:
            return
            
        if self.timeout_timer:
            self.timeout_timer.cancel()

        UI_CMD_QUEUE.put({'command': 'hide_cycle_window'})
        
        self.is_active = False
        self.items = []
        self.current_index = 0
        self.timeout_timer = None
        self.trigger_key_info = None


CMD_CYCLE_MANAGER = CommandCycleManager()

def _get_pynput_key(key_name):
    """Helper to convert a string back to a pynput key object."""
    if isinstance(key_name, str) and key_name.startswith("Key."):
        key_name = key_name.replace("Key.", "")
    
    try:
        # Check if it is a special key in the Key enum
        return getattr(Key, key_name)
    except AttributeError:
        # Otherwise, it is a normal character
        return key_name
    

def execute_cycle_windows(payload):
    """Cycles focus through all open, visible windows of the given application(s)."""
    if not payload or not isinstance(payload, str):
        return ValueError("Cycle Windows action requires at least one executable name in the payload.")
    
    # Parse the payload into a list of executables, cleaning each name.
    exe_names_to_find = [name.strip().lower() for name in payload.split('|') if name.strip()]
    if not exe_names_to_find:
        return ValueError("Cycle Windows payload is empty or invalid.")
    
    try:
        # Find all windows that belong to any of the specified executables
        matching_windows = []
        all_windows = gw.getAllWindows()
        for window in all_windows:
            if not window.visible or window.isMinimized or not window.title:
                continue
            try:
                _, pid = win32process.GetWindowThreadProcessId(window._hWnd)
                process_name = psutil.Process(pid).name().lower()
                # Check if the window's process is in our target list.
                if process_name in exe_names_to_find:
                    matching_windows.append(window)
            except (psutil.NoSuchProcess, psutil.AccessDenied, pywintypes.error):
                continue
        
        if not matching_windows:
            log.warning(f"Cycle Windows: No open windows found for '{payload}'.")
            return None

        # Determine the next window to focus using the raw payload as a unique key for this cycle group
        last_index = CYCLE_WINDOW_INDEX.get(payload, -1)
        next_index = (last_index + 1) % len(matching_windows)
        
        window_to_focus = matching_windows[next_index]

        # Activate the window
        log.info(f"Cycling to window: '{window_to_focus.title}'")
        if window_to_focus.isMinimized:
            window_to_focus.restore()
        
        try:
            keyboard.press(Key.alt)
            keyboard.release(Key.alt)
            time.sleep(0.05)
            win32gui.SetForegroundWindow(window_to_focus._hWnd)
        except pywintypes.error:
            window_to_focus.activate()
        
        # Update the index for the next cycle
        CYCLE_WINDOW_INDEX[payload] = next_index
        return None

    except Exception as e:
        log.error(f"Error in cycle_windows action: {e}")
        traceback.print_exc()
        return e


def execute_http_request(payload):
    """Executes an HTTP request based on the payload."""
    if not isinstance(payload, dict) or "url" not in payload:
        return ValueError("HTTP request payload must be a dict with a 'url' key.")
    
    try:
        response = requests.request(
            method=payload.get("method", "GET"),
            url=payload["url"],
            json=payload.get("json"),
            headers=payload.get("headers"),
            timeout=10 # Add a timeout to prevent the app from hanging
        )
        # Check if the request was successful
        response.raise_for_status() 
        print(f"HTTP request to {payload['url']} successful (Status: {response.status_code}).")
        return None
    except requests.exceptions.RequestException as e:
        print(f"HTTP Request failed: {e}")
        return e
    

def execute_hotkey(payload):
    # This function is unchanged
    try:
        parts = payload.lower().split('+')
        keys_to_press, special_keys = [], []
        key_map = {'ctrl': Key.ctrl, 'alt': Key.alt, 'shift': Key.shift, 'cmd': Key.cmd, 'win': Key.cmd}
        for part in parts:
            part = part.strip()
            if part in key_map:
                special_keys.append(key_map[part])
            elif hasattr(Key, part):
                keys_to_press.append(getattr(Key, part))
            else:
                keys_to_press.append(part)
        for special_key in special_keys: keyboard.press(special_key)
        for key in keys_to_press:
            keyboard.press(key)
            keyboard.release(key)
        for special_key in reversed(special_keys): keyboard.release(special_key)
        return None
    except Exception as e:
        return e


def execute_window_action(payload):
    """
    Executes a window management command, with robust focus handling.
    """
    try:
        command = None
        target_window = None
        monitor_number = None

        if isinstance(payload, dict):
            command = payload.get("command")
            window_title = payload.get("window_title")
            monitor_number = payload.get("monitor")
        else:
            command = payload
            window_title = None

        if not command:
            return None

        if window_title:
            matching_windows = gw.getWindowsWithTitle(window_title)
            if matching_windows:
                target_window = matching_windows[0]
                if target_window.isMinimized:
                    target_window.restore()

                activated = False
                if sys.platform == "win32":
                    try:
                        # This simulates an Alt key press to help Windows allow the focus change
                        keyboard.press(Key.alt)
                        keyboard.release(Key.alt)
                        time.sleep(0.05)
                        
                        win32gui.SetForegroundWindow(target_window._hWnd)
                        activated = True
                    except pywintypes.error as e:
                        if e.winerror == 0:
                            activated = True
                        else:
                            print(f"[DEBUG] SetForegroundWindow failed with real error: {e}")
                
                if not activated:
                    try:
                        target_window.activate()
                    except gw.PyGetWindowException as e:
                        if not (hasattr(e, 'winerror') and e.winerror == 0):
                            raise e

                time.sleep(0.2)
            else:
                return None
        else:
            target_window = gw.getActiveWindow()

        if not target_window or target_window.isMinimized:
            return None

        monitors = get_monitors()
        target_monitor = None

        if monitor_number:
            try:
                monitor_index = int(monitor_number) - 1 # Convert 1-based to 0-based index
                if 0 <= monitor_index < len(monitors):
                    target_monitor = monitors[monitor_index]
                else:
                    log.warning(f"Invalid monitor number: {monitor_number}. Total monitors: {len(monitors)}. Falling back to current.")
            except (ValueError, TypeError):
                log.warning(f"Invalid monitor number format: {monitor_number}. Falling back to current.")

        win_center_x = target_window.left + target_window.width / 2
        current_monitor = monitors[0]
        for monitor in monitors:
            if monitor.x <= win_center_x < monitor.x + monitor.width:
                current_monitor = monitor
                break

        if command == "move_to_next_monitor":
            if len(monitors) < 2: return None
            current_monitor_index = monitors.index(current_monitor)
            next_monitor_index = (current_monitor_index + 1) % len(monitors)
            next_monitor = monitors[next_monitor_index]
            new_x = next_monitor.x + (next_monitor.width - target_window.width) // 2
            new_y = next_monitor.y + (next_monitor.height - target_window.height) // 2
            target_window.moveTo(new_x, new_y)

        elif command in ["snap_left", "snap_right", "toggle_snap_left_right"]:
            if target_window.isMaximized:
                target_window.restore()
                time.sleep(0.1)

            new_width = target_monitor.width // 2
            new_height = target_monitor.height
            new_y = target_monitor.y
            snap_to = command

            if command == "toggle_snap_left_right":
                window_key = target_window.title
                last_state = WINDOW_SNAP_STATES.get(window_key)
                if last_state == "left":
                    snap_to = "right"
                else:
                    snap_to = "left"
                WINDOW_SNAP_STATES[window_key] = snap_to
            
            if snap_to == "left":
                new_x = current_monitor.x
            else:
                new_x = current_monitor.x + new_width
            
            target_window.resizeTo(new_width, new_height)
            target_window.moveTo(new_x, new_y)

        elif command == "minimize_others":
            all_windows = gw.getWindowsWithTitle('')
            for window in all_windows:
                if window != target_window and window.isVisible and not window.isMinimized:
                    window.minimize()

        return None
    except Exception as e:
        traceback.print_exc()
        return e


def execute_smart_open(payload):
    """
    If the app is running, focus it. Otherwise, execute it.
    Supports 'launch | process | title' syntax for complex/localized apps.
    """
    if not payload or not isinstance(payload, str):
        return ValueError("Smart Open action requires an executable path/name in the payload.")

    parts = [p.strip() for p in payload.split('|')]
    launch_command = parts[0]
    process_name = os.path.basename(parts[1] if len(parts) > 1 and parts[1] else launch_command).lower()
    window_title = parts[2] if len(parts) > 2 and parts[2] else None

    is_running = False

    # Check if the target process is running
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'].lower() == process_name:
                is_running = True
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # if it is running, find and focus its window
    if is_running:
        log.info(f"'{process_name}' is running. Attempting to focus window.")
        target_window = None
        try:
            if window_title:
                # If a title is provided, trust it. This is the best method for UWP apps. (calc.exe)
                # It finds any window containing the title text.
                matching_windows = gw.getWindowsWithTitle(window_title)
                if matching_windows:
                    target_window = matching_windows[0]
            else:
                # If no title is given, fall back to the old method of matching the process owner.
                # This works well for traditional apps like notepad.exe.
                for window in gw.getAllWindows():
                    if not window.visible or not window.title: continue
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(window._hWnd)
                        if psutil.Process(pid).name().lower() == process_name:
                            target_window = window
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied, pywintypes.error):
                        continue
            
            if target_window:
                if target_window.isMinimized:
                    target_window.restore()
                # Use the alt-key trick to reliably steal focus
                keyboard.press(Key.alt)
                keyboard.release(Key.alt)
                time.sleep(0.05)
                win32gui.SetForegroundWindow(target_window._hWnd)
            else:
                log.warning(f"Process '{process_name}' is running but no matching window was found. Launching a new instance.")
                subprocess.Popen(launch_command, shell=True)
        except Exception as e:
            log.error(f"Error while trying to focus '{process_name}': {e}")
            return e

    # If it is not running, execute the launch_command
    else:
        log.info(f"'{process_name}' is not running. Executing: {launch_command}")
        try:
            subprocess.Popen(launch_command, shell=True)
        except Exception as e:
            log.error(f"Error while trying to execute '{launch_command}': {e}")
            return e
            
    return None


def execute_insert_text(payload):
    """
    Temporarily places text on the clipboard, pastes it, and restores the original clipboard.
    """        
    original_clipboard = ""
    try:
        original_clipboard = ClipboardManager.get_clipboard()
        content = str(payload or "")
        ClipboardManager.set_clipboard(content)
        time.sleep(0.1)
        
        execute_hotkey("ctrl+v")
        time.sleep(0.1)

    except Exception as e:
        log.error(f"Error during 'Insert Text' action: {e}")
        return e
    finally:
        try:
            ClipboardManager.set_clipboard(original_clipboard)
        except Exception as e:
            log.warning(f"Could not restore original clipboard content: {e}")
    
    return None


def execute_action(action_type, payload, deck_info=None):
    """Executes a defined action based on its type and payload."""
    print(f"  - Executing: Action='{action_type}', Payload='{payload}'")
    try:
        if sys.platform == "win32":
            if action_type == "media_play_pause":
                _send_media_key(VK_MEDIA_PLAY_PAUSE)
                return None
            elif action_type == "media_next":
                _send_media_key(VK_MEDIA_NEXT_TRACK)
                return None
            elif action_type == "media_previous":
                _send_media_key(VK_MEDIA_PREV_TRACK)
                return None
            elif action_type == "media_stop":
                _send_media_key(VK_MEDIA_STOP)
                return None

        if action_type == "set_audio_device":
            error_message = set_default_audio_device(payload)
            if error_message:
                return ValueError(error_message)
        elif action_type == "media_play_pause" and sys.platform != "win32":
            keyboard.tap(Key.media_play_pause)
        elif action_type == "media_next" and sys.platform != "win32":
            keyboard.tap(Key.media_next)
        elif action_type == "media_previous" and sys.platform != "win32":
            keyboard.tap(Key.media_previous)
        elif action_type == "media_stop" and sys.platform != "win32":
            keyboard.tap(Key.media_stop)
        elif action_type == "execute":
            subprocess.Popen(payload, shell=True)
        elif action_type == "write":
            time.sleep(0.1)
            keyboard.type(str(payload))
        elif action_type == "hotkey":
            time.sleep(0.1)
            return execute_hotkey(payload)
        elif action_type == "insert_text":
            return execute_insert_text(payload)
        elif action_type == "delay":
            time.sleep(float(payload))
        elif action_type == "window_management":
            return execute_window_action(payload)
        elif action_type == "http_request":
            return execute_http_request(payload)
        elif action_type == "key_press":
            key_obj = _get_pynput_key(payload)
            keyboard.press(key_obj)
        elif action_type == "key_release":
            key_obj = _get_pynput_key(payload)
            keyboard.release(key_obj)
        elif action_type == "mouse_move":
            mouse.position = (payload['x'], payload['y'])
        elif action_type == "mouse_click":
            # Move mouse to position before clicking
            mouse.position = (payload['x'], payload['y'])
            time.sleep(0.05) # Small delay to ensure mouse is in position
            button = getattr(Button, payload['button'])
            if payload['pressed']:
                mouse.press(button)
            else:
                mouse.release(button)
        elif action_type == "mouse_scroll":
            mouse.scroll(payload['dx'], payload['dy'])
        elif action_type == "volume_up":
            return volume_up(payload)
        elif action_type == "volume_down":
            return volume_down(payload)
        elif action_type == "toggle_mute":
            return toggle_mute()
        elif action_type == "cycle_windows":
            return execute_cycle_windows(payload)
        elif action_type == "command_cycle":
            if not deck_info:
                return ValueError("Command Cycle requires deck_info.")
            
            current_key_info = (deck_info['deck_id'], deck_info['key_index'])
            
            # If the window is not open, open it
            if not CMD_CYCLE_MANAGER.is_active:
                CMD_CYCLE_MANAGER.start(payload, current_key_info)
            # If the window is open AND the same key was pressed, cycle the selection
            elif CMD_CYCLE_MANAGER.trigger_key_info == current_key_info:
                CMD_CYCLE_MANAGER.cycle()
            # If a different key was pressed, do nothing
            return None
        elif action_type == "clipboard_history":
            if not deck_info:
                return ValueError("Clipboard History requires deck_info.")
            
            current_key_info = (deck_info['deck_id'], deck_info['key_index'])

            if not CLIPBOARD_MANAGER.is_active:
                CLIPBOARD_MANAGER.start(current_key_info)
            elif CLIPBOARD_MANAGER.trigger_key_info == current_key_info:
                CLIPBOARD_MANAGER.cycle()
            return None
        elif action_type == "smart_open":
            return execute_smart_open(payload)
        return None
    except Exception as e:
        print(f"Error executing action '{action_type}': {e}")
        traceback.print_exc()
        return e