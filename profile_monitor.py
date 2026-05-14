#--------------------------------------------------------------------
# Import packages
#--------------------------------------------------------------------
import sys
import time

try:
    import psutil
    import pygetwindow as gw
    if sys.platform == "win32":
        import win32process
    CONTEXT_AWARE_ENABLED = True
except ImportError:
    CONTEXT_AWARE_ENABLED = False

#--------------------------------------------------------------------
# Import local packages
#--------------------------------------------------------------------
from config_manager import log

def is_sub_layer(config_dta, child_layer, god_layer):
    """
    Checks if a layer is a descendant of another layer by tracing parentage up the tree.
    """
    if child_layer == god_layer:
        return True
    
    current_layer = child_layer
    for _ in range(100):
        layer_config = config_dta.get(current_layer, {})
        parent = layer_config.get("parent")
        
        if not parent:
            return False # end reached
        
        if parent == god_layer:
            return True 
            
        current_layer = parent # next
        
    return False #Error 


def profile_monitor_loop(driver_instances):
    """
    Monitors the active window and switches layers only when the focused application changes,
    respecting sub-layers of a context profile.
    """
    if not CONTEXT_AWARE_ENABLED:
        log.warning("Context-aware dependencies not installed. Profile monitor disabled.")
        return

    if not driver_instances:
        return

    shutdown_event = driver_instances[0].shutdown_event
    last_active_process = None

    while not shutdown_event.is_set():
        current_active_process = None
        active_window = None
        try:
            active_window = gw.getActiveWindow()
            if active_window and sys.platform == "win32" and active_window.title:
                _, pid = win32process.GetWindowThreadProcessId(active_window._hWnd)
                current_active_process = psutil.Process(pid).name().lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied, gw.PyGetWindowException, AttributeError):
            current_active_process = None
            active_window = None
        
        if current_active_process != last_active_process:
            last_active_process = current_active_process

            for driver in driver_instances:
                profile_config = driver.config.get("context_aware_profiles", {})
                if not profile_config.get("enabled", False):
                    continue

                profiles = profile_config.get("profiles", {})
                profiles_lower = {exe.lower(): layer for exe, layer in profiles.items()}
                
                found_layer = profiles_lower.get(current_active_process)

                # If exe not found, check if any profile matches part of the window title.
                if not found_layer and active_window and active_window.title:
                    found_layer = next((v for k, v in profiles_lower.items() if k in active_window.title.lower()), None)


                if found_layer:
                    # An app with a profile is in focus. This is our target context.
                    target_layer = found_layer
                    
                    # Check if the user is already on the target layer OR one of its children.
                    is_already_active = is_sub_layer(
                        driver.config, driver.current_layer, target_layer
                    )
                    
                    if not is_already_active:
                        log.info(f"Context switch for deck '{driver.deck.id()}': App '{current_active_process}' -> Layer '{target_layer}'")
                        driver.set_context_layer(target_layer)
                else:
                    # An un-profiled app is in focus. Do nothing, leave the layer "sticky".
                    driver.context_layer = "main"
        
        time.sleep(1)


# def profile_monitor_loop(driver_instances):
#     """
#     Monitors the active window and switches layers only when a profiled app is focused.
#     The layer will remain "sticky" until another profiled app is focused.
#     """
#     if not CONTEXT_AWARE_ENABLED:
#         log.warning("Context-aware dependencies not installed. Profile monitor disabled.")
#         return

#     if not driver_instances:
#         return

#     shutdown_event = driver_instances[0].shutdown_event

#     while not shutdown_event.is_set():
#         active_process_name = None
#         try:
#             active_window = gw.getActiveWindow()
#             if active_window and sys.platform == "win32" and active_window.title:
#                 _, pid = win32process.GetWindowThreadProcessId(active_window._hWnd)
#                 active_process_name = psutil.Process(pid).name().lower()
#         except (psutil.NoSuchProcess, psutil.AccessDenied, gw.PyGetWindowException, AttributeError):
#             active_process_name = None

