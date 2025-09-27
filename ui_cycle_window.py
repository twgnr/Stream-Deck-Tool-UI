#--------------------------------------------------------------------
# Import packages
#--------------------------------------------------------------------
import tkinter as tk

#--------------------------------------------------------------------
# Import sub-packages
#--------------------------------------------------------------------
from tkinter import ttk

class CycleWindow(tk.Toplevel):
    """A small, borderless window to display and cycle through commands."""
    def __init__(self, items):
        super().__init__()
        
        # Make the window a borderless, always-on-top tool window
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        
        self.items = items
        self.labels = []
        
        # Style for selected vs. default items
        style = ttk.Style(self)
        style.configure("Selected.TLabel", background="#0078D7", foreground="white")
        style.configure("Default.TLabel", background="#2E2E2E", foreground="white")

        # Create a label for each item
        for i, item_text in enumerate(items):
            label = ttk.Label(self, text=item_text, padding=(10, 5), style="Default.TLabel", font=("Arial", 11))
            label.pack(fill="x")
            self.labels.append(label)

        # Position the window at the center of the screen
        self.update_idletasks()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (self.winfo_width() // 2)
        y = (screen_height // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")
        
        # Initial highlight
        self.update_selection(0)


    def update_selection(self, new_index):
        """Updates the visual highlight to the newly selected item."""
        for i, label in enumerate(self.labels):
            if i == new_index:
                label.config(style="Selected.TLabel")
            else:
                label.config(style="Default.TLabel")