import subprocess
import threading
import logging
from gi.repository import GLib

def run_async_cmd(cmd, callback=None):
    def target():
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True)
            out = proc.stdout + proc.stderr
            logging.debug(f"Command {' '.join(cmd)} exited {proc.returncode}")
        except Exception as e:
            out = str(e)
            logging.error(out)
        if callback:
            GLib.idle_add(callback)
    t = threading.Thread(target=target, daemon=True)
    t.start()