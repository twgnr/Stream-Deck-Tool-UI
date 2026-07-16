#--------------------------------------------------------------------
# Import packages
#--------------------------------------------------------------------
import time

#--------------------------------------------------------------------
# Import sub-packages
#--------------------------------------------------------------------
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

#--------------------------------------------------------------------
# Import local modules
#--------------------------------------------------------------------
from config_manager import CONFIG_FILE, CONFIG_FILE_NAME, BASEPATH,log

class ConfigChangeHandler(FileSystemEventHandler):
    """Handles the event when the config file is modified."""
    def __init__(self, driver_instances):
        self.drivers = driver_instances 
        self.last_triggered = 0
        self.log = log


    def on_modified(self, event):
        # Ignore directory events and focus on the specific config file
        if not event.is_directory and event.src_path.endswith(CONFIG_FILE_NAME):
            # Debounce the event to avoid multiple triggers on a single save
            current_time = time.time()
            if current_time - self.last_triggered > 1:
                self.last_triggered = current_time
                self.log.info(f"Detected change in '{CONFIG_FILE}'. Triggering hot-reload.")
                # Copy: the shared driver list may be mutated on device hot-plug
                for driver in list(self.drivers):
                    driver.reload_config()


def start_reloader(driver_instance):
    """Starts the watchdog observer in a separate thread."""
    event_handler = ConfigChangeHandler(driver_instance)
    observer = Observer()
    # Watch the current directory for changes to the config file
    observer.schedule(event_handler, path=BASEPATH, recursive=False)
    observer.start()
    log.info("Configuration hot-reloader started.")
    return observer