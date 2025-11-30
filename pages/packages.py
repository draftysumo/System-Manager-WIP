import subprocess
import time
from gi.repository import Gtk, Gdk, GLib
# Restored imports for custom functions
from utils.apt import run_apt_command
from utils.async_ops import run_async_cmd

class PackagesPage(Gtk.Box):
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.app = app
        self._suppress_pkg_toggle = False
        self.last_pkg_toggled_idx = None
        
        for side in ("start", "end", "top", "bottom"):
            getattr(self, f"set_margin_{side}")(10)

        # 1. Primary action bar (like a header bar)
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header_box.set_css_classes(["toolbar"]) 
        
        # --- Create Buttons (All now icons on the left side) ---
        
        # Refresh button (Icon) - Furthest left
        refresh_img = Gtk.Image.new_from_icon_name("view-refresh-symbolic")
        self.refresh_btn = Gtk.Button(child=refresh_img)
        self.refresh_btn.set_tooltip_text("Refresh")
        self.refresh_btn.connect("clicked", self.refresh_packages)

        # Update System Button (Icon)
        update_img = Gtk.Image.new_from_icon_name("update-manager-symbolic")
        self.update_btn = Gtk.Button(child=update_img)
        self.update_btn.set_tooltip_text("Update & Upgrade System")
        self.update_btn.connect("clicked", self.update_system)
        
        # Clean Packages Button (Icon)
        clean_img = Gtk.Image.new_from_icon_name("remove-custom-icon-symbolic")
        self.clean_btn = Gtk.Button(child=clean_img)
        self.clean_btn.set_tooltip_text("Clean Unused")
        self.clean_btn.connect("clicked", self.clean_packages)
        
        # Install Package Button (Icon)
        install_img = Gtk.Image.new_from_icon_name("aptdaemon-download-symbolic")
        self.install_btn = Gtk.Button(child=install_img)
        self.install_btn.set_tooltip_text("Install Package")
        self.install_btn.connect("clicked", self.install_package_dialog)
        
        # Search Entry (takes most space)
        self.package_search = Gtk.Entry()
        self.package_search.set_placeholder_text("Search packages")
        self.package_search.connect("changed", self.filter_packages)
        self.package_search.set_hexpand(True)
        
        # Secondary Actions (Grouped in a MenuButton, now on the right of search bar)
        self.action_menu_btn = Gtk.MenuButton()
        self.action_menu_btn.set_icon_name("open-menu-symbolic")
        self.action_menu_btn.set_tooltip_text("Additional Actions")
        
        # Create a Gtk.Popover and Gtk.Box for the menu contents
        menu_popover = Gtk.Popover.new()
        menu_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        menu_box.set_spacing(0) 
        
        # Show Upgradable button (Text Label, now inside the menu)
        upgradable_btn = Gtk.Button(label="Show Upgradable Packages")
        upgradable_btn.connect("clicked", self.show_upgradeable_packages)
        menu_box.append(upgradable_btn)
        
        # Set popover content and connect to menu button
        menu_popover.set_child(menu_box)
        self.action_menu_btn.set_popover(menu_popover)

        # --- Append in new order: Icons on Left, Search Bar, Dropdown on Right ---
        header_box.append(self.refresh_btn)       # 1. Refresh
        header_box.append(self.update_btn)        # 2. Update & Upgrade
        header_box.append(self.clean_btn)         # 3. Clean
        header_box.append(self.install_btn)       # 4. Install
        header_box.append(self.package_search)    # 5. Search Bar (Expanded)
        header_box.append(self.action_menu_btn)   # 6. Dropdown Menu (on the far right)
        
        self.append(header_box) 

        # ListStore and filter
        self.pkg_store = Gtk.ListStore(bool, str, str, str, int, int)
        self.pkg_filter = self.pkg_store.filter_new(None)
        self.pkg_filter.set_visible_func(self.pkg_visible_func)

        self.packages_tree = Gtk.TreeView(model=self.pkg_filter)
        self.packages_tree.set_vexpand(True)

        # Checkbox column (index 0)
        toggle_renderer = Gtk.CellRendererToggle()
        toggle_renderer.connect("toggled", self.on_package_toggled)
        col_checkbox = Gtk.TreeViewColumn("", toggle_renderer)
        col_checkbox.add_attribute(toggle_renderer, "active", 0)
        self.packages_tree.append_column(col_checkbox)

        # Icon column (index 2)
        pixbuf_renderer = Gtk.CellRendererPixbuf()
        col_icon = Gtk.TreeViewColumn("", pixbuf_renderer)
        col_icon.add_attribute(pixbuf_renderer, "icon-name", 2)
        col_icon.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        col_icon.set_fixed_width(36)
        self.packages_tree.append_column(col_icon)

        # Name column
        text_renderer = Gtk.CellRendererText()
        col_name = Gtk.TreeViewColumn("Package", text_renderer, text=1)
        col_name.set_expand(True)
        self.packages_tree.append_column(col_name)

        # Version column
        col_version = Gtk.TreeViewColumn("Version", text_renderer, text=3)
        self.packages_tree.append_column(col_version)

        # Size column
        col_size = Gtk.TreeViewColumn("Size (KB)", text_renderer, text=4)
        self.packages_tree.append_column(col_size)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(self.packages_tree)
        self.append(scroll)

        # Buttons: immediate actions on selected packages
        btn_row = Gtk.Box(spacing=8)
        remove_btn = Gtk.Button(label="Remove Selected")
        remove_btn.connect("clicked", self.remove_selected_packages)
        purge_btn = Gtk.Button(label="Purge Selected")
        purge_btn.connect("clicked", self.purge_selected_packages)
        reinstall_btn = Gtk.Button(label="Reinstall Selected")
        reinstall_btn.connect("clicked", self.reinstall_selected_packages)
        btn_row.append(remove_btn)
        btn_row.append(purge_btn)
        btn_row.append(reinstall_btn)
        self.append(btn_row)

        # Progress Status Bar
        self.status_box = Gtk.Box(spacing=8, orientation=Gtk.Orientation.HORIZONTAL)
        self.status_spinner = Gtk.Spinner()
        self.status_label = Gtk.Label(label="Ready.")
        self.status_box.append(self.status_spinner)
        self.status_box.append(self.status_label)
        self.status_box.set_halign(Gtk.Align.START)
        self.status_box.set_margin_top(10)
        self.append(self.status_box)

        # Shift-click support
        click = Gtk.GestureClick()
        click.connect("pressed", self.on_packages_tree_click)
        self.packages_tree.add_controller(click)

        self.refresh_packages()

    def show_progress(self, message, is_active):
        """Controls the visibility and state of the progress spinner and label."""
        self.status_label.set_text(message)
        if is_active:
            self.status_spinner.start()
            self.status_box.set_visible(True)
        else:
            self.status_spinner.stop()
            # Status bar remains visible to show the "Ready." state

    def _run_apt_action(self, message, command, success_message, error_message=None):
        """Helper to standardize running apt commands with progress indication."""
        self.show_progress(message, True)

        def completion_callback(success=True):
            if success:
                self.show_progress(success_message, False)
            else:
                self.show_progress(error_message or "Action failed. Check logs.", False)
            
            # Use a timeout to ensure the UI updates happen smoothly before refresh
            GLib.timeout_add(100, self.refresh_packages)

        run_apt_command(
            self.app.window,
            message,
            command,
            callback=completion_callback
        )

    def pkg_visible_func(self, model, iter_, data=None):
        text = self.package_search.get_text().lower()
        if not text:
            return True
        name = model.get_value(iter_, 1) or ""
        return text in name.lower()

    def filter_packages(self, widget):
        self.pkg_filter.refilter()

    def refresh_packages(self, widget=None):
        """Refreshes the package list, also called by the progress wrapper."""
        # Updated user-friendly status text
        self.show_progress("Scanning installed packages (via: dpkg-query)...", True)
        self.pkg_store.clear()
        try:
            result = subprocess.run(["dpkg-query", "--show", "--showformat=${Package}\t${Status}\t${Version}\t${Installed-Size}\n"],
                                    capture_output=True, text=True, check=True)
            for line in result.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) == 4 and "install ok installed" in parts[1]:
                    pkg_name = parts[0]
                    version = parts[2]
                    try:
                        size = int(parts[3] or 0) // 1024 
                    except ValueError:
                         size = 0
                    icon_name = "package-x-generic"
                    self.pkg_store.append([False, pkg_name, icon_name, version, size, 0])
        except Exception as e:
            self.pkg_store.append([False, f"Error: {e}", "dialog-error", "", 0, 0])
            self.show_progress(f"Error loading packages: {e}", False)
        finally:
            self.show_progress("Ready.", False)

    def show_upgradeable_packages(self, widget=None):
        # The show_upgradeable_packages button is now only in the dropdown, so we hide the popover here.
        # This function is called by a button *inside* the popover menu box.
        if isinstance(widget.get_parent(), Gtk.Box):
             if widget.get_parent().get_parent() and isinstance(widget.get_parent().get_parent(), Gtk.Popover):
                widget.get_parent().get_parent().popdown()
                
        # Updated user-friendly status text
        self.show_progress("Checking for updates (via: apt list)...", True)
        self.pkg_store.clear()
        try:
            result = subprocess.run(["apt", "list", "--upgradable"], capture_output=True, text=True, check=True)
            for line in result.stdout.splitlines():
                if line and not line.startswith("Listing..."):
                    parts = line.split("/")
                    pkg_name = parts[0]
                    self.pkg_store.append([False, pkg_name, "package-x-generic", "", 0, 0])
            self.show_progress("Upgradeable packages listed.", False)
        except Exception as e:
            self.pkg_store.append([False, f"Error: {e}", "dialog-error", "", 0, 0])
            self.show_progress(f"Error checking upgrades: {e}", False)

    def install_package_dialog(self, widget):
        # Popover hiding logic removed, as this is now triggered by the main icon button.
        
        # GTK4 fix: Use transient_for and string buttons
        dialog = Gtk.Dialog(title="Install Package", transient_for=self.app.window, modal=True)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL,
                           "Install", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)

        entry = Gtk.Entry()
        entry.set_placeholder_text("Enter package name(s), e.g. vlc htop")
        entry.set_activates_default(True)
        entry.set_margin_top(10)
        entry.set_margin_bottom(10)
        entry.set_margin_start(10)
        entry.set_margin_end(10)

        box = dialog.get_content_area()
        box.append(entry)
        
        # GTK4 fix: Handle dialog response with a signal connection
        def handle_response(dialog, response):
            if response == Gtk.ResponseType.OK:
                text = entry.get_text().strip()
                if text:
                    packages = text.split()
                    self._run_apt_action(
                        # Updated user-friendly status text
                        f"Installing package(s): {' '.join(packages)} (via: apt install)",
                        ["pkexec", "apt", "install", "-y"] + packages,
                        # Updated success message
                        f"Installation complete: {' '.join(packages)}."
                    )
            dialog.destroy()
            
        dialog.connect("response", handle_response)
        dialog.present()

    def update_system(self, widget):
        self._run_apt_action(
            # Updated user-friendly status text
            "Updating system and installing upgrades (via: apt update & upgrade)",
            ["pkexec", "bash", "-c", "apt update && apt upgrade -y"],
            # Updated success message
            "System is fully up-to-date."
        )

    def remove_selected_packages(self, widget):
        pkgs = [r[1] for r in self.pkg_store if r[0]]
        if not pkgs: return
        self._run_apt_action(
            # Updated user-friendly status text
            f"Removing selected packages (via: apt remove)", 
            ["pkexec", "apt", "remove", "-y"] + pkgs, 
            "Selected packages removed."
        )

    def purge_selected_packages(self, widget):
        pkgs = [r[1] for r in self.pkg_store if r[0]]
        if not pkgs: return
        self._run_apt_action(
            # Updated user-friendly status text
            f"Purging selected packages & config files (via: apt purge)", 
            ["pkexec", "apt", "purge", "-y"] + pkgs, 
            "Selected packages and configurations purged."
        )

    def reinstall_selected_packages(self, widget):
        pkgs = [r[1] for r in self.pkg_store if r[0]]
        if not pkgs: return
        self._run_apt_action(
            # Updated user-friendly status text
            f"Reinstalling selected packages (via: apt reinstall)", 
            ["pkexec", "apt", "install", "--reinstall", "-y"] + pkgs, 
            "Selected packages reinstalled."
        )

    def clean_packages(self, widget):
        # Popover hiding logic removed, as this is now triggered by the main icon button.
        
        self._run_apt_action(
            # Updated user-friendly status text
            "Cleaning up unused dependencies and cache (via: apt autoremove)", 
            ["pkexec", "apt", "autoremove", "-y"],
            # Updated success message
            "Cleanup complete. System storage freed."
        )

    def on_package_toggled(self, renderer, path):
        if self._suppress_pkg_toggle:
            self._suppress_pkg_toggle = False
            return
        try:
            tp = Gtk.TreePath(path)
        except Exception:
            tp = path
        child_path = self.pkg_filter.convert_path_to_child_path(tp)
        if not child_path: return
        idx = child_path.get_indices()[0]
        try:
            iter_ = self.pkg_store.get_iter(idx)
            current = self.pkg_store.get_value(iter_, 0)
        except Exception:
            try:
                current = bool(self.pkg_store[idx][0])
            except Exception:
                current = False

        new_state = not current
        try:
            self.pkg_store.set_value(iter_, 0, new_state)
        except Exception:
            try:
                self.pkg_store[idx][0] = new_state
            except Exception:
                pass
        self.last_pkg_toggled_idx = idx

    def on_packages_tree_click(self, gesture, n_press, x, y):
        tree = gesture.get_widget()
        try:
            res = tree.get_path_at_pos(int(x), int(y))
            if not res: return False
            path, column, cx, cy = res
            if column != tree.get_column(0): return False

            # Check app global shift state
            is_shift = self.app.shift_pressed or (self.app.shift_last_active and (time.time() - self.app.shift_last_active) < 0.6)

            try:
                tp = Gtk.TreePath(path)
            except Exception:
                tp = path
            child = self.pkg_filter.convert_path_to_child_path(tp)
            if not child: return False
            idx = child.get_indices()[0]

            if is_shift and self.last_pkg_toggled_idx is not None:
                try:
                    anchor_it = self.pkg_store.get_iter(self.last_pkg_toggled_idx)
                    anchor_state = self.pkg_store.get_value(anchor_it, 0)
                except Exception:
                    try:
                        anchor_state = bool(self.pkg_store[self.last_pkg_toggled_idx][0])
                    except Exception:
                        anchor_state = True

                new_state = anchor_state
                self._suppress_pkg_toggle = True
                a = min(self.last_pkg_toggled_idx, idx)
                b = max(self.last_pkg_toggled_idx, idx)
                for i in range(a, b + 1):
                    try:
                        it2 = self.pkg_store.get_iter(i)
                        self.pkg_store.set_value(it2, 0, new_state)
                    except Exception:
                        try:
                            self.pkg_store[i][0] = new_state
                        except Exception:
                            pass
                self.last_pkg_toggled_idx = idx
                return True
        except Exception:
            pass
        return False
