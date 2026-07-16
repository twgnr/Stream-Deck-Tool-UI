#--------------------------------------------------------------------
# Import packages
#--------------------------------------------------------------------
import os
import threading
import time
import psutil

#--------------------------------------------------------------------
# Import sub-packages
#--------------------------------------------------------------------
from datetime import datetime
from PIL import Image
from StreamDeck.ImageHelpers import PILHelper

#--------------------------------------------------------------------
# Import local modules
#--------------------------------------------------------------------
from rendering import render_key_image
from config_manager import log
from data_providers import PROVIDER_MAP, gpu_monitor

#--------------------------------------------------------------------
# Data provider
#--------------------------------------------------------------------
def get_clock_data():
    """Returns the current time as a string."""
    return datetime.now().strftime("%H:%M:%S")

def get_cpu_usage_data():
    """Returns the current CPU usage as a percentage string."""
    return f"{psutil.cpu_percent():.0f}%"

# Mapping of provider names in config.json to their functions
DATA_PROVIDERS = {
    "clock": get_clock_data,
    "cpu_usage": get_cpu_usage_data,
}
UI_DATA_CACHE = {}


def updater_loop(driver_instances, shutdown_event=None):
    """
    The main loop that runs in a background thread to update dynamic and animated keys
    across ALL connected Stream Decks. `driver_instances` may be a shared list that
    is mutated at runtime when decks are plugged in or unplugged.
    """
    if shutdown_event is None:
        if not driver_instances:
            log.warning("Dynamic key updater started with no drivers.")
            return
        shutdown_event = driver_instances[0].shutdown_event

    while not shutdown_event.is_set():
        try:
            now = time.time()

            for driver in list(driver_instances):
                with driver.state_lock:
                    active_keys = list(driver.active_dynamic_keys)
                    current_layer = driver.current_layer

                for key_index, key_config in active_keys:
                    if shutdown_event.is_set():
                        break

                    display_config = key_config.get("display", {})
                    display_type = display_config.get("type")

                    if display_type == "animated":
                        icon_name = key_config.get("icon", "")
                        icon_path = os.path.join(driver.icon_folder, icon_name) if icon_name else ""
                        if icon_path in driver.gif_cache:
                            gif = driver.gif_cache[icon_path]
                            
                            gif["frame_index"] = (gif["frame_index"] + 1) % len(gif["frames"])
                            frame_image = gif["frames"][gif["frame_index"]]

                            image_format = driver.deck.key_image_format()
                            image = Image.new("RGB", image_format['size'], "black")
                            image.paste(frame_image, (0, 0), frame_image)
                            
                            native_image = PILHelper.to_native_format(driver.deck, image)
                            driver.deck.set_key_image(key_index, native_image)

                    elif display_type == "dynamic":
                        interval = display_config.get("update_interval", 5.0)
                        
                        if now - driver.dynamic_key_last_updates.get(key_index, 0) > interval:
                            provider_name = display_config.get("provider")
                            provider_func = PROVIDER_MAP.get(provider_name)
                            
                            if provider_func:
                                try:
                                    options = display_config.get("provider_options", {})
                                    dta = provider_func(**options)
                                    label_text = dta.get("text", "Error")
                                    
                                    cache_key = (driver.deck_id, current_layer, key_index)
                                    UI_DATA_CACHE[cache_key] = label_text

                                    font_settings = key_config.get("font_settings", {})
                                    font_color = key_config.get("font_color", "white")
                                    label_pos = key_config.get("label_pos", "bottom")

                                    action_type = key_config.get("action_type")
                                    is_layer_key = (action_type == "layer")
                                    is_active_toggle = False
                                    if action_type == "toggle_key":
                                        state_key = (driver.deck.id(), key_index)
                                        if state_key in driver.toggled_keys:
                                            is_active_toggle = True

                                    background_color = key_config.get("background", "#000000")

                                    image = render_key_image(
                                        driver.deck, "", label_text, driver.icon_folder, driver.font_path,
                                        driver.font_size, label_pos_config=label_pos,
                                        font_color=font_color, font_settings=font_settings,
                                        background_color=background_color,
                                        is_layer_key=is_layer_key,
                                        is_active_toggle=is_active_toggle
                                    )
                                    driver.deck.set_key_image(key_index, image)
                                    driver.dynamic_key_last_updates[key_index] = now
                                except Exception as e:
                                    log.error(f"Error updating dynamic key {key_index} on deck {driver.deck.id()}: {e}")

                if shutdown_event.is_set():
                    break
            
            time.sleep(0.1)

        except Exception as e:
            log.error(f"Error in dynamic key updater thread: {e}")
            shutdown_event.wait(5)

    log.info("Updater loop is shutting down...")
    gpu_monitor.shutdown()


def start_dynamic_key_updater(driver_instances, shutdown_event=None):
    """Starts the background thread to update dynamic keys."""
    if not isinstance(driver_instances, list):
        driver_instances = [driver_instances]
    update_thread = threading.Thread(target=updater_loop, args=(driver_instances, shutdown_event), daemon=True)
    update_thread.start()


def dynamic_key_update_loop(driver):
    """The main loop that periodically updates dynamic keys."""
    while not driver.shutdown_event.is_set():
        current_time = time.time()
        active_keys_on_layer = [k for k in driver.active_dynamic_keys if k[1].get('display')]
        
        for key_index, key_config in active_keys_on_layer:
            display_config = key_config.get("display", {})
            provider_name = display_config.get("provider")

            last_update = driver.dynamic_key_last_updates.get(key_index, 0)
            update_interval = display_config.get("update_interval", 1.0)

            if (current_time - last_update) > update_interval:
                if provider_name in PROVIDER_MAP:
                    provider_func = PROVIDER_MAP[provider_name]
                    options = display_config.get("provider_options", {})

                    current_deck_layer = driver.current_layer
                    cache_key = (current_deck_layer, key_index)

                    try:
                        # Call the provider, passing options if they exist (for disk_space)
                        dta = provider_func(**options)
                        label_text = dta.get("text", "Error")
                        
                        UI_DATA_CACHE[cache_key] = label_text

                        # Use the keys main config as a base for visuals
                        font_settings = key_config.get("font_settings", {})
                        font_color = key_config.get("font_color", "white")
                        label_pos = key_config.get("label_pos", "bottom")
                        
                        # Here you could add logic to change color based on dta['percent']
                        
                        image = render_key_image(
                            driver.deck, "", label_text, driver.icon_folder, driver.font_path,
                            driver.font_size, label_pos_config=label_pos,
                            font_color=font_color, font_settings=font_settings
                        )
                        driver.deck.set_key_image(key_index, image)
                        driver.dynamic_key_last_updates[key_index] = current_time
                    except Exception as e:
                        if cache_key in UI_DATA_CACHE:
                            del UI_DATA_CACHE[cache_key]
                        print(f"Error updating dynamic key {key_index} with provider '{provider_name}': {e}")

        time.sleep(0.5)
    
    # Cleanly shut down the NVML library when the app exits
    gpu_monitor.shutdown()