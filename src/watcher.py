import os
import threading
import time
from variables import CONFIG_PATH
file_changed_event = threading.Event()
def config_watcher(poll_interval=3):
    last_mtime = os.path.getmtime(CONFIG_PATH) if os.path.exists(CONFIG_PATH) else None
    while True:
        try: current = os.path.getmtime(CONFIG_PATH)
        except FileNotFoundError: current = None
        if current is not None and last_mtime is not None and current != last_mtime: file_changed_event.set()
        last_mtime = current
        time.sleep(poll_interval)
def register_config_watcher():
    threading.Thread(target=config_watcher, name="config-watcher", daemon=True).start()
    return file_changed_event