#         # If process cant be identified, wait.
#         if not active_process_name:
#             time.sleep(1)
#             continue
            
#         for driver in driver_instances:
#             profile_config = driver.config.get("context_aware_profiles", {})
#             if not profile_config.get("enabled", False):
#                 continue

#             profiles = profile_config.get("profiles", {})
#             profiles_lower = {exe.lower(): layer for exe, layer in profiles.items()}
            
#             # Check for a config
#             profiled_layer_for_app = profiles_lower.get(active_process_name)
#             # If exe not found, check if any profile matches part of the window title.
#             if not profiled_layer_for_app:
#                 profiled_layer_for_app = next((v for k, v in profiles_lower.items() if k in active_window.title.lower()), None)

#             if profiled_layer_for_app:
#                 # A profiled application is in focus
#                 target_layer = profiled_layer_for_app
                
#                 # Only switch if the layer is not correct, or if user has manually navigated away from the layer.
#                 if target_layer != driver.context_layer or driver.current_layer != target_layer:
#                     log.info(f"Context switch/re-assertion for deck '{driver.deck.id()}': App '{active_process_name}' -> Layer '{target_layer}'")
#                     driver.set_context_layer(target_layer)
#             # If an un-profiled app is in focus (profiled_layer_for_app is None), do nothing.
#             # This makes the previous layer stick.
        
#         time.sleep(1)


# def profile_monitor_loop(driver_instances):
#     """
#     Monitors the active window and switches layers only when the focused application changes.
#     """
#     if not CONTEXT_AWARE_ENABLED:
#         log.warning("Context-aware dependencies not installed. Profile monitor disabled.")
#         return

#     if not driver_instances:
#         return

#     shutdown_event = driver_instances[0].shutdown_event
#     # Track the last known process to detect when it changes.
#     last_active_process_name = None

#     while not shutdown_event.is_set():
#         current_active_process_name = None
#         try:
#             active_window = gw.getActiveWindow()
#             if active_window and sys.platform == "win32" and active_window.title:
#                 _, pid = win32process.GetWindowThreadProcessId(active_window._hWnd)
#                 current_active_process_name = psutil.Process(pid).name().lower()
#         except (psutil.NoSuchProcess, psutil.AccessDenied, gw.PyGetWindowException, AttributeError):
#             current_active_process_name = None
        
#         # Only evaluate profiles if the focused application has actually changed.
#         if current_active_process_name != last_active_process_name:
#             log.info(f"Focus changed from '{last_active_process_name}' to '{current_active_process_name}'. Checking profiles...")
#             # Update the last known process.
#             last_active_process_name = current_active_process_name

#             for driver in driver_instances:
#                 profile_config = driver.config.get("context_aware_profiles", {})
#                 if not profile_config.get("enabled", False):
#                     continue

#                 profiles = profile_config.get("profiles", {})
#                 profiles_lower = {exe.lower(): layer for exe, layer in profiles.items()}
                
#                 profiled_layer_for_app = profiles_lower.get(current_active_process_name)

#                 if not profiled_layer_for_app:
#                     profiled_layer_for_app = next((v for k, v in profiles_lower.items() if k in active_window.title.lower()), None)

#                 if profiled_layer_for_app:
#                     # If the newly focused app has a profile, switch to it.
#                     if profiled_layer_for_app != driver.context_layer:
#                         log.info(f"Context switch for deck '{driver.deck.id()}': App '{current_active_process_name}' -> Layer '{profiled_layer_for_app}'")
#                         driver.set_context_layer(profiled_layer_for_app)
#                 else:
#                     # If the newly focused app has no profile, set the internal context to "main"
#                     # but leave the currently displayed layer as-is ("sticky" behavior).
#                     driver.context_layer = "main"
        
#         time.sleep(1)