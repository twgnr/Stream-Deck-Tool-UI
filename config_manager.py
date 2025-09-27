#--------------------------------------------------------------------
# Import packages
#--------------------------------------------------------------------
import json
import sys
import os
import logging

#--------------------------------------------------------------------
# Import sub-packages
#--------------------------------------------------------------------
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass

# -------------------------
# Logging Setup
# -------------------------
log = logging.getLogger("StreamDeckTool")
log.setLevel(logging.INFO)

# Set up the console/stream logger immediately.
# This ensures that startup messages are always visible.
if not log.handlers:
    stream_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    stream_handler.setFormatter(formatter)
    log.addHandler(stream_handler)


def get_base_path():
    """Gets the base path for the application, working for both script and frozen exe."""
    if getattr(sys, 'frozen', False):
        # If the application is run as a bundle (PyInstaller)
        return os.path.dirname(sys.executable)
    else:
        # If run as a normal script
        return os.path.dirname(os.path.abspath(__file__))
    
BASEPATH = get_base_path()
ICON_FOLDER = os.path.join(BASEPATH, "icons")
FONT_PATH = "C:/Windows/Fonts/Arial.ttf"
CONFIG_FILE_NAME = "config.json"
CONFIG_FILE = os.path.join(BASEPATH, CONFIG_FILE_NAME)


# Sets up file logging based on the loaded config.
def setup_logging(full_config):
    """Configures file logging if enabled in any device's settings."""
    log_enabled = False
    if isinstance(full_config, dict):
        for deck_id, deck_config in full_config.items():
            if deck_config.get("settings", {}).get("log_to_file", False):
                log_enabled = True
                break

    if log_enabled:
        # Check if a file handler already exists to prevent duplicates.
        if any(isinstance(h, logging.FileHandler) for h in log.handlers):
            return

        log_file_path = os.path.join(BASEPATH, "streamdeck_tool.log")
        
        # Use a rotating log file to prevent it from growing too large.
        # This will create a 5MB log file and keep up to 3 backup files.
        file_handler = RotatingFileHandler(
            log_file_path, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8'
        )
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        log.addHandler(file_handler)
        log.info(f"File logging is enabled. Outputting to: {log_file_path}")


#--------------------------------------------------------------------
# Class
#--------------------------------------------------------------------
class AppSettings:
    """Holds dynamic application settings loaded from config.json."""
    def __init__(self):
        self.DEFAULT_KEY_SIZE = 75
        self.DOUBLE_CLICK_DELAY_MS = 300


    def load_from_dict(self, config_dta: dict):
        """Loads settings from the 'settings' key of the config dictionary."""
        settings = config_dta.get("settings", {})
        self.DEFAULT_KEY_SIZE = settings.get("default_key_size", self.DEFAULT_KEY_SIZE)
        self.DOUBLE_CLICK_DELAY_MS = settings.get("double_click_delay_ms", self.DOUBLE_CLICK_DELAY_MS)

# Create a single global instance that the app will use
app_settings = AppSettings()

@dataclass
class KeyConfig:
    """Represents the configuration for a single key."""
    label: str = ""
    icon: str = ""
    action_type: str = "execute"
    payload: object = ""
    label_pos: str = "bottom"
    display: dict = None


def load_config():
    """Loads the entire configuration from the JSON file."""

    if not os.path.exists(CONFIG_FILE):
        return {"main": {}}
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            dta = json.load(f)
            if dta:
                first_deck_id = next(iter(dta))
                app_settings.load_from_dict(dta[first_deck_id])
            return dta
    except FileNotFoundError:
        print(f"FATAL: Configuration file '{CONFIG_FILE}' not found. Please create it.")
        sys.exit(1)
    except (json.JSONDecodeError, StopIteration) as e:
        print(f"FATAL: Could not decode or parse '{CONFIG_FILE}'. Please check syntax or ensure it's not empty: {e}")
        # Return a default structure to allow the app to start
        return {}


def save_config(config_dta):
    """Saves the provided configuration data to the JSON file."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_dta, f, indent=4, ensure_ascii=False)
    except IOError as e:
        raise e
    

def generate_layer_name(config_dta, desired_name, original_name=None):
    """
    Generates a unique layer name based on a desired name.
    If the desired_name is taken, it appends a counter (_1, _2, etc.).

    Args:
        config_dta (dict): The full configuration dictionary.
        desired_name (str): The requested name for the layer.
        original_name (str, optional): The original name if renaming. This allows
                                       saving a layer with its own name without error.

    Returns:
        str: A unique layer name.
    """
    # Renaming but the name has not changed, its a valid operation.
    if desired_name == original_name:
        return desired_name

    # Check if the desired name is already in use by another layer.
    if desired_name not in config_dta:
        return desired_name

    # If it is, find a unique alternative by appending a counter.
    counter = 1
    while True:
        new_name = f"{desired_name}_{counter}"
        if new_name not in config_dta:
            return new_name
        counter += 1