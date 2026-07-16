# Stream Deck Configuration Tool

A powerful, open-source configuration tool for Elgato Stream Deck devices, offering deep customization and workflow integration. It provides a user-friendly graphical interface to customize key layouts, actions, and appearances, going beyond the official software's capabilities. With features like dynamic data display, automatic profile switching, and a versatile action system, this tool allows for deep integration with your workflows.

## Core Features

* **Graphical User Interface:** An intuitive UI built with Tkinter and ttkbootstrap for easy configuration of Stream Deck keys.
* **Multiple Action Types:** Assign a wide range of actions to keys, including:
  * Executing applications and scripts.
  * Simulating hotkeys and keyboard shortcuts.
  * Typing text and inserting snippets.
  * Controlling media playback and system volume.
  * Performing HTTP requests.
  * Advanced multi-action sequences and macros.
* **Dynamic Keys:** Display real-time information on your Stream Deck keys from various data providers like:
  * System metrics (CPU, RAM, GPU usage).
  * Network speed.
  * Disk space.
  * Custom data sources.
* **Layers and Profiles:** Create different layers of keys and switch between them. Set up profiles that automatically activate when specific applications are in focus.
* **Customizable Appearance:** Tailor the look of your keys with custom icons, labels, fonts, and background colors.
* **Hot-Reloading:** Configuration changes are automatically detected and applied without needing to restart the application.
* **Automatic Device Detection:** Stream Decks that are unplugged and replugged (or connected after startup) are detected and reconnected automatically — no application restart required.
* **Macro Recorder:** Record mouse and keyboard actions to create complex macros.

## Advanced Functionality

* **Context-Aware Profile Switching:** The `profile_monitor.py` script actively monitors the foreground application and can automatically switch to a pre-configured layer, providing context-sensitive controls.
* **Press-and-Hold Actions:** Configure keys to perform a different action when held for a short duration.
* **Toggle and Timed Keys:** Create toggle keys for states (like a mute button) or timed actions that automatically revert.
* **Window Management:** Assign actions to manage application windows, such as snapping them to screen edges or moving them between monitors.

## Getting Started

### Prerequisites

* Python 3.7+
* An Elgato Stream Deck device

### Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/twgnr/Stream-Deck-Tool-UI.git
    cd Stream-Deck-Tool-UI
    ```

2.  Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```

#### Windows Specific Setup: `hidapi.dll`

For the Stream Deck to be recognized on Windows, you will need to download the correct `hidapi.dll` file.

1.  Go to the [hidapi releases page](https://github.com/libusb/hidapi/releases).
2.  Download the latest release zip file for Windows (e.g., `hidapi-0.14.0-win64.zip` for a 64-bit system).
3.  Extract the zip file.
4.  Copy the `hidapi.dll` file from the appropriate architecture folder (`x64` for 64-bit) into the root directory of this project (the same folder as `ui_main.py`).

### Running the Application

To start the main application with the user interface and Stream Deck driver, run:
```bash
python ui_main.py
```
## How It Works

The application is composed of several key modules:

* `main.py`: A command-line entry point to run the drivers without the graphical user interface.

* `ui_main.py`: The main entry point for the application, creating the GUI and managing the overall application state.

* `config_manager.py`: Handles all interactions with the `config.json` file, including loading, saving, and logging setup.

* `deck_driver.py`: Handles the direct communication with the Stream Deck device, setting key images and receiving key press events.

* `action_handler.py`: Executes the various actions assigned to keys.

* `rendering.py`: Responsible for creating the images displayed on the Stream Deck keys by combining icons, labels, and backgrounds.

* `ui_key_editor.py`: Provides the detailed configuration window for individual keys.

* `ui_macro_recorder.py`: The GUI window for recording keyboard and mouse macros.

* `ui_cycle_window.py`: Implements the pop-up window used by cycle actions like the command cycler and clipboard history.

* `dynamic_keys.py`: Manages the updating of keys that display real-time data.

* `data_providers.py`: Contains the functions that fetch real-time data (CPU, RAM, etc.) for the dynamic keys.

* `profile_monitor.py`: The background process that enables automatic profile switching.

* `hot_reloader.py`: Watches for changes in the configuration file and triggers a reload.

* `audio_utils.py`: Contains helper functions for controlling system audio on Windows.

## Contributing

Contributions are welcome! If you have ideas for new features, bug fixes, or improvements, please feel free to open an issue or submit a pull request.

## Acknowledgements

This project utilizes several open-source libraries, including:

* [streamdeck](https://pypi.org/project/streamdeck/) for Stream Deck communication.

* [ttkbootstrap](https://pypi.org/project/ttkbootstrap/) for the modern GUI theme.

* [pynput](https://pypi.org/project/pynput/) for keyboard and mouse control.

* [psutil](https://pypi.org/project/psutil/) for system monitoring.

* [pygetwindow](https://pypi.org/project/PyGetWindow/) for window management.

* [pycaw](https://pypi.org/project/pycaw/) for audio control on Windows.
