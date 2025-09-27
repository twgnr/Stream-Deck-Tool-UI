#--------------------------------------------------------------------
# Import packages
#--------------------------------------------------------------------
import threading

#--------------------------------------------------------------------
# Import sub-packages
#--------------------------------------------------------------------
from StreamDeck.DeviceManager import DeviceManager

#--------------------------------------------------------------------
# Import local modules
#--------------------------------------------------------------------
from config_manager import load_config, log, setup_logging
from deck_driver import DeckDriver
from profile_monitor import profile_monitor_loop, CONTEXT_AWARE_ENABLED
from hot_reloader import start_reloader
from dynamic_keys import start_dynamic_key_updater

def main():
    """Initializes and runs the Stream Deck driver for all connected devices."""
    full_config = load_config()
    setup_logging(full_config)
    streamdecks = DeviceManager().enumerate()

    if not streamdecks:
        log.error("No Stream Deck found.")
        return

    drivers = []
    reloader_drivers = [] # List of drivers that have hot-reloading enabled
    shutdown_event = threading.Event()

    for deck in streamdecks:
        deck.open()
        deck.reset()

        log.info(f"Opened '{deck.deck_type()}' device ({deck.id()}).")
        deck.set_brightness(30)
        
        # Initialize driver with the full config; it will find its own slice.
        driver = DeckDriver(deck, full_config, shutdown_event)
        drivers.append(driver)
        
        deck.set_key_callback(driver.key_change_callback)
        driver.draw_layer("main")

        # Check if this specific deck should be included in the hot reloader
        if driver.config.get("settings", {}).get("hot_reload_enabled", False):
            reloader_drivers.append(driver)

    # --- Start Global Services After All Decks are Initialized ---

    # Start the context-aware profile monitor if ANY deck has it enabled
    any_deck_has_context_aware = any(
        d.config.get("context_aware_profiles", {}).get("enabled", False) for d in drivers
    )
    if CONTEXT_AWARE_ENABLED and any_deck_has_context_aware:
        monitor_thread = threading.Thread(target=profile_monitor_loop, args=(drivers,), daemon=True)
        monitor_thread.start()
        log.info("Context-aware profile monitor started for all detected devices.")

    # Start the hot-reloader if ANY deck has it enabled in its config
    if reloader_drivers:
        reloader_observer = start_reloader(reloader_drivers)

    # Start the dynamic key updater thread for all drivers
    start_dynamic_key_updater(drivers)
    
    try:
        log.info(f"Application started for {len(drivers)} device(s). Press Ctrl+C to quit.")
        shutdown_event.wait()
    except KeyboardInterrupt:
        log.info("Caught KeyboardInterrupt. Shutting down.")
    finally:
        log.info("Cleaning up resources...")
        if 'reloader_observer' in locals() and reloader_observer.is_alive():
            reloader_observer.stop()
            reloader_observer.join()
        
        for deck in streamdecks:
            deck.reset()
            deck.close()
        log.info("Application terminated cleanly.")


if __name__ == "__main__":
    main()