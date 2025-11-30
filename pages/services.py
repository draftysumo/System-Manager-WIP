import gi
import subprocess
import threading
from gi.repository import Gtk, GLib

class ServicesPage(Gtk.Box):
    """
    A page for managing systemd services (start, stop, restart, enable, disable).
    Uses pkexec for all sensitive actions.
    """
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.app = app
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.FILL)
        
        for side in ("start", "end", "top", "bottom"):
            getattr(self, f"set_margin_{side}")(10)

        # ListStore: Status (str), Name (str), Description (str), Active (bool)
        self.service_store = Gtk.ListStore(str, str, str, bool)
        self.service_tree = Gtk.TreeView(model=self.service_store)
        self.service_tree.set_vexpand(True)

        # Set up columns
        render_status = Gtk.CellRendererText()
        col_status = Gtk.TreeViewColumn("Status", render_status, text=0)
        col_status.set_sort_column_id(0)
        self.service_tree.append_column(col_status)

        render_name = Gtk.CellRendererText()
        col_name = Gtk.TreeViewColumn("Service Name", render_name, text=1)
        col_name.set_expand(True)
        col_name.set_sort_column_id(1)
        self.service_tree.append_column(col_name)

        render_desc = Gtk.CellRendererText()
        col_desc = Gtk.TreeViewColumn("Description", render_desc, text=2)
        col_desc.set_sort_column_id(2)
        self.service_tree.append_column(col_desc)

        # Scrolled Window
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.service_tree)
        self.append(scroll)

        # Action Buttons (all require root)
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        self.start_btn = Gtk.Button(label="Start")
        self.start_btn.connect("clicked", lambda w: self._run_service_action("start"))
        
        self.stop_btn = Gtk.Button(label="Stop")
        self.stop_btn.connect("clicked", lambda w: self._run_service_action("stop"))
        
        self.restart_btn = Gtk.Button(label="Restart")
        self.restart_btn.connect("clicked", lambda w: self._run_service_action("restart"))

        self.enable_btn = Gtk.Button(label="Enable (Auto-start)")
        self.enable_btn.connect("clicked", lambda w: self._run_service_action("enable"))
        
        self.disable_btn = Gtk.Button(label="Disable (No Auto-start)")
        self.disable_btn.connect("clicked", lambda w: self._run_service_action("disable"))

        # Add buttons to box
        button_box.append(self.start_btn)
        button_box.append(self.stop_btn)
        button_box.append(self.restart_btn)
        button_box.append(self.enable_btn)
        button_box.append(self.disable_btn)
        self.append(button_box)
        
        # Status Bar
        self.status_label = Gtk.Label(label="Ready.")
        self.append(self.status_label)
        
        # Initial data load
        GLib.idle_add(self._load_services)

    def _load_services(self):
        """Loads the list of system services using systemctl."""
        self.status_label.set_text("Loading system services...")
        threading.Thread(target=self._run_service_load_thread).start()
        return False # Stop idle handler

    def _run_service_load_thread(self):
        """Runs the systemctl command in a separate thread."""
        try:
            # systemctl list-units --type=service is usually non-privileged
            cmd = ["systemctl", "list-units", "--type=service", "--no-pager"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
            GLib.idle_add(self._process_service_output, result.stdout.strip())
        except subprocess.CalledProcessError as e:
            error = f"Error loading services (Code {e.returncode}): {e.stderr.strip()}"
            GLib.idle_add(lambda: self.status_label.set_text(error))
        except Exception as e:
            GLib.idle_add(lambda: self.status_label.set_text(f"Service load failed: {e}"))
            
    def _process_service_output(self, output):
        """Processes the systemctl output and populates the ListStore."""
        self.service_store.clear()
        lines = output.splitlines()
        
        # Skip the header line and the summary line at the end
        if len(lines) > 2:
            lines = lines[1:-1]

        for line in lines:
            # Split line by multiple spaces, which is how systemctl formats output
            parts = line.split(maxsplit=5)
            if len(parts) >= 5:
                # Example parts: ['unit', 'load', 'active', 'sub', 'description']
                unit_name = parts[0]
                active_status = parts[2] # 'active', 'inactive', 'failed', etc.
                description = parts[4] if len(parts) > 4 else unit_name
                
                is_active = active_status == "active"
                
                # Status, Name, Description, Active (bool)
                self.service_store.append([active_status, unit_name, description, is_active])
        
        self.status_label.set_text(f"Loaded {len(self.service_store)} services.")


    def _run_service_action(self, action):
        """Executes a privileged systemctl action on the selected service."""
        
        selection = self.service_tree.get_selection()
        model, iter_ = selection.get_selected()

        if not iter_:
            self._show_dialog("No Service Selected", "Please select a service from the list to perform an action.", Gtk.MessageType.WARNING)
            return

        service_name = model.get_value(iter_, 1)
        
        # Confirmation Dialog
        dialog = Gtk.MessageDialog(
            transient_for=self.app.window, 
            modal=True,
            buttons=Gtk.ButtonsType.YES_NO,
            message_type=Gtk.MessageType.QUESTION,
            text=f"Confirm Action: {action.capitalize()} {service_name}",
            secondary_text=f"Are you sure you want to {action} the service '{service_name}'? This requires administrative privileges and affects system stability."
        )
        
        def handle_response(dialog, response):
            if response == Gtk.ResponseType.YES:
                self.status_label.set_text(f"Requesting privilege to {action} {service_name}...")
                threading.Thread(target=self._run_privileged_action_thread, args=(action, service_name)).start()
            dialog.destroy()
            
        dialog.connect("response", handle_response)
        dialog.present()


    def _run_privileged_action_thread(self, action, service_name):
        """Runs the privileged systemctl command via pkexec."""
        try:
            # Command: pkexec systemctl [action] [service_name]
            cmd = ["pkexec", "systemctl", action, service_name]
            
            # Run the command with check=True to raise an error on failure
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
            
            # If successful, refresh the service list and show success
            GLib.idle_add(lambda: self.status_label.set_text(f"Successfully executed '{action}' on {service_name}."))
            GLib.idle_add(self._load_services) # Refresh list after success

        except subprocess.CalledProcessError as e:
            # Failed command execution (could be pkexec denied or systemctl failure)
            error_msg = f"Action '{action}' failed on {service_name}.\n\nError Output:\n{e.stderr.strip()}"
            GLib.idle_add(lambda: self._show_dialog("Privileged Action Failed", error_msg, Gtk.MessageType.ERROR))
            GLib.idle_add(lambda: self.status_label.set_text(f"Action '{action}' on {service_name} failed."))
        except FileNotFoundError:
             # pkexec or systemctl not found (unlikely on Linux)
            error_msg = f"Dependency not found: systemctl or pkexec."
            GLib.idle_add(lambda: self._show_dialog("System Error", error_msg, Gtk.MessageType.ERROR))
        except Exception as e:
            GLib.idle_add(lambda: self._show_dialog("Unexpected Error", f"An unexpected error occurred: {e}", Gtk.MessageType.ERROR))

    def _show_dialog(self, title, message, type=Gtk.MessageType.INFO):
        """Helper to display a non-blocking dialog for action feedback."""
        dialog = Gtk.MessageDialog(
            transient_for=self.app.window, 
            modal=True,
            buttons=Gtk.ButtonsType.OK,
            message_type=type,
            text=title,
            secondary_text=message
        )
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.present()