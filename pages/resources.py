import psutil
from gi.repository import Gtk, GLib, cairo # cairo is imported to fix LineCap error

class ResourcesPage(Gtk.Box):
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.app = app
        for side in ("start", "end", "top", "bottom"):
            getattr(self, f"set_margin_{side}")(10)

        # Initialize network counters locally
        nic = psutil.net_io_counters()
        self.last_bytes_sent = getattr(nic, 'bytes_sent', 0)
        self.last_bytes_recv = getattr(nic, 'bytes_recv', 0)

        cpu_count = psutil.cpu_count(logical=True)
        self.metrics = ["CPU Total"] + [f"CPU Core {i+1}" for i in range(cpu_count)] + ["RAM"]
        
        # Only initialize disk metrics for the root disk summary card
        self.disk_partitions = psutil.disk_partitions(all=False)
        root_mount = self.disk_partitions[0].mountpoint if self.disk_partitions else "/"
        self.disk_metrics = [f"Disk {root_mount}"]
        
        self.metrics += self.disk_metrics + ["Network Sent", "Network Recv"]
        self.metric_history = {m: [] for m in self.metrics}
        self.max_history = 120 # History in seconds (2 minutes)
        self.max_for_metric = {m: 100 for m in self.metrics if "Network" not in m}
        self.max_for_metric["Network Sent"] = 1.0
        self.max_for_metric["Network Recv"] = 1.0

        # -----------------------------------------------------
        # 1. Summary Cards (CPU, RAM, Disk, Network Speed)
        # -----------------------------------------------------
        summary_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        summary_box.set_hexpand(True)
        self.summary_labels = {}
        self.summary_areas = {}

        summary_box.append(self.make_card("CPU", "CPU Total", (0.2, 0.6, 0.8)))
        summary_box.append(self.make_card("Memory", "RAM", (0.8, 0.4, 0.2)))
        summary_box.append(self.make_card("Disk", f"Disk {root_mount}", (0.4, 0.8, 0.2)))
        summary_box.append(self.make_card("Network", "Network Sent", (0.8, 0.2, 0.4)))

        self.append(summary_box)

        # -----------------------------------------------------
        # 2. Detailed Metrics (Cores and Network)
        # -----------------------------------------------------
        details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        
        # CPU Cores Detail (Now includes percentage label next to sparkline)
        cores_label = Gtk.Label(label="CPU Cores Activity", xalign=0)
        cores_label.set_margin_top(10)
        details_box.append(cores_label)
        
        cores_grid = Gtk.Grid(column_spacing=15, row_spacing=8)
        cores_grid.set_hexpand(True)
        
        self.core_widgets = [] 
        cols = 3 
        for i in range(cpu_count):
            metric_key = f"CPU Core {i+1}"
            
            h_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            h_box.set_hexpand(True)
            
            # Label
            label = Gtk.Label(label=f"Core {i+1}: 0.0%", xalign=0)
            label.set_size_request(80, -1) 
            
            # Drawing Area (Sparkline)
            a = Gtk.DrawingArea()
            a.set_size_request(-1, 50)
            a.set_hexpand(True)
            a.set_draw_func(self.make_sparkline_draw(metric_key, (0.2, 0.6, 0.8)))
            
            h_box.append(label)
            h_box.append(a)
            
            self.core_widgets.append({'label': label, 'area': a})
            r = i // cols; c = i % cols
            cores_grid.attach(h_box, c, r, 1, 1)

        details_box.append(cores_grid)

        # Disks section removed as requested
        
        # Network Graph
        net_label = Gtk.Label(label="Network Throughput (MB/s)", xalign=0)
        details_box.append(net_label)
        
        self.network_area = Gtk.DrawingArea()
        self.network_area.set_vexpand(True)
        self.network_area.set_hexpand(True)
        self.network_area.set_size_request(-1, 180)
        self.network_area.set_draw_func(self.make_network_draw())
        details_box.append(self.network_area)

        self.append(details_box)

        # Set up a continuous timer for updates
        GLib.timeout_add_seconds(1, self.update_resources)

    def make_card(self, title, metric_key, color):
        frame = Gtk.Frame()
        frame.set_hexpand(True)
        frame.set_css_classes(["card", "elevated"])
        
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        v.set_margin_top(15); v.set_margin_bottom(15); v.set_margin_start(15); v.set_margin_end(15)
        
        title_lbl = Gtk.Label(label=title, xalign=0)
        title_lbl.set_css_classes(["dim-label"])
        title_lbl.set_margin_bottom(2)
        
        big_lbl = Gtk.Label(label="0%", xalign=0)
        big_lbl.set_markup(f"<span font_desc='Sans 28'><b>0%</b></span>")
        
        small_area = Gtk.DrawingArea(); small_area.set_size_request(-1, 50)
        small_area.set_hexpand(True)
        small_area.set_draw_func(self.make_sparkline_draw(metric_key, color))
        
        v.append(title_lbl)
        v.append(big_lbl)
        v.append(small_area)
        frame.set_child(v)
        
        self.summary_labels[metric_key] = big_lbl
        self.summary_areas[metric_key] = small_area
        return frame

    def make_sparkline_draw(self, metric, color=(0.2, 0.6, 0.8)):
        def draw(area, cr, w, h):
            # Draw dark background for high contrast (Consistency with Network Graph)
            cr.set_source_rgb(0.07, 0.07, 0.07)
            cr.paint()
            
            values = self.metric_history.get(metric, [])[-self.max_history:]
            if not values:
                return
            
            # --- Margins and Drawing Area ---
            x_margin = 25  # Space for Y-axis labels (small for sparkline)
            y_margin_top = 5 
            y_margin_bottom = 5 
            
            draw_w = w - x_margin
            draw_h = h - y_margin_top - y_margin_bottom
            
            max_v = self.max_for_metric.get(metric, 100) # Always 100 for CPU/RAM/Disk
            
            # --- Grid Lines and Labels (Y-Axis) ---
            cr.set_source_rgb(0.18, 0.18, 0.18)
            cr.set_line_width(1)
            cr.set_font_size(8) # Smaller font for small sparkline area
            
            # Draw 100%, 50%, 0% grid lines and labels
            # The range (3) covers three positions: top (100%), middle (50%), bottom (0%)
            for i in range(3): 
                percent_label = (2 - i) * 50
                y = y_margin_top + draw_h * (i / 2)
                
                # Draw grid line
                if i < 2: # Draw 100% and 50% lines as grid lines
                    cr.set_source_rgb(0.18, 0.18, 0.18)
                    cr.move_to(x_margin, y); cr.line_to(w, y); cr.stroke()
                
                # Draw label (100% and 50%)
                if percent_label > 0:
                    cr.set_source_rgb(0.6, 0.6, 0.6)
                    cr.move_to(2, y + 3) # x=2 to keep margin
                    cr.show_text(f"{percent_label}%")
            
            # Draw 0% baseline (slightly thicker/darker)
            y_zero = y_margin_top + draw_h
            cr.set_source_rgb(0.2, 0.2, 0.2)
            cr.move_to(x_margin, y_zero); cr.line_to(w, y_zero); cr.stroke()
            
            # --- Draw Metric Line ---
            cr.set_source_rgb(*color)
            cr.set_line_width(2)
            cr.set_line_cap(cairo.LineCap.ROUND) 
            
            for i, v in enumerate(values):
                x = x_margin + i * draw_w / max(1, len(values) - 1)
                # Invert Y axis (0% is bottom, 100% is top)
                y = y_margin_top + draw_h - (min(v, max_v) / max_v) * draw_h
                
                if i == 0:
                    cr.move_to(x, y)
                else:
                    cr.line_to(x, y)
            cr.stroke()
            
        return draw

    def make_network_draw(self):
        def draw(area, cr, w, h):
            # Draw dark background for high contrast
            cr.set_source_rgb(0.07, 0.07, 0.07)
            cr.paint()
            
            sent = self.metric_history.get("Network Sent", [])[-self.max_history:]
            recv = self.metric_history.get("Network Recv", [])[-self.max_history:]

            # --- Dynamic Scaling ---
            absolute_max = max(max(sent or [0]), max(recv or [0]), 0.01) # Min scale for calculation
            
            # Simple rounding up mechanism for clean axis labels
            if absolute_max > 5.0:
                scale_step = 5.0
            elif absolute_max > 1.0:
                scale_step = 1.0
            elif absolute_max > 0.1:
                scale_step = 0.2
            else:
                scale_step = 0.05

            # Calculate the next clean upper bound
            max_v = (int(absolute_max / scale_step) + 1) * scale_step
            
            # --- Margins and Drawing Area ---
            x_margin = 45  # Space for Y-axis labels
            y_margin_top = 10 # Space for 'MB/s' label
            y_margin_bottom = 15 # Space for X-axis label
            
            draw_w = w - x_margin
            draw_h = h - y_margin_top - y_margin_bottom
            
            # --- Grid Lines and Labels (Y-Axis) ---
            cr.set_source_rgb(0.18, 0.18, 0.18)
            cr.set_line_width(1)
            cr.set_font_size(10)
            
            num_segments = 4 # Draws 3 intermediate lines and the 0 line
            
            # Draw Y-axis labels and horizontal grid lines
            for i in range(num_segments + 1): 
                y = y_margin_top + draw_h * (i / num_segments)
                
                # Draw grid line (don't draw top edge line)
                if i > 0 and i < num_segments:
                    cr.move_to(x_margin, y); cr.line_to(w, y); cr.stroke()
                
                # Draw the bottom line (0 MB/s) slightly thicker/darker
                if i == num_segments:
                    cr.set_source_rgb(0.2, 0.2, 0.2)
                    cr.move_to(x_margin, y); cr.line_to(w, y); cr.stroke()
                    cr.set_source_rgb(0.18, 0.18, 0.18) # Restore grid color

                # Draw label (Top to Bottom)
                value = max_v * (num_segments - i) / num_segments
                
                if i > 0 and i <= num_segments: # Label all lines from max down to 0
                    cr.set_source_rgb(0.6, 0.6, 0.6)
                    cr.move_to(5, y + 3) 
                    # Use appropriate formatting based on scale
                    format_str = ".2f" if max_v < 1.0 else ".1f"
                    cr.show_text(f"{value:{format_str}}")
            
            # --- Draw Max Value Label (Top Left) ---
            cr.set_source_rgb(0.9, 0.9, 0.9)
            cr.set_font_size(12)
            cr.move_to(5, y_margin_top - 2)
            cr.show_text(f"MB/s")

            # --- Draw X-axis Time Label (Bottom Right) ---
            cr.set_source_rgb(0.4, 0.4, 0.4)
            cr.set_font_size(10)
            time_span_min = self.max_history // 60
            cr.move_to(w - 70, h - 5)
            cr.show_text(f"Last {time_span_min} min")

            # --- Draw Network Lines ---
            
            # Need at least two points to draw lines
            if len(sent) < 2 and len(recv) < 2: return 

            # --- Draw Receive Line (Green) ---
            cr.set_source_rgb(0.2, 0.8, 0.2)
            cr.set_line_width(3)
            cr.set_line_cap(cairo.LineCap.ROUND)
            
            # Start draw path from the last point on the X-axis for smoother initial plot
            cr.move_to(x_margin, y_margin_top + draw_h) 
            for i, v in enumerate(recv):
                x = x_margin + i * draw_w / max(1, len(recv) - 1)
                # Invert Y: 0 is bottom (y_margin_top + draw_h), max_v is top (y_margin_top)
                y = y_margin_top + draw_h - (min(v, max_v) / max_v) * draw_h
                
                if i == 0: cr.move_to(x, y)
                else: cr.line_to(x, y)
            cr.stroke()
            
            # --- Draw Sent Line (Red) ---
            cr.set_source_rgb(0.9, 0.3, 0.3)
            cr.set_line_width(3)
            cr.set_line_cap(cairo.LineCap.ROUND)
            
            # Start draw path from the last point on the X-axis for smoother initial plot
            cr.move_to(x_margin, y_margin_top + draw_h) 
            for i, v in enumerate(sent):
                x = x_margin + i * draw_w / max(1, len(sent) - 1)
                y = y_margin_top + draw_h - (min(v, max_v) / max_v) * draw_h
                
                if i == 0: cr.move_to(x, y)
                else: cr.line_to(x, y)
            cr.stroke()
            
            # --- Draw Legend ---
            cr.set_source_rgb(1.0, 1.0, 1.0)
            legend_x = w - 150
            legend_y = y_margin_top + 15 # Move legend slightly down from the max label

            # Sent Legend
            cr.set_source_rgb(0.9, 0.3, 0.3)
            cr.rectangle(legend_x, legend_y - 8, 10, 10)
            cr.fill()
            cr.set_source_rgb(1.0, 1.0, 1.0)
            cr.move_to(legend_x + 15, legend_y)
            cr.show_text("Sent")

            # Recv Legend
            cr.set_source_rgb(0.2, 0.8, 0.2)
            cr.rectangle(legend_x + 60, legend_y - 8, 10, 10)
            cr.fill()
            cr.set_source_rgb(1.0, 1.0, 1.0)
            cr.move_to(legend_x + 75, legend_y)
            cr.show_text("Received")

        return draw

    def get_metric_values(self, metric):
        if metric == "CPU Total":
            return [psutil.cpu_percent()]
        elif metric.startswith("CPU Core"):
            try:
                core_percs = psutil.cpu_percent(percpu=True)
                core_index = int(metric.split()[-1]) - 1
                return [core_percs[core_index]]
            except IndexError:
                return [0]
        elif metric == "RAM":
            return [psutil.virtual_memory().percent]
        elif metric.startswith("Disk "):
            mount = metric[5:]
            try:
                return [psutil.disk_usage(mount).percent]
            except Exception:
                return [0]
        elif "Network" in metric:
            key = "bytes_sent" if "Sent" in metric else "bytes_recv"
            curr = getattr(psutil.net_io_counters(), key)
            delta = curr - getattr(self, f'last_{key}')
            setattr(self, f'last_{key}', curr)
            speed = delta / 1024 / 1024
            if speed > self.max_for_metric[metric]:
                self.max_for_metric[metric] = speed * 1.2
            return [speed]
        return [0]

    def update_resources(self):
        try:
            cpu_percs = psutil.cpu_percent(percpu=True)
        except Exception:
            cpu_percs = [0] * (psutil.cpu_count(logical=True) or 1)
        total = sum(cpu_percs) / max(1, len(cpu_percs))
        self.metric_history.setdefault("CPU Total", []).append(total)
        self.metric_history["CPU Total"] = self.metric_history["CPU Total"][-self.max_history:]
        
        # Update CPU Total Summary
        if "CPU Total" in self.summary_labels:
            self.summary_labels["CPU Total"].set_markup(f"<span font_desc='Sans 28'><b>{total:.0f}%</b></span>")
        if "CPU Total" in self.summary_areas:
            self.summary_areas["CPU Total"].queue_draw()

        # Update CPU Cores Detail (using new widget structure)
        for i, p in enumerate(cpu_percs):
            key = f"CPU Core {i+1}"
            self.metric_history.setdefault(key, []).append(p)
            self.metric_history[key] = self.metric_history[key][-self.max_history:]
            
            if i < len(getattr(self, 'core_widgets', [])):
                widget_data = self.core_widgets[i]
                widget_data['label'].set_text(f"Core {i+1}: {p:.1f}%") 
                widget_data['area'].queue_draw()

        # RAM Update
        try:
            ram = psutil.virtual_memory().percent
        except Exception:
            ram = 0.0
        self.metric_history.setdefault("RAM", []).append(ram)
        self.metric_history["RAM"] = self.metric_history["RAM"][-self.max_history:]
        if "RAM" in self.summary_labels:
            self.summary_labels["RAM"].set_markup(f"<span font_desc='Sans 28'><b>{ram:.0f}%</b></span>")
        if "RAM" in self.summary_areas:
            self.summary_areas["RAM"].queue_draw()
            
        # Disk Update (Only Root)
        try:
            root = self.disk_partitions[0].mountpoint if self.disk_partitions else "/"
            root_usage = psutil.disk_usage(root).percent
        except Exception:
            root_usage = 0.0
        
        disk_key = f"Disk {root}"
        self.metric_history.setdefault(disk_key, []).append(root_usage)
        self.metric_history[disk_key] = self.metric_history[disk_key][-self.max_history:]
        
        if disk_key in self.summary_labels:
            self.summary_labels[disk_key].set_markup(f"<span font_desc='Sans 28'><b>{root_usage:.0f}%</b></span>")
        if disk_key in self.summary_areas:
            self.summary_areas[disk_key].queue_draw()
            
        # Network Update
        sent = self.get_metric_values("Network Sent")[0]
        recv = self.get_metric_values("Network Recv")[0]
        self.metric_history.setdefault("Network Sent", []).append(sent)
        self.metric_history.setdefault("Network Recv", []).append(recv)
        self.metric_history["Network Sent"] = self.metric_history["Network Sent"][-self.max_history:]
        self.metric_history["Network Recv"] = self.metric_history["Network Recv"][-self.max_history:]
        
        if "Network Sent" in self.summary_labels:
            self.summary_labels["Network Sent"].set_markup(f"<span font_desc='Sans 28'><b>{sent:.2f} MB/s</b></span>")
        
        if hasattr(self, 'network_area'):
            self.network_area.queue_draw()
        if "Network Sent" in self.summary_areas:
            self.summary_areas["Network Sent"].queue_draw()
            
        return True