import os
import signal
import time
import psutil
import subprocess
import logging
from gi.repository import Gtk, Gdk, GLib
from utils.icons import build_desktop_icon_map
# FIX: Correcting the import path to reference the file where human_readable_size is defined.
from utils.helpers import human_readable_size

class ProcessesPage(Gtk.Box):
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.app = app
        self.desktop_icon_map = build_desktop_icon_map()
        self.last_proc_toggled_idx = None
        self._suppress_proc_toggle = False

        for side in ("start", "end", "top", "bottom"):
            getattr(self, f"set_margin_{side}")(10)

        self.process_search = Gtk.Entry()
        self.process_search.set_placeholder_text("Search processes")
        self.process_search.connect("changed", self.filter_processes)
        self.append(self.process_search)

        # FIX: Change last two types from int (for raw bytes) to str (for human-readable size)
        # Column types: (0:bool, 1:int, 2:str, 3:str, 4:float, 5:float, 6:int, 7:str, 8:str, 9:str, 10:str, 11:str)
        # Column content: (Active, PID, IconName, Name, CPU%, Mem%, Threads, Status, User, Command, Read (B), Write (B))
        self.process_store = Gtk.ListStore(bool, int, str, str, float, float, int, str, str, str, str, str)
        self.process_filter = self.process_store.filter_new(None)
        self.process_filter.set_visible_func(self.proc_visible_func)

        self.process_tree = Gtk.TreeView(model=self.process_filter)
        self.process_tree.set_vexpand(True)

        toggle = Gtk.CellRendererToggle()
        toggle.connect("toggled", self.on_process_toggled)
        col_check = Gtk.TreeViewColumn("", toggle)
        col_check.add_attribute(toggle, "active", 0)
        self.process_tree.append_column(col_check)

        pix = Gtk.CellRendererPixbuf()
        col_pix = Gtk.TreeViewColumn("", pix)
        # FIX: Use a custom data function to control visibility and suppress the Gtk placeholder icon.
        col_pix.set_cell_data_func(pix, self.render_icon_cell)
        col_pix.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        col_pix.set_fixed_width(36)
        self.process_tree.append_column(col_pix)

        headers = ["PID", "Name", "CPU%", "Memory%", "Threads", "Status", "User", "Command", "Read (B)", "Write (B)"]
        header_indices = [1, 3, 4, 5, 6, 7, 8, 9, 10, 11]
        for i, h in enumerate(headers):
            r = Gtk.CellRendererText()
            c = Gtk.TreeViewColumn(h, r, text=header_indices[i])
            c.set_sort_column_id(header_indices[i])
            self.process_tree.append_column(c)

        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.process_tree)
        scroll.set_vexpand(True)
        self.append(scroll)

        btn_box = Gtk.Box(spacing=8)
        for label, func in [
            ("Kill Selected", self.kill_selected_processes),
            ("Force Kill Selected", self.force_kill_selected),
            ("Suspend Selected", lambda w: self.send_signal(signal.SIGSTOP)),
            ("Resume Selected", lambda w: self.send_signal(signal.SIGCONT)),
            ("Force Refresh", lambda w: self.refresh_process_list())
        ]:
            b = Gtk.Button(label=label)
            b.connect("clicked", func)
            btn_box.append(b)
        self.append(btn_box)

        proc_click = Gtk.GestureClick()
        proc_click.connect("pressed", self.on_process_tree_click)
        self.process_tree.add_controller(proc_click)

        GLib.timeout_add_seconds(2, self.refresh_process_list)
        
    def render_icon_cell(self, column, cell, model, iter, data):
        """
        Custom cell data function for the icon column.
        Hides the Gtk.CellRendererPixbuf if no icon name is available by setting 'visible' to False.
        """
        icon_name = model.get_value(iter, 2) # Column 2 holds the icon name string
        
        if icon_name:
            cell.set_property("visible", True)
            cell.set_property("icon-name", icon_name)
        else:
            # If icon name is empty or None, hide the renderer completely
            cell.set_property("visible", False)
            cell.set_property("icon-name", "")


    def proc_visible_func(self, model, iter_, data=None):
        text = self.process_search.get_text().lower()
        if not text:
            return True
        name = model.get_value(iter_, 3) or ""
        cmd = model.get_value(iter_, 9) or ""
        return text in name.lower() or text in cmd.lower()

    def filter_processes(self, widget):
        self.process_filter.refilter()

    def refresh_process_list(self):
        selected_pids = {r[1] for r in self.process_store if r[0]}
        new_data = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'num_threads', 'status', 'username', 'cmdline', 'io_counters', 'exe']):
            try:
                i = p.info
                cmd = " ".join(i.get('cmdline') or []) or i.get('name') or ''
                io = i.get('io_counters', None)
                read_b = io.read_bytes if io else 0
                write_b = io.write_bytes if io else 0
                pid = i.get('pid')
                name = i.get('name') or '<unknown>'
                
                # 1. Get the icon name (returns None if not found)
                icon_name = self.icon_for_process(i)
                
                # 2. Convert None to empty string ("") to signal 'no icon' to the custom renderer
                icon_name_for_store = icon_name if icon_name is not None else ""

                # Convert large byte numbers to human-readable strings to prevent OverflowError
                read_str = human_readable_size(read_b)
                write_str = human_readable_size(write_b)

                new_data.append([pid in selected_pids, pid, icon_name_for_store, name,
                                 i.get('cpu_percent') or 0.0, i.get('memory_percent') or 0.0,
                                 i.get('num_threads') or 0, i.get('status') or "", i.get('username') or "", cmd, read_str, write_str]) # Use the strings here
            except Exception:
                pass

        existing = {self.process_store[i][1]: i for i in range(len(self.process_store))}
        for row in new_data:
            pid = row[1]
            if pid in existing:
                path = existing[pid]
                # Update existing row data
                for col, val in enumerate(row):
                    self.process_store[path][col] = val
            else:
                # Append new row
                self.process_store.append(row)

        # Remove processes that are no longer running
        to_remove = [i for i in range(len(self.process_store)) if self.process_store[i][1] not in {r[1] for r in new_data}]
        for i in reversed(to_remove):
            del self.process_store[self.process_store.get_iter(i)]
        return True

    def icon_for_process(self, pinfo):
        """
        Determines the appropriate icon name for a process.
        Returns None if no specific or generic icon can be found.
        """
        exe = pinfo.get('exe') or (pinfo.get('cmdline') or [None])[0] or pinfo.get('name')
        
        # If no executable/name is found, return None (no icon)
        if not exe:
            return None
            
        base = os.path.basename(exe).split()[0]
        icon = self.desktop_icon_map.get(base)
        
        # If a mapped icon is found, return it
        if icon:
            return icon
            
        # Try to guess based on basename, otherwise return None (no icon)
        guess = base.replace('.exe', '')
        # Return None if the guess is also empty or missing
        return guess if guess else None

    def kill_selected_processes(self, w):
        pids = [r[1] for r in self.process_store if r[0]]
        if not pids: return
        self.confirm_kill(pids, signal.SIGTERM, "Kill")

    def force_kill_selected(self, w):
        pids = [r[1] for r in self.process_store if r[0]]
        if not pids: return
        self.confirm_kill(pids, signal.SIGKILL, "FORCE KILL (SIGKILL)")

    def confirm_kill(self, pids, sig, title):
        dialog = Gtk.MessageDialog(transient_for=self.app.window, modal=True,
                                   buttons=Gtk.ButtonsType.YES_NO,
                                   message_type=Gtk.MessageType.WARNING,
                                   text=f"{title} {len(pids)} process(es)?")
        def resp(d, r):
            d.destroy()
            if r == Gtk.ResponseType.YES:
                for p in pids:
                    try:
                        os.kill(p, sig)
                    except PermissionError:
                        try:
                            subprocess.run(["pkexec", "kill", f"-{sig}", str(p)], check=True)
                        except Exception as e:
                            logging.error(f"Failed to kill {p}: {e}")
                    except Exception as e:
                        logging.error(f"Failed to kill {p}: {e}")
                self.refresh_process_list()
        dialog.connect("response", resp)
        dialog.show()

    def send_signal(self, sig):
        for row in self.process_store:
            if row[0]:
                try:
                    os.kill(row[1], sig)
                except PermissionError:
                    try:
                        subprocess.run(["pkexec", "kill", f"-{sig}", str(row[1])], check=True)
                    except Exception as e:
                        logging.error(f"Failed to send signal to {row[1]}: {e}")
                except Exception:
                    pass

    def on_process_toggled(self, w, path):
        if self._suppress_proc_toggle:
            self._suppress_proc_toggle = False
            return
        try:
            tp = Gtk.TreePath(path)
        except Exception:
            tp = path
        child_path = self.process_filter.convert_path_to_child_path(tp)
        if not child_path: return
        idx = child_path.get_indices()[0]
        try:
            it = self.process_store.get_iter(idx)
            cur = self.process_store.get_value(it, 0)
        except Exception:
            try:
                cur = bool(self.process_store[idx][0])
            except Exception:
                cur = False
        new_state = not cur
        try:
            self.process_store.set_value(it, 0, new_state)
        except Exception:
            try:
                self.process_store[idx][0] = new_state
            except Exception:
                pass
        self.last_proc_toggled_idx = idx

    def on_process_tree_click(self, gesture, n_press, x, y):
        tree = gesture.get_widget()
        try:
            res = tree.get_path_at_pos(int(x), int(y))
            if not res: return False
            path, column, cx, cy = res
            if column != tree.get_column(0): return False

            is_shift = self.app.shift_pressed or (self.app.shift_last_active and (time.time() - self.app.shift_last_active) < 0.6)

            try:
                tp = Gtk.TreePath(path)
            except Exception:
                tp = path
            child = self.process_filter.convert_path_to_child_path(tp)
            if not child: return False
            idx = child.get_indices()[0]

            if is_shift and self.last_proc_toggled_idx is not None:
                try:
                    anchor_it = self.process_store.get_iter(self.last_proc_toggled_idx)
                    anchor_state = self.process_store.get_value(anchor_it, 0)
                except Exception:
                    try:
                        anchor_state = bool(self.process_store[self.last_proc_toggled_idx][0])
                    except Exception:
                        anchor_state = True
                new_state = anchor_state
                self._suppress_proc_toggle = True
                a = min(self.last_proc_toggled_idx, idx)
                b = max(self.last_proc_toggled_idx, idx)
                for i in range(a, b + 1):
                    try:
                        it2 = self.process_store.get_iter(i)
                        self.process_store.set_value(it2, 0, new_state)
                    except Exception:
                        try:
                            self.process_store[i][0] = new_state
                        except Exception:
                            pass
                self.last_proc_toggled_idx = idx
                return True
        except Exception:
            pass
        return False