import os
import platform
import signal
import subprocess
import socket
import shutil
from contextlib import contextmanager
from .linux_display import LinuxDisplayManager



class AgentVisualizer:
    def __init__(self, resolution="1280x800x24"):
        self.resolution = resolution
        self.system = platform.system()
        self.display_manager = None
        self._started = False

    def _is_linux(self):
        return self.system.lower() == "linux"

    def start(self):
        if self._is_linux():
            self.display_manager = LinuxDisplayManager(self.resolution)
            self.display_manager.start()
        self._started = True

    def get_display(self):
        if self._is_linux():
            return self.display_manager.display
        return None

    def get_live_view_url(self):
        if self._is_linux():
            return f"http://localhost:{self.display_manager.novnc_port}/vnc.html"
        return None

    def stop(self):
        if self.display_manager:
            self.display_manager.stop()
        self._started = False

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

      