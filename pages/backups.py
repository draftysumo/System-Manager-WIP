import os
import time
import subprocess
import logging
from gi import require_version
require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Gio

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class BackupsPage(Gtk.Box):
    # --- Configuration (Default Paths) ---
    DEFAULT_SOURCE_DIR = os.path.expanduser("~")
    DEFAULT_DESTINATION_DIR = os.path.expanduser("~/RsyncBackups")
    # -------------------------------------

    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        self.app = app
        for side in ("start", "end", "top", "bottom"):
            getattr(self, f"set_margin_{side}")(20)

        # 1. Configuration Frame
        config_frame = Gtk.Frame(label="Backup Configuration")
        config_frame.set_css_classes(["card", "shadow"])
        
        config_grid = Gtk.Grid(column_spacing=15, row_spacing=12)
        config_grid.set_margin_start(15); config_grid.set_margin_end(15); config_grid.set_margin_top(15); config_grid.set_margin_bottom(15)
        
        row_index = 0

        # --- What to backup (Source) ---
        lbl_source = Gtk.Label(label="What to backup:", xalign=0)
        lbl_source.set_css_classes(["title-5"])
        
        source_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.source_entry = Gtk.Entry()
        self.source_entry.set_text(self.DEFAULT_SOURCE_DIR)
        self.source_entry.set_hexpand(True)
        self.source_entry.set_editable(False) # Display only
        
        self.browse_source_btn = Gtk.Button(label="Browse...")
        # Use lambda to pass the specific entry to be updated
        self.browse_source_btn.connect("clicked", self.open_folder_chooser, self.source_entry) 

        source_box.append(self.source_entry)
        source_box.append(self.browse_source_btn)
        
        config_grid.attach(lbl_source, 0, row_index, 1, 1)
        config_grid.attach(source_box, 1, row_index, 1, 1); row_index += 1


        # --- Where to dump backups (Destination) ---
        lbl_destination = Gtk.Label(label="Where to dump backups:", xalign=0)
        lbl_destination.set_css_classes(["title-5"])

        destination_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.destination_entry = Gtk.Entry()
        self.destination_entry.set_text(self.DEFAULT_DESTINATION_DIR)
        self.destination_entry.set_hexpand(True)
        self.destination_entry.set_editable(False) # Display only
        
        self.browse_destination_btn = Gtk.Button(label="Browse...")
        # Use lambda to pass the specific entry to be updated
        self.browse_destination_btn.connect("clicked", self.open_folder_chooser, self.destination_entry) 

        destination_box.append(self.destination_entry)
        destination_box.append(self.browse_destination_btn)

        config_grid.attach(lbl_destination, 0, row_index, 1, 1)
        config_grid.attach(destination_box, 1, row_index, 1, 1); row_index += 1


        # --- Name (Prefix) ---
        lbl_name_prefix = Gtk.Label(label="Name:", xalign=0)
        lbl_name_prefix.set_css_classes(["title-5"])
        self.name_prefix_entry = Gtk.Entry()
        self.name_prefix_entry.set_placeholder_text("e.g., my_daily")
        self.name_prefix_entry.set_text("manual")
        self.name_prefix_entry.set_hexpand(True)
        
        config_grid.attach(lbl_name_prefix, 0, row_index, 1, 1)
        config_grid.attach(self.name_prefix_entry, 1, row_index, 1, 1); row_index += 1

        config_frame.set_child(config_grid)
        self.append(config_frame)
        
        # 2. Action Toolbar and Status
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        action_box.set_css_classes(["toolbar", "padded"])
        
        # Create Backup Button
        create_img = Gtk.Image.new_from_icon_name("document-save-symbolic")
        self.create_btn = Gtk.Button(label="Create Backup", child=create_img)
        self.create_btn.set_tooltip_text("Create new Rsync backup.")
        self.create_btn.connect("clicked", self.create_backup)
        self.create_btn.set_css_classes(["suggested-action"])

        # Refresh button
        refresh_img = Gtk.Image.new_from_icon_name("view-refresh-symbolic")
        self.refresh_btn = Gtk.Button(child=refresh_img)
        self.refresh_btn.set_tooltip_text("Refresh List")
        self.refresh_btn.connect("clicked", self.refresh_backups)
        self.refresh_btn.set_css_classes(["flat"])

        # Status & Progress Container
        self.status_label = Gtk.Label(label="", xalign=0)
        self.status_label.set_hexpand(True)
        self.status_label.set_css_classes(["dim-label"])

        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_visible(False)
        self.progress_bar.set_text("Waiting...")
        self.progress_bar.set_show_text(True)
        self.progress_bar.set_hexpand(True)
        
        status_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        status_container.set_hexpand(True)
        status_container.append(self.status_label)
        status_container.append(self.progress_bar)
        
        action_box.append(self.create_btn)
        action_box.append(self.refresh_btn)
        action_box.append(status_container)
        
        self.append(action_box) 

        # 3. List of Backups
        lbl_list = Gtk.Label(label="Existing Backups", xalign=0)
        lbl_list.set_css_classes(["title-3"])
        lbl_list.set_margin_top(5)
        self.append(lbl_list)
        
        self.backup_list = Gtk.ListBox()
        self.backup_list.set_vexpand(True)
        self.backup_list.set_css_classes(["list"])
        
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(self.backup_list)
        self.append(scroll)
        
        # Initial status update and refresh
        self.update_status_message(f"Current destination: {self.destination_entry.get_text()}")
        self.refresh_backups()


    def update_status_message(self, message, is_error=False):
        """Updates the status label text and styling."""
        self.status_label.set_text(message)
        self.status_label.set_css_classes(["error"] if is_error else ["dim-label"])


    def set_ui_busy(self, is_busy, message=""):
        """Sets the UI state for busy/idle operations and manages progress bar."""
        is_idle = not is_busy
        self.create_btn.set_sensitive(is_idle)
        self.refresh_btn.set_sensitive(is_idle)
        
        for entry in [self.source_entry, self.destination_entry, self.name_prefix_entry]:
            entry.set_sensitive(is_idle)
        
        for btn in [self.browse_source_btn, self.browse_destination_btn]:
            btn.set_sensitive(is_idle)
        
        if is_busy:
            self.progress_bar.set_fraction(0.0)
            self.progress_bar.set_text(message)
            self.progress_bar.set_visible(True)
            self.progress_bar.pulse()
            self.status_label.set_visible(False)
        else:
            self.progress_bar.set_visible(False)
            self.progress_bar.set_fraction(0.0)
            self.update_status_message(f"Current destination: {self.destination_entry.get_text()}")
            self.status_label.set_visible(True)

    def open_folder_chooser(self, widget, target_entry):
        """Opens a Gtk.FileChooserDialog and updates the specified entry widget."""
        logging.info(f"Browse button clicked for {target_entry.get_text()}.")
        
        parent_window = self.app.window 
        current_path = target_entry.get_text()
        start_path = current_path
        
        # Determine the safest path to start from
        if not os.path.isdir(start_path):
            start_path = os.path.expanduser("~")
            logging.warning(f"Initial path '{current_path}' is invalid or inaccessible. Falling back to: {start_path}")
        else:
             logging.info(f"Using initial path: {start_path}")
        
        # Use Gtk.FileChooserDialog for maximum compatibility
        dialog = Gtk.FileChooserDialog(
            title="Select Folder",
            transient_for=parent_window,
            action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        
        dialog.add_buttons(
            "Cancel", Gtk.ResponseType.CANCEL,
            "Select", Gtk.ResponseType.ACCEPT
        )
        
        # Set the current folder
        try:
            dialog.set_current_folder(Gio.File.new_for_path(start_path))
        except Exception as e:
             logging.error(f"Failed to set initial folder: {e}")

        
        # Connect the response handler, passing the target entry
        def on_folder_chosen(dialog, response):
            if response == Gtk.ResponseType.ACCEPT:
                gfile = dialog.get_file()
                if gfile:
                    path = gfile.get_path()
                    if path:
                        logging.info(f"Folder selected: {path}")
                        target_entry.set_text(path)
                    else:
                        logging.error("Selected file is None or path is invalid.")
            else:
                 logging.info("Folder selection cancelled.")
            
            dialog.destroy()

        dialog.connect("response", on_folder_chosen)
        dialog.present()


    def create_backup(self, widget):
        """Creates a new timestamped backup using rsync."""
        source_dir = os.path.expanduser(self.source_entry.get_text())
        destination_root = os.path.expanduser(self.destination_entry.get_text())
        name_prefix = self.name_prefix_entry.get_text().strip() or "manual"

        if not os.path.isdir(source_dir):
            self.update_status_message(f"Error: Source directory not found: {source_dir}", is_error=True)
            return

        # Ensure destination root exists before proceeding
        try:
            os.makedirs(destination_root, exist_ok=True)
        except Exception as e:
            self.update_status_message(f"Error: Could not create destination directory: {e}", is_error=True)
            return

        self.set_ui_busy(True, "Creating backup (This may take a moment)...")
        # Pass all dynamic paths and prefix to the async execution helper
        GLib.idle_add(self._execute_rsync, source_dir, destination_root, name_prefix)
        
    def _execute_rsync(self, source_dir, destination_root, name_prefix):
        """Internal helper for the synchronous rsync execution."""
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            target_name = f"{name_prefix}_{timestamp}"
            target_dir = os.path.join(destination_root, target_name)
            
            # Rsync command: -a (archive mode)
            # Trailing slash on source copies the *contents*.
            rsync_command = [
                "rsync", "-a", 
                source_dir.rstrip(os.path.sep) + os.path.sep, 
                target_dir
            ]
            
            result = subprocess.run(rsync_command, capture_output=True, text=True, check=True)
            
            # Success
            self.set_ui_busy(False)
            self.update_status_message(f"Backup '{target_name}' created successfully in {destination_root}.")
            self.refresh_backups()

        except subprocess.CalledProcessError as e:
            # Failure
            self.set_ui_busy(False)
            error_msg = f"Rsync failed (Code {e.returncode}): {e.stderr.strip() or e.stdout.strip()}"
            logging.error(error_msg)
            self.update_status_message(error_msg, is_error=True)
            
        except FileNotFoundError:
            self.set_ui_busy(False)
            error_msg = "Error: rsync command not found. Ensure rsync is installed."
            logging.error(error_msg)
            self.update_status_message(error_msg, is_error=True)
            
        except Exception as e:
            self.set_ui_busy(False)
            error_msg = f"An unexpected error occurred: {e}"
            logging.error(error_msg)
            self.update_status_message(error_msg, is_error=True)
            
        return GLib.SOURCE_REMOVE

    def rename_backup(self, old_path, new_name):
        """Renames a backup directory."""
        destination_root = os.path.expanduser(self.destination_entry.get_text())
        old_name = os.path.basename(old_path)
        new_path = os.path.join(destination_root, new_name)
        
        if os.path.exists(new_path):
            self.update_status_message(f"Error: A backup named '{new_name}' already exists in the destination folder.", is_error=True)
            return

        try:
            # Need to ensure the original backup is in the CURRENT destination root path
            # For simplicity, we assume the list only shows backups in the current destination.
            os.rename(old_path, new_path)
            self.update_status_message(f"Backup '{old_name}' renamed to '{new_name}'.")
            self.refresh_backups()
        except Exception as e:
            error_msg = f"Failed to rename backup: {e}"
            logging.error(error_msg)
            self.update_status_message(error_msg, is_error=True)
            
    def delete_backup(self, path):
        """Deletes a backup directory recursively using 'rm -rf'."""
        self.set_ui_busy(True, f"Deleting backup: {os.path.basename(path)}...")
        GLib.idle_add(self._execute_delete, path)

    def _execute_delete(self, path):
        """Internal helper for synchronous recursive deletion."""
        try:
            command = ["rm", "-rf", path]
            subprocess.run(command, check=True)
            
            self.set_ui_busy(False)
            self.update_status_message(f"Backup '{os.path.basename(path)}' deleted successfully.")
            self.refresh_backups()
            
        except subprocess.CalledProcessError as e:
            self.set_ui_busy(False)
            error_msg = f"Deletion failed: {e.stderr.strip() or e.stdout.strip()}"
            logging.error(error_msg)
            self.update_status_message(error_msg, is_error=True)
            
        except Exception as e:
            self.set_ui_busy(False)
            error_msg = f"An unexpected error occurred during deletion: {e}"
            logging.error(error_msg)
            self.update_status_message(error_msg, is_error=True)

        return GLib.SOURCE_REMOVE

    def show_rename_dialog(self, widget, backup_path):
        """Displays a dialog to get the new name for the backup."""
        old_name = os.path.basename(backup_path)
        
        dialog = Gtk.Dialog(title="Rename Backup", transient_for=self.app.window, modal=True)
        dialog.set_default_size(300, 100)
        
        content_area = dialog.get_content_area()
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_top(10); vbox.set_margin_bottom(10); vbox.set_margin_start(10); vbox.set_margin_end(10)
        
        lbl = Gtk.Label(label=f"Enter new name for: <b>{old_name}</b>", xalign=0, use_markup=True)
        vbox.append(lbl)
        
        entry = Gtk.Entry()
        entry.set_text(old_name)
        vbox.append(entry)
        
        content_area.append(vbox)

        action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        action_bar.set_halign(Gtk.Align.END)
        action_bar.set_margin_end(10)
        action_bar.set_margin_bottom(10)
        
        cancel_button = Gtk.Button(label="Cancel")
        cancel_button.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.CANCEL))

        ok_button = Gtk.Button(label="Rename")
        ok_button.set_css_classes(["suggested-action"])
        ok_button.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.OK))

        action_bar.append(cancel_button)
        action_bar.append(ok_button)
        
        content_area.append(action_bar)

        def on_dialog_response(dialog, response):
            if response == Gtk.ResponseType.OK:
                new_name = entry.get_text().strip()
                if new_name and new_name != old_name:
                    self.rename_backup(backup_path, new_name)
                elif new_name == old_name:
                    self.update_status_message("Name not changed.")
            
            dialog.destroy()
            
        dialog.connect("response", on_dialog_response)
        dialog.present()

    def show_delete_confirmation_dialog(self, widget, backup_path):
        """Displays a dialog to confirm backup deletion."""
        backup_name = os.path.basename(backup_path)
        
        dialog = Gtk.Dialog(
            title="Confirm Deletion", 
            transient_for=self.app.window, 
            modal=True
        )
        dialog.set_default_size(350, 100)
        
        content_area = dialog.get_content_area()
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_top(20); vbox.set_margin_bottom(10); vbox.set_margin_start(10); vbox.set_margin_end(10)
        
        lbl = Gtk.Label(
            label=f"Are you sure you want to permanently delete backup: <b>{backup_name}</b>?", 
            xalign=0, 
            use_markup=True
        )
        lbl.set_wrap(True)
        vbox.append(lbl)
        content_area.append(vbox)

        action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        action_bar.set_halign(Gtk.Align.END)
        action_bar.set_margin_end(10)
        action_bar.set_margin_bottom(10)
        
        cancel_button = Gtk.Button(label="Cancel")
        cancel_button.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.CANCEL))

        delete_button = Gtk.Button(label="Delete", css_classes=["destructive-action"])
        delete_button.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.OK))

        action_bar.append(cancel_button)
        action_bar.append(delete_button)
        content_area.append(action_bar)

        def on_dialog_response(dialog, response):
            if response == Gtk.ResponseType.OK:
                self.delete_backup(backup_path)
            
            dialog.destroy()
            
        dialog.connect("response", on_dialog_response)
        dialog.present()


    def refresh_backups(self, widget=None):
        """Finds Rsync backups in the CURRENT destination and populates the ListBox."""
        self.backup_list.remove_all()
        
        destination_root = os.path.expanduser(self.destination_entry.get_text())

        # 1. Check if the root directory exists
        if not os.path.isdir(destination_root):
            row = Gtk.Label(label=f"Backup root directory not found: {destination_root}. Please set a valid destination.", css_classes=["error"])
            row.set_margin_top(20)
            self.backup_list.append(Gtk.ListBoxRow(child=row))
            self.update_status_message(f"Destination folder '{destination_root}' not found.", is_error=True)
            return True

        # 2. Find all directories inside the root
        try:
            backup_paths = [
                os.path.join(destination_root, d)
                for d in os.listdir(destination_root)
                if os.path.isdir(os.path.join(destination_root, d))
            ]
        except Exception as e:
            self.update_status_message(f"Error reading destination directory: {e}", is_error=True)
            return True
        
        # 3. Sort by modification time (most recent first)
        backup_paths = sorted(backup_paths, key=lambda p: os.path.getmtime(p), reverse=True)

        if not backup_paths:
            row = Gtk.Label(label=f"No Rsync backups found in {destination_root}.", css_classes=["dim-label"])
            row.set_margin_top(20)
            self.backup_list.append(Gtk.ListBoxRow(child=row))
            return True

        for p in backup_paths:
            name = os.path.basename(p)
            
            # Metadata extraction
            try:
                mtime = time.localtime(os.path.getmtime(p))
                timestr = time.strftime("%Y-%m-%d %H:%M:%S", mtime)
                # Parse timestamp from folder name
                if len(name) > 16 and name[-16] == '_':
                    t = time.strptime(name[-15:], "%Y%m%d_%H%M%S")
                    timestr = time.strftime("%Y-%m-%d %H:%M:%S", t)
            except Exception:
                timestr = "Unknown"
                
            # --- START Size Calculation Fix ---
            try:
                # Use 'du -sh' for proper recursive directory size calculation in human-readable format.
                # This is a synchronous call, but generally fast enough for typical directory structures.
                du_result = subprocess.run(
                    ["du", "-sh", p],
                    capture_output=True,
                    text=True,
                    check=True
                )
                # The output format is typically: <size>\t<path>. We take the size part.
                size_str = du_result.stdout.split()[0]
            except Exception as e:
                logging.error(f"Error calculating size for {p}: {e}")
                size_str = "Size Unknown"
            # --- END Size Calculation Fix ---
            
            # --- Row Layout ---
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
            row_box.set_margin_top(10); row_box.set_margin_bottom(10)
            
            # Snapshot name
            lbl_name = Gtk.Label(label=name, xalign=0)
            lbl_name.set_css_classes(["title-4"])
            lbl_name.set_hexpand(True)
            
            # Timestamp
            lbl_time = Gtk.Label(label=timestr, xalign=0)
            lbl_time.set_css_classes(["dim-label"])
            lbl_time.set_size_request(150, -1) 

            # Size
            # lbl_size will now contain human-readable format like '1.5G', '200M', etc.
            lbl_size = Gtk.Label(label=size_str, xalign=1)
            lbl_size.set_css_classes(["dim-label"])
            lbl_size.set_size_request(100, -1) 

            # Action Buttons Box
            action_buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

            # Rename Button
            rename_img = Gtk.Image.new_from_icon_name("document-properties-symbolic")
            rename_btn = Gtk.Button(child=rename_img)
            rename_btn.set_tooltip_text("Rename Backup")
            rename_btn.connect("clicked", self.show_rename_dialog, p)
            rename_btn.set_css_classes(["flat"])
            
            # Delete Button
            delete_img = Gtk.Image.new_from_icon_name("user-trash-symbolic")
            delete_btn = Gtk.Button(child=delete_img)
            delete_btn.set_tooltip_text("Delete Backup")
            delete_btn.connect("clicked", self.show_delete_confirmation_dialog, p)
            delete_btn.set_css_classes(["destructive-action", "flat"])

            action_buttons_box.append(rename_btn)
            action_buttons_box.append(delete_btn)


            row_box.append(lbl_name)
            row_box.append(lbl_time)
            row_box.append(lbl_size)
            row_box.append(action_buttons_box)
            
            row = Gtk.ListBoxRow(child=row_box)
            self.backup_list.append(row)
            
        return True