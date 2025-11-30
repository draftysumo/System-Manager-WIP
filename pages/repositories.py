import gi
gi.require_version('Gtk', '4.0') # Explicitly require GTK 4.0
import subprocess
import threading
import os
import re 
from gi.repository import Gtk, GLib

class RepositoriesPage(Gtk.Box):
    """
    A page for viewing and managing system package repositories (APT and Flatpak).
    Uses pkexec for actions that modify the system state.
    """
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.app = app
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.FILL)
        
        # Using individual margin setters for GTK 4 compatibility
        self.set_margin_start(10)
        self.set_margin_end(10)
        self.set_margin_top(10)
        self.set_margin_bottom(10)

        # Main Stack for APT and Flatpak views
        self.stack = Gtk.Stack()
        self.stack_switcher = Gtk.StackSwitcher(stack=self.stack)
        
        self.append(self.stack_switcher)
        self.append(self.stack)
        
        # Status Bar
        self.status_label = Gtk.Label(label="Ready.")
        
        # We must create the views before appending them to the stack
        # This fixes a potential issue where status_label might be missing if created too late
        self.apt_view = self._create_apt_view()
        self.flatpak_view = self._create_flatpak_view()

        self.stack.add_titled(self.apt_view, "apt_page", "APT Repositories")
        self.stack.add_titled(self.flatpak_view, "flatpak_page", "Flatpak Remotes")
        
        self.append(self.status_label)

        # Initial Load
        # Use GLib.idle_add to ensure the UI is fully constructed before starting threads
        GLib.idle_add(self._load_all_repositories)

    def _create_apt_view(self):
        """Creates the UI for APT repository management."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        # Model: Enabled (bool), File/Source (str), Components (str), Options (str)
        self.apt_store = Gtk.ListStore(bool, str, str, str)
        self.apt_tree = Gtk.TreeView(model=self.apt_store)
        self.apt_tree.set_vexpand(True)

        self._add_tree_column(self.apt_tree, "Enabled", 0, Gtk.CellRendererToggle(), toggled=self._toggle_apt_source)
        self._add_tree_column(self.apt_tree, "Source File", 1, Gtk.CellRendererText(), expand=True)
        self._add_tree_column(self.apt_tree, "Components", 2, Gtk.CellRendererText())
        self._add_tree_column(self.apt_tree, "Options", 3, Gtk.CellRendererText())

        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.apt_tree)
        box.append(scroll)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        # APT actions (primarily file editing/command based, simplifying to Add/Remove)
        self.apt_add_btn = Gtk.Button(label="Add Repository...")
        self.apt_add_btn.connect("clicked", lambda w: self._show_dialog("APT Add", "Adding a repository requires running 'pkexec add-apt-repository'. This feature requires manual input for security.", Gtk.MessageType.INFO))
        
        self.apt_remove_btn = Gtk.Button(label="Remove Selected")
        self.apt_remove_btn.connect("clicked", lambda w: self._run_apt_action("remove"))
        
        button_box.append(self.apt_add_btn)
        button_box.append(self.apt_remove_btn)
        box.append(button_box)
        
        return box

    def _create_flatpak_view(self):
        """Creates the UI for Flatpak remote management."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        # Model: Name (str), URL (str), Verified (bool), Homepage (str)
        self.flatpak_store = Gtk.ListStore(str, str, str, str)
        self.flatpak_tree = Gtk.TreeView(model=self.flatpak_store)
        self.flatpak_tree.set_vexpand(True)

        self._add_tree_column(self.flatpak_tree, "Name", 0, Gtk.CellRendererText())
        self._add_tree_column(self.flatpak_tree, "URL", 1, Gtk.CellRendererText(), expand=True)
        # Using a text renderer for the status since we can't reliably get a bool
        self._add_tree_column(self.flatpak_tree, "Verified", 2, Gtk.CellRendererText(), activatable=False) 
        self._add_tree_column(self.flatpak_tree, "Homepage", 3, Gtk.CellRendererText())
        
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.flatpak_tree)
        box.append(scroll)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        self.flatpak_add_btn = Gtk.Button(label="Add Remote...")
        self.flatpak_add_btn.connect("clicked", lambda w: self._show_dialog("Flatpak Add", "Adding a remote requires running 'pkexec flatpak remote-add'. This feature requires manual input for security.", Gtk.MessageType.INFO))
        
        self.flatpak_remove_btn = Gtk.Button(label="Remove Selected")
        self.flatpak_remove_btn.connect("clicked", lambda w: self._run_flatpak_action("delete"))
        
        button_box.append(self.flatpak_add_btn)
        button_box.append(self.flatpak_remove_btn)
        box.append(button_box)
        
        return box

    def _add_tree_column(self, tree, title, col_id, renderer, expand=False, toggled=None, **kwargs):
        """Helper to create and append a column to a TreeView."""
        column = Gtk.TreeViewColumn(title, renderer, text=col_id, **kwargs)
        column.set_sort_column_id(col_id)
        column.set_expand(expand)
        if toggled:
            renderer.set_property("activatable", True)
            renderer.connect("toggled", toggled, col_id)
        tree.append_column(column)

    # --- Loading Logic ---
    
    def _load_all_repositories(self):
        """Initiates loading of both APT and Flatpak data."""
        self.status_label.set_text("Loading repository information...")
        threading.Thread(target=self._run_load_threads).start()
        return False

    def _run_load_threads(self):
        """Runs loading for both repository types in the background."""
        # Load APT Sources in the main thread (since it's typically non-blocking file I/O)
        GLib.idle_add(self._load_apt_sources) 
        
        # Load Flatpak Remotes in a separate thread
        try:
            # Using the absolute simplest command to avoid syntax errors 
            cmd = ["flatpak", "remotes", "--all"] 
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=10) 
            if result.returncode == 0:
                GLib.idle_add(self._process_flatpak_output, result.stdout.strip())
            else:
                 error_msg = result.stderr.strip()
                 status_text = f"Flatpak load failed. (Code: {result.returncode}). Error: {error_msg}" if error_msg else f"Flatpak load failed. (Code: {result.returncode})"
                 GLib.idle_add(lambda: self.status_label.set_text(status_text))
        except Exception as e:
            GLib.idle_add(lambda: self.status_label.set_text(f"Flatpak execution error: {e}"))
            
    def _parse_apt_line(self, line, source_path):
        """Basic parsing of a 'deb' or 'deb-src' line."""
        line = line.strip()
        if not line or line.startswith(('#', 'deb-src')):
            return None # Skip comments and source repositories for simplicity

        # Simple regex for deb [options] uri dist component1 component2...
        match = re.match(r'^deb\s+\[(.*?)\]\s+(.*?)\s+(.*?)\s+(.*)', line)
        if match:
            options, uri, dist, components = match.groups()
            source_info = f"{uri} ({dist})"
            components = components.strip()
            return [True, source_info, components, options]
        
        # Simpler regex for deb uri dist component1 component2... (no options)
        match = re.match(r'^deb\s+(.*?)\s+(.*?)\s+(.*)', line)
        if match:
            uri, dist, components = match.groups()
            source_info = f"{uri} ({dist})"
            components = components.strip()
            return [True, source_info, components, ""]

        # Fallback to just displaying the line as the source
        return [True, f"[Unparsed] {line}", "", ""]

    def _load_apt_sources(self):
        """Loads and parses real APT source files."""
        self.apt_store.clear()
        sources = []

        # 1. Check /etc/apt/sources.list
        try:
            with open("/etc/apt/sources.list", 'r') as f:
                for line in f:
                    parsed = self._parse_apt_line(line, "/etc/apt/sources.list")
                    if parsed: sources.append(parsed)
        except Exception:
            # File might not exist or be readable (e.g., non-Debian system)
            pass

        # 2. Check /etc/apt/sources.list.d/ directory
        apt_dir = "/etc/apt/sources.list.d"
        if os.path.isdir(apt_dir):
            try:
                for filename in os.listdir(apt_dir):
                    if filename.endswith(".list") or filename.endswith(".sources"):
                        filepath = os.path.join(apt_dir, filename)
                        enabled = not filename.endswith(".disabled") # Basic check for .disabled files
                        
                        try:
                            with open(filepath, 'r') as f:
                                for line in f:
                                    # Use a modified parse for list.d files, adding the filename
                                    parsed = self._parse_apt_line(line, filepath)
                                    if parsed:
                                        # Update the source info to include the filename
                                        parsed[1] = f"{filename}: {parsed[1]}" 
                                        parsed[0] = enabled and parsed[0] # Combine file status with line status
                                        sources.append(parsed)
                        except Exception as e:
                            # Failed to read a specific file, report filename only
                            sources.append([enabled, f"[Read Error] {filename}", str(e), ""])
            except Exception as e:
                sources.append([True, f"[Directory Error] {apt_dir}", str(e), ""])

        # Add all sources to the store
        if not sources:
            self.apt_store.append([True, "No APT sources found.", "", ""])
            
        for source in sources:
            self.apt_store.append(source)
        
        self.status_label.set_text("APT sources loaded. Flatpak data loading...") # Update status message

    def _process_flatpak_output(self, output):
        """Processes flatpak remotes output using the standard space-separated format."""
        self.flatpak_store.clear()
        lines = output.splitlines()
        
        if not lines or (len(lines) == 1 and "Name" in lines[0]):
            if self.status_label.get_text().startswith("APT sources loaded."):
                 self.status_label.set_text(f"Loaded {len(self.apt_store)} APT sources. No Flatpak remotes found.")
            else:
                 self.status_label.set_text("No Flatpak remotes found.")
            return
        
        # Skip the header line if it exists
        if "Name" in lines[0]:
            lines = lines[1:]

        for line in lines:
            # Split by whitespace. The default columns are Name, Origin, Type, URL.
            parts = line.split() 
            
            if len(parts) >= 4:
                name = parts[0]
                url = parts[3] # URL is the fourth element
                
                # We cannot determine Verified or Homepage without the --columns flag, 
                # so we use placeholders.
                is_verified = "N/A" 
                homepage = ""
                
                # Append [Name, URL, Verified (str), Homepage (str)]
                self.flatpak_store.append([name, url, is_verified, homepage])
        
        self.status_label.set_text(f"Loaded {len(self.apt_store)} APT sources and {len(self.flatpak_store)} Flatpak remotes.")


    # --- Action Logic ---

    def _toggle_apt_source(self, cell, path, col_id):
        """Handles toggling the enabled state of an APT source (requires pkexec to rename file)."""
        iter_ = self.apt_store.get_iter(path)
        enabled = self.apt_store.get_value(iter_, 0)
        source_file = self.apt_store.get_value(iter_, 1)
        
        action = "disable" if enabled else "enable"
        
        if source_file.startswith("/etc/apt/sources.list.d/"):
            self._show_dialog("Action Blocked", 
                             f"Toggling APT sources ({action}) requires renaming files in /etc/apt/sources.list.d/ via 'pkexec'. Implementation is currently limited to view-only for security.", 
                             Gtk.MessageType.WARNING)
        else:
             self._show_dialog("Action Blocked", 
                             "Only sources in /etc/apt/sources.list.d/ can be toggled easily.", 
                             Gtk.MessageType.WARNING)

    def _run_flatpak_action(self, action):
        """Executes a privileged flatpak remote action."""
        
        selection = self.flatpak_tree.get_selection()
        model, iter_ = selection.get_selected()

        if not iter_:
            self._show_dialog("No Remote Selected", "Please select a Flatpak remote.", Gtk.MessageType.WARNING)
            return

        remote_name = model.get_value(iter_, 0)
        
        # Confirmation Dialog
        dialog = Gtk.MessageDialog(
            transient_for=self.app.window, 
            modal=True,
            buttons=Gtk.ButtonsType.YES_NO,
            message_type=Gtk.MessageType.QUESTION,
            text=f"Confirm Flatpak Action: {action.capitalize()} {remote_name}",
            secondary_text=f"Are you sure you want to {action} the remote '{remote_name}'? This requires administrative privileges."
        )
        
        def handle_response(dialog, response):
            if response == Gtk.ResponseType.YES:
                self.status_label.set_text(f"Requesting privilege to {action} {remote_name}...")
                threading.Thread(target=self._run_privileged_flatpak_thread, args=(action, remote_name)).start()
            dialog.destroy()
            
        dialog.connect("response", handle_response)
        dialog.present()
        
    def _run_privileged_flatpak_thread(self, action, remote_name):
        """Runs the privileged flatpak command via pkexec."""
        try:
            # Command: pkexec flatpak remote-delete [remote_name]
            cmd = ["pkexec", "flatpak", f"remote-{action}", remote_name]
            
            # Using check=True to raise error on non-zero exit code
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
            
            GLib.idle_add(lambda: self.status_label.set_text(f"Successfully executed '{action}' on {remote_name}."))
            GLib.idle_add(self._load_all_repositories) # Refresh list

        except subprocess.CalledProcessError as e:
            error_msg = f"Action '{action}' failed on {remote_name}.\n\nError Output:\n{e.stderr.strip()}"
            GLib.idle_add(lambda: self._show_dialog("Privileged Action Failed", error_msg, Gtk.MessageType.ERROR))
            GLib.idle_add(lambda: self.status_label.set_text(f"Action '{action}' on {remote_name} failed."))
        except Exception as e:
            GLib.idle_add(lambda: self._show_dialog("Unexpected Error", f"An unexpected error occurred: {e}", Gtk.MessageType.ERROR))

    def _run_apt_action(self, action):
        """Stub for privileged APT actions."""
        self._show_dialog("Action Blocked", 
                         f"APT actions like '{action}' require complex file manipulation in /etc/apt/ or using 'add-apt-repository' via 'pkexec'. Implementation is currently limited to view-only for security.", 
                         Gtk.MessageType.WARNING)

    def _show_dialog(self, title, message, type=Gtk.MessageType.INFO):
        """Helper to display a non-blocking dialog for action feedback."""
        dialog = Gtk.MessageDialog(
            # NOTE: self.app.window might not be the main window if not properly passed, 
            # use self.get_root() as a more robust solution in GTK 4
            transient_for=self.get_root() if self.get_root() else None, 
            modal=True,
            buttons=Gtk.ButtonsType.OK,
            message_type=type,
            text=title,
            secondary_text=message
        )
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.present()