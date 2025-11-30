import glob
import os

def build_desktop_icon_map():
    paths = []
    paths += glob.glob('/usr/share/applications/*.desktop')
    paths += glob.glob(os.path.expanduser('~/.local/share/applications/*.desktop'))
    mapping = {}
    for p in paths:
        try:
            with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                icon = None
                exec_cmd = None
                for ln in f:
                    if ln.strip().startswith('Icon=') and icon is None:
                        icon = ln.split('=', 1)[1].strip()
                    if ln.strip().startswith('Exec=') and exec_cmd is None:
                        exec_cmd = ln.split('=', 1)[1].strip()
                    if icon and exec_cmd:
                        break
                if exec_cmd:
                    exe = exec_cmd.split()[0]
                    exe_base = os.path.basename(exe)
                    if icon:
                        mapping[exe_base] = icon
                    else:
                        mapping[exe_base] = os.path.splitext(os.path.basename(p))[0]
        except Exception:
            pass
    mapping.setdefault('python', 'python3')
    mapping.setdefault('bash', 'utilities-terminal')
    mapping.setdefault('sh', 'utilities-terminal')
    return mapping
