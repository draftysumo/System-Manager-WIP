import gi
import subprocess
import threading
import sys
import os
from gi.repository import Gtk, GLib, Gdk

class StoragePage(Gtk.Box):
    """
    A page that launches the GNOME Disk Usage Analyzer when the tab is opened.
    It checks the process list before launching to ensure only one instance runs.
    """
    
    # Common names for the Disk Usage Analyzer executable
    ANALYZER_COMMANDS = ["baobab", "gnome-disk-usage-analyzer"]

    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.app = app
        
        for side in ("start", "end", "top", "bottom"):
            getattr(self, f"set_margin_{side}")(40)
        
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)
        
        # --- UI Elements ---
        
        # 1. Main Content Box (centered)
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        main_box.set_halign(Gtk.Align.CENTER)
        
        # 2. Status Label (for error or success messages)
        self.status_label = Gtk.Label(
            label="Loading...", 
            xalign=0.5,
            wrap=True,
            max_width_chars=60
        )
        self.status_label.get_style_context().add_class("title")
        main_box.append(self.status_label)
        
        self.append(main_box)
        
        self.analyzer_command = None # Stores the confirmed command name

        # Initial check for the tool's availability
        GLib.idle_add(self._check_tool_availability)
        
        # Connect to the 'map' signal to trigger the launch logic when the page is shown
        self.connect("map", self._on_page_mapped)

    def _on_page_mapped(self, widget):
        """Called when the widget is first made visible (i.e., when the tab is clicked)."""
        if self.analyzer_command:
            self.status_label.set_text(f"Checking if '{self.analyzer_command}' is already open...")
            # Use a thread to perform the launch check and action without freezing the UI
            threading.Thread(target=self._launch_or_update_thread).start()
        elif self.analyzer_command is False:
            # If the command check failed, the error message is already set.
            pass


    def _check_tool_availability(self):
        """Checks if any of the analyzer commands are available in the system PATH."""
        for cmd in self.ANALYZER_COMMANDS:
            try:
                # Check if the command exists (which returns the path if found)
                subprocess.run(['which', cmd], check=True, capture_output=True)
                self.analyzer_command = cmd
                self.status_label.set_text(f"Ready to check and launch '{cmd}'.")
                return False # Stop GLib idle handler
            except subprocess.CalledProcessError:
                continue
            except FileNotFoundError:
                continue

        # If loop finishes without finding a command
        self.analyzer_command = False # Indicate check completed and failed
        self.status_label.set_text(
            "Error: Disk Usage Analyzer (baobab) not found. Please ensure it is installed."
        )
        return False # Stop GLib idle handler

    def _is_analyzer_running(self):
        """Checks the process list to see if the analyzer is currently running."""
        if not self.analyzer_command:
            return False
            
        try:
            # Use 'pgrep' to check for the process name. 
            # -f searches the full command line, making it more reliable.
            subprocess.run(['pgrep', '-f', self.analyzer_command], check=True, capture_output=True)
            return True # Process found (pgrep returns exit code 0)
        except subprocess.CalledProcessError:
            return False # Process not found (pgrep returns exit code 1)
        except Exception:
            # pgrep command itself not found or other I/O error
            return False

    def _launch_or_update_thread(self):
        """Checks for running process and launches/updates status in a background thread."""
        
        if not self.analyzer_command:
            # If the tool check failed, just let the error message remain
            return 

        if self._is_analyzer_running():
            GLib.idle_add(lambda: self.status_label.set_text("Disk Analyzer is already open in external application."))
        else:
            # If not running, launch it
            self._run_tool_thread(self.analyzer_command)

    def _run_tool_thread(self, command):
        """Executes the external tool in the background."""
        
        # Update the status to show launching is in progress
        GLib.idle_add(lambda: self.status_label.set_text(f"Launching '{command}' in external window..."))

        try:
            # Popen is used as the tool runs independently
            subprocess.Popen([command])
            # Update the status to show success in the main thread
            GLib.idle_add(lambda: self.status_label.set_text("Opened in external application."))
        except FileNotFoundError:
            GLib.idle_add(lambda: self.status_label.set_text(f"Launch Failed: Command '{command}' not found."))
        except Exception as e:
            GLib.idle_add(lambda: self.status_label.set_text(f"Launch Error: An error occurred: {e}"))