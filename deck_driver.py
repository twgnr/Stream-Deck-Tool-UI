#--------------------------------------------------------------------
# Import sub-packages
#--------------------------------------------------------------------
import threading
import os

#--------------------------------------------------------------------
# Import sub-packages
#--------------------------------------------------------------------
from PIL import Image, ImageSequence
from StreamDeck.ImageHelpers import PILHelper

#--------------------------------------------------------------------
# Import local modules
#--------------------------------------------------------------------
from rendering import render_key_image, get_blank_key_image, render_error_key
from action_handler import execute_action
from config_manager import load_config, BASEPATH, log, setup_logging

#--------------------------------------------------------------------
# Class
#--------------------------------------------------------------------
class DeckDriver:
    def __init__(self, deck, full_config, shutdown_event, ui_refresh_callback=None, layer_change_callback=None, ui_visual_refresh_callback=None):
        self.deck = deck
        self.deck_id = deck.id()
        self.full_config = full_config
        self.config = self.full_config.setdefault(self.deck_id, {"main": {}})
        
        self.log = log
        self.shutdown_event = shutdown_event
        self.ui_refresh_callback = ui_refresh_callback                  # Callback to refresh the UI (data provider etc.)
        self.layer_change_callback = layer_change_callback              # Callback for layer changes
        self.ui_visual_refresh_callback = ui_visual_refresh_callback    # Callback for live key visual refreshes
        self.key_states = {}
        self.sequence_states = {}
        self.current_layer = "main"
        self.context_layer = "main"
        self.layer_history = []
        
        # State for dynamic and animated keys
        self.gif_cache = {}
        self.active_dynamic_keys = []
        self.dynamic_key_last_updates = {}
        
        # State for Press-and-Hold functionality
        self.key_press_timers = {}
        self.key_hold_triggered = set()
        self.toggled_keys = set()
        self.timed_toggles = {}

        # Protects shared state (config, gif_cache, active_dynamic_keys, current_layer)
        # against the watchdog hot-reloader, the dynamic-key updater thread, and
        # the deck's own key-callback thread.
        self.state_lock = threading.RLock()

        self._update_settings()


    def _update_settings(self):
        settings = self.config.get("settings", {})
        self.icon_folder = os.path.join(BASEPATH, settings.get("icon_folder", "icons"))
        self.font_path = settings.get("font_path", "C:/Windows/Fonts/Arial.ttf")
        self.font_size = settings.get("font_size", 14)
        self.hold_duration = settings.get("hold_duration_seconds", 0.7)
        self.log.info(f"Assets loaded: Icons='{self.icon_folder}', Font='{self.font_path}'")
        self.log.info(f"Hold duration set to {self.hold_duration} seconds.")


    def key_change_callback(self, deck, key, state):
        """Main event handler, now with press-and-hold logic."""
        key_config = self.config.get(self.current_layer, {}).get(str(key))
        if not key_config:
            return

        if state: # Key Down
            hold_action_config = key_config.get("hold_action")
            if not hold_action_config:
                # No hold action, execute immediately on press
                self._start_action_thread(key, key_config)
                return

            # Start timer to check for a hold status
            timer = threading.Timer(self.hold_duration, self._trigger_hold_action, args=[key, hold_action_config])
            timer.daemon = True
            self.key_press_timers[key] = timer
            timer.start()

        else: # Key Up
            # Check if a hold action has already been triggered for this key
            if key in self.key_hold_triggered:
                self.key_hold_triggered.remove(key)
                return

            # If a timer is present, hold duration was not reached
            if key in self.key_press_timers:
                timer = self.key_press_timers.pop(key)
                timer.cancel()
                self._start_action_thread(key, key_config)


    def _trigger_hold_action(self, key_index, hold_action_config):
        """Callback for the timer, executes the hold action."""
        self.log.info(f"Key Hold: {key_index}, Layer: '{self.current_layer}'")
        self.key_hold_triggered.add(key_index)
        self.key_press_timers.pop(key_index, None)
        
        # The hold action has its own config, but use the parent keys index
        self._start_action_thread(key_index, hold_action_config)


    def _start_action_thread(self, key_index, key_config, deck_info=None):
        """Starts a new thread to execute an action, to avoid blocking the main loop."""
        if not deck_info:
            deck_info = {"deck_id": self.deck_id, "key_index": key_index}
        log.info(f"Key Press: {key_index}, Layer: '{self.current_layer}', Action: '{key_config.get('action_type')}'")
        action_thread = threading.Thread(target=self._execute_action_logic, args=(key_index, key_config, deck_info))
        action_thread.start()


    def execute_key_action(self, key_index):
        """Finds the configuration for a given key and executes its primary action."""
        self.log.info(f"Executing action for key {key_index} on layer '{self.current_layer}' (triggered by UI).")
        key_config = self.config.get(self.current_layer, {}).get(str(key_index))
        
        if not key_config or not key_config.get("action_type"):
            self.log.warning(f"No action configured for key {key_index} on layer '{self.current_layer}'.")
            return
            
        # Reuse the existing threaded action logic to prevent UI freezes
        deck_info = {"deck_id": self.deck_id, "key_index": key_index}
        self._start_action_thread(key_index, key_config, deck_info=deck_info)


    def _execute_action_logic(self, key_index, key_config, deck_info):
        """The actual logic for executing any action, called by the action thread."""
        action_type = key_config.get("action_type")
        payload = key_config.get("payload")
        error = None

        if action_type == "toggle_key":
            state_key = (self.deck.id(), key_index)
            # If the key is already on, turn it off
            if state_key in self.toggled_keys:
                log.info(f"Toggling key OFF: {key_index} ({payload})")
                error = execute_action("key_release", payload)
                self.toggled_keys.remove(state_key)
            # If the key is off, turn it on
            else:
                log.info(f"Toggling key ON: {key_index} ({payload})")
                error = execute_action("key_press", payload)
                self.toggled_keys.add(state_key)
            
            self.update_key_visuals(key_index)
            if self.ui_visual_refresh_callback:
                self.ui_visual_refresh_callback()

        elif action_type == "toggle_key_timer":
            state_key = (self.deck.id(), key_index)
            
            # Parse payload into hold and tap keys
            parts = [p.strip() for p in str(payload).split('|')]
            if len(parts) < 2:
                log.error(f"Invalid payload for toggle_key_timer: '{payload}'. Must be 'hold_key | tap_key'.")
                return

            hold_key = parts[0]
            tap_keys = parts[1:]

            # If the key is already active, tap and reset the timer
            if state_key in self.timed_toggles:
                log.info(f"Cycling timed toggle: {key_index}")
                timer = self.timed_toggles.pop(state_key)
                timer.cancel()
                for key in tap_keys:
                    error = execute_action("hotkey", key)

            else:
                log.info(f"Activating timed toggle: {key_index}")
                error = execute_action("key_press", hold_key)
                for key in tap_keys:
                    error = execute_action("hotkey", key)

            new_timer = threading.Timer(2.0, self._deactivate_timed_toggle, args=[state_key, hold_key])
            new_timer.daemon = True
            self.timed_toggles[state_key] = new_timer
            new_timer.start()

            self.update_key_visuals(key_index) # Update hardware visual
            if self.ui_visual_refresh_callback:
                self.ui_visual_refresh_callback() # Update UI visual


        elif action_type == "exit":
            self.log.info("Exit action triggered. Signaling application to shut down.")
            self.shutdown_event.set()
            return
        elif action_type == "layer":
            target_layer = None
            # Check if the payload is a dictionary (new format) or string (old format)
            if isinstance(payload, dict):
                target_layer = payload.get("target")
                second_action = payload.get("secondary_action")
                if second_action and second_action.get("action_type"):
                    log.info(f"  - Executing secondary action: {second_action.get('action_type')}")
                    # Execute the secondary action first. (recursive call)
                    execute_action(
                        second_action.get("action_type"),
                        second_action.get("payload"),
                        deck_info=deck_info
                    )
            else:
                target_layer = payload

            if target_layer:
                self.change_layer_forward(target_layer)
            else:
                error = ValueError("Layer action has no target layer specified.")

        elif action_type == "back":
            if self.layer_history:
                self.change_layer_back()

            elif self.current_layer != "main":
                self.draw_layer("main")

        elif action_type == "jump_to_layer":
            self.jump_to_layer(payload)

        elif action_type == "back_to_main":
            self.jump_to_layer("main")

        elif action_type == "multi-action":
            for action in payload:
                err = execute_action(action.get("action_type"), action.get("payload"))
                if err:
                    error = err
                    break

        elif action_type == "sequence":
            if not isinstance(payload, list) or not payload:
                error = ValueError("Sequence payload is not a valid list of actions.")
            else:
                state_key = (self.current_layer, key_index)
                
                # Get the current step for this key, defaulting to 0 if not found
                step_index = self.sequence_states.get(state_key, 0)
                action_to_run = payload[step_index]
                error = execute_action(action_to_run.get("action_type"), action_to_run.get("payload"))
                
                if not error:
                    # calculate the next step, looping back to the start
                    next_step = (step_index + 1) % len(payload)
                    self.sequence_states[state_key] = next_step

        elif action_type == "toggle_state":
            state_key = (self.current_layer, key_index)
            state_index = self.key_states.get(state_key, 0)

            if isinstance(payload, list) and len(payload) > state_index:
                state_config = payload[state_index]
                action_to_run = state_config.get("action", {})
                error = execute_action(action_to_run.get("action_type"), action_to_run.get("payload"))

                if not error:
                    self.key_states[state_key] = (state_index + 1) % len(payload)
                    self.update_key_visuals(key_index)
            else:
                error = ValueError("Toggle state out of bounds")
        else:
            # Pass the deck_info
            error = execute_action(action_type, payload, deck_info=deck_info)

        if error:
            self.log.error(f"Action Error: {error}")
            self._flash_error_on_key(key_index)


    def _deactivate_timed_toggle(self, state_key, hold_key):
        """Callback for the timer to release the held key and update visuals."""
        log.info(f"Timed toggle deactivating for key: {state_key[1]}")
        if state_key in self.timed_toggles:
            self.timed_toggles.pop(state_key)
        
        execute_action("key_release", hold_key)
        
        # Refresh visuals on both hardware and UI
        self.update_key_visuals(state_key[1])
        if self.ui_visual_refresh_callback:
            self.ui_visual_refresh_callback()


    def _load_gif(self, icon_path):
        if icon_path in self.gif_cache: return
        try:
            self.log.info(f"  - Loading GIF: {icon_path}")
            gif_image = Image.open(icon_path)
            frames = [frame.convert("RGBA") for frame in ImageSequence.Iterator(gif_image)]
            self.gif_cache[icon_path] = {"frames": frames, "frame_index": 0}
        except Exception as e:
            self.log.warning(f"Could not load GIF '{icon_path}'. Error: {e}")


    def change_layer_forward(self, new_layer):
        """Navigates to a new layer and saves the history. Called by hardware or UI."""
        if new_layer in self.config:
            self.layer_history.append(self.current_layer)
            self.draw_layer(new_layer)

    def change_layer_back(self):
        """Navigates back one layer in the history. Called by hardware or UI."""
        if self.layer_history:
            self.draw_layer(self.layer_history.pop())
        elif self.current_layer != "main":
             self.draw_layer("main")

    def jump_to_layer(self, new_layer):
        """Jumps to a layer, clearing history. Called by the UI sidebar."""
        if new_layer in self.config:
            self.layer_history.clear()
            self.draw_layer(new_layer)

    def draw_layer(self, layer_name):
        with self.state_lock:
            if layer_name not in self.config:
                self.log.warning(f"Layer '{layer_name}' no longer exists. Switching to main layer.")
                layer_name = "main"

            self.log.info(f"Switching to layer: '{layer_name}'")
            self.current_layer = layer_name
            self.active_dynamic_keys.clear()
            self.dynamic_key_last_updates.clear()
            layer_config = self.config.get(layer_name, {})

            for key_index in range(self.deck.key_count()):
                key_config = layer_config.get(str(key_index))
                self.update_key_visuals(key_index)

                if key_config:
                    display_config = key_config.get("display")
                    if display_config:
                        display_type = display_config.get("type")
                        if display_type == "animated" and key_config.get("icon", "").endswith(".gif"):
                            icon_path = os.path.join(self.icon_folder, key_config["icon"])
                            self._load_gif(icon_path)
                            self.active_dynamic_keys.append((key_index, key_config))
                        elif display_type == "dynamic":
                            self.active_dynamic_keys.append((key_index, key_config))

            history_snapshot = self.layer_history.copy()
            current_layer = self.current_layer

        if self.layer_change_callback:
            self.layer_change_callback(self.deck_id, current_layer, history_snapshot)


    def update_key_visuals(self, key_index):
        key_config = self.config.get(self.current_layer, {}).get(str(key_index))
        if not key_config:
            self.deck.set_key_image(key_index, get_blank_key_image(self.deck))
            return
        
        font_settings = key_config.get("font_settings", {})
        icon_name = key_config.get("icon", "")
        label_text = key_config.get("label", "")
        action_type = key_config.get("action_type")
        display_type = key_config.get("display", {}).get("type")
        font_color = key_config.get("font_color", "white")
        label_pos = key_config.get("label_pos", "bottom")

        if action_type == "toggle_state":
            states = key_config.get("payload", [])
            if isinstance(states, list) and states:
                state_index = self.key_states.get((self.current_layer, key_index), 0) % len(states)
                state_config = states[state_index]
                icon_name = state_config.get("icon", icon_name)
                label_text = state_config.get("label", label_text)
                label_pos = state_config.get("label_pos", label_pos)
                font_color = state_config.get("font_color", font_color)
                font_settings = state_config.get("font_settings", font_settings)

        background_color = key_config.get("background", "#2A446F")
        is_layer_key = (action_type == "layer")

        is_active_toggle = False
        if action_type in ["toggle_key", "toggle_key_timer"]:
            state_key = (self.deck.id(), key_index)
            if state_key in self.toggled_keys or state_key in self.timed_toggles:
                is_active_toggle = True

        if display_type == "animated" and icon_name.endswith(".gif"):
            icon_path = os.path.join(self.icon_folder, icon_name)
            if icon_path in self.gif_cache:
                frame_image = self.gif_cache[icon_path]["frames"][0]
                image_format = self.deck.key_image_format()
                image = Image.new("RGB", image_format['size'], background_color)
                image.paste(frame_image, (0,0), frame_image)
                native_image = PILHelper.to_native_format(self.deck, image)
                self.deck.set_key_image(key_index, native_image)
            else:
                self.deck.set_key_image(key_index, render_error_key(self.deck, "GIF?"))
        else:
            image = render_key_image(self.deck, 
                                     icon_name, 
                                     label_text, 
                                     self.icon_folder, 
                                     self.font_path, 
                                     self.font_size, 
                                     label_pos_config=label_pos, 
                                     font_color=font_color, 
                                     font_settings=font_settings, 
                                     background_color=background_color, 
                                     is_layer_key=is_layer_key,
                                     is_active_toggle=is_active_toggle
                                )
            self.deck.set_key_image(key_index, image)


    def reload_config(self):
        self.log.info(f"Hot-reloading configuration for deck {self.deck_id}...")
        try:
            new_full_config = load_config()
            setup_logging(new_full_config)
            with self.state_lock:
                self.full_config = new_full_config
                self.config = self.full_config.setdefault(self.deck_id, {"main": {}})
                self._update_settings()
                current_layer = self.current_layer

            if self.ui_refresh_callback:
                self.ui_refresh_callback(self.full_config)

            self.draw_layer(current_layer)
            self.log.info(f"Configuration for deck {self.deck_id} reloaded successfully.")
        except Exception as e:
            self.log.error(f"Error during hot-reload: {e}")


    def _flash_error_on_key(self, key_index):
        self.log.info(f"  - Flashing error on key {key_index}")
        error_image = render_error_key(self.deck)
        self.deck.set_key_image(key_index, error_image)
        revert_timer = threading.Timer(2.0, self.update_key_visuals, args=[key_index])
        revert_timer.daemon = True
        revert_timer.start()


    def set_context_layer(self, layer_name):
        """Sets the current layer as a result of an application context switch."""
        if self.current_layer == layer_name:
            return

        self.context_layer = layer_name
        self.layer_history = [self.current_layer]
        self.draw_layer(layer_name)