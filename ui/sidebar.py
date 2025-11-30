from gi.repository import Gtk

def create_sidebar_button(title, stack_name, icon_name, stack_object):
    btn = Gtk.Button()
    h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    h.set_margin_top(6); h.set_margin_bottom(6); h.set_margin_start(6); h.set_margin_end(6)

    # Check for unicode/emoji icons vs standard icon names
    if icon_name and (len(icon_name) > 1 and (icon_name[0] in "\U0001F300-\U0001F6FF" or icon_name[0].encode('utf-8').startswith(b'\xf0')) or any(ord(ch) > 10000 for ch in icon_name)):
        img = Gtk.Label(label=icon_name)
        img.set_xalign(0)
    else:
        try:
            img = Gtk.Image.new_from_icon_name(icon_name)
        except Exception:
            img = Gtk.Image.new_from_icon_name("applications-system")
    h.append(img)
    lab = Gtk.Label(label=title, xalign=0)
    h.append(lab)
    btn.set_child(h)
    btn.connect("clicked", lambda w: stack_object.set_visible_child_name(stack_name))
    return btn
