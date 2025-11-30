from gi.repository import Gtk
from utils.async_ops import run_async_cmd

def run_apt_command(parent_window, prompt, cmd, callback=None):
    dialog = Gtk.MessageDialog(transient_for=parent_window, modal=True,
                               buttons=Gtk.ButtonsType.YES_NO,
                               message_type=Gtk.MessageType.QUESTION,
                               text=prompt)

    def resp(d, r):
        d.destroy()
        if r == Gtk.ResponseType.YES:
            run_async_cmd(cmd, callback=callback)
    dialog.connect("response", resp)
    dialog.show()