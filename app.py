import gi
import time
import logging
from gi.repository import Gtk, Gdk 

# Import UI and Pages
from ui.sidebar import create_sidebar_button
from pages.packages import PackagesPage
from pages.backups import BackupsPage
from pages.resources import ResourcesPage
from pages.processes import ProcessesPage
from pages.storage import StoragePage
from pages.services import ServicesPage
from pages.repositories import RepositoriesPage # <-- New Import

logging.basicConfig(level=logging.ERROR)

class SystemManager(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.draftysumo.SystemManager")
        self.connect("activate", self.on_activate)
        
        # Global state for Shift-Click functionality
        self.shift_pressed = False
        self.shift_last_active = None

    # New method to apply CSS for the sidebar header/divider
    def _apply_sidebar_css(self):
        """Applies custom CSS for styling the sidebar header."""
        css_provider = Gtk.CssProvider()
        
        # Define CSS for the header class
        css = """
        .sidebar-header {
            font-weight: bold;
            font-size: 0.9em;
            color: #6a6a6a; /* A subtle grey color */
            padding-top: 10px;
            padding-bottom: 5px;
        }
        """
        
        css_provider.load_from_data(css.encode('utf-8'))
        
        # Apply the provider globally using the default display (GTK4 standard)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), 
            css_provider, 
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


    def on_activate(self, app):
        self.window = Gtk.ApplicationWindow(application=app)
        self.window.set_title("System Manager")
        self.window.set_default_size(1400, 900)

        # Track Shift key state for gesture-based range selection
        keyc = Gtk.EventControllerKey()
        keyc.connect("key-pressed", self.on_key_pressed)
        keyc.connect("key-released", self.on_key_released)
        self.window.add_controller(keyc)

        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.window.set_child(main_box)

        # Sidebar (custom so we can show icons)
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for side in ("start", "end", "top", "bottom"):
            getattr(sidebar_box, f"set_margin_{side}")(10)
        sidebar_box.set_size_request(220, -1)

        # Main stack
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_vexpand(True)
        self.stack.set_hexpand(True)

        main_box.append(sidebar_box)
        main_box.append(self.stack)

        # Initialize Pages
        # We pass 'self' (app instance) so pages can access app.window and app.shift_pressed
        self.pages = {
            "packages": PackagesPage(self),
            "backups": BackupsPage(self),
            "resources": ResourcesPage(self),
            "processes": ProcessesPage(self),
            "storage": StoragePage(self),
            "repositories": RepositoriesPage(self), # <-- Initialize Repositories Page
            "services": ServicesPage(self)
        }

        # Add pages to stack
        for name, page_widget in self.pages.items():
            self.stack.add_titled(page_widget, name, name.capitalize())

        # Sidebar items configuration
        sidebar_items_top = [
            ("Packages", "packages", "package-x-generic-symbolic"),
            ("Backups", "backups", "backups-app-symbolic"),
            ("Resources", "resources", "gnome-system-monitor-symbolic"),
            ("Processes", "processes", "format-unordered-list-symbolic"),
            ("Storage", "storage", "drive-harddisk-symbolic"), 
        ]
        
        # Items meant to appear near the bottom
        sidebar_items_bottom = [
            ("Repositories", "repositories", "network-server-symbolic"), # <-- New item
            ("Services", "services", "org.gnome.Settings-online-accounts-symbolic"),
        ]

        # Add buttons to the top
        for title, name, icon in sidebar_items_top:
            btn = create_sidebar_button(title, name, icon, self.stack)
            sidebar_box.append(btn)
            
        # --- START Sidebar Divider Logic (Advanced Section) ---

        # 1. Separator line for visual division
        top_separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        top_separator.set_margin_top(10)
        top_separator.set_margin_bottom(5)
        sidebar_box.append(top_separator)
        
        # 2. Header Label for the Advanced section
        header_label = Gtk.Label(label="Advanced", halign=Gtk.Align.START)
        header_label.set_css_classes(["sidebar-header"])
        header_label.set_margin_start(10) # Match sidebar padding
        header_label.set_margin_end(10)
        header_label.set_margin_bottom(5)
        sidebar_box.append(header_label)

        # 3. Apply the custom CSS
        self._apply_sidebar_css()

        # --- END Sidebar Divider Logic ---

        # Add buttons to the bottom (Advanced Section)
        for title, name, icon in sidebar_items_bottom:
            btn = create_sidebar_button(title, name, icon, self.stack)
            sidebar_box.append(btn)


        self.window.present()

    def on_key_pressed(self, controller, keyval, keycode, state):
        try:
            if keyval in (Gdk.KEY_Shift_L, Gdk.KEY_Shift_R):
                self.shift_pressed = True
                self.shift_last_active = time.time()
        except Exception:
            pass
        return False

    # FIX 2: Added 'state' argument to correct the positional argument count
    def on_key_released(self, controller, keyval, keycode, state):
        try:
            if keyval in (Gdk.KEY_Shift_L, Gdk.KEY_Shift_R):
                self.shift_pressed = False
                self.shift_last_active = None
        except Exception:
            pass
        return False