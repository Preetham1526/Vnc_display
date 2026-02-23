import os
import subprocess
import shutil
import socket
import time
import signal


def find_free_port():
    s = socket.socket()
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    return port
def find_free_display():
    for display_num in range(90, 200):
        path = f"/tmp/.X11-unix/X{display_num}"
        if not os.path.exists(path):
            return f":{display_num}"
    raise RuntimeError("No free X display found")

class LinuxDisplayManager:
    def __init__(self, resolution):
        self.resolution = resolution
        self.display = find_free_display()
        self.vnc_port = find_free_port()
        self.novnc_port = find_free_port()
        self.processes = []

    def _check_binary(self, name):
        if not shutil.which(name):
            raise RuntimeError(f"{name} is not installed.")

    def _check_dependencies(self):
        for binary in ["Xvfb", "fluxbox", "x11vnc", "websockify"]:
            self._check_binary(binary)

    def start(self):
        self._check_dependencies()

        os.environ["DISPLAY"] = self.display

        xvfb = subprocess.Popen(
            ["Xvfb", self.display, "-screen", "0", self.resolution],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.processes.append(xvfb)
        time.sleep(1)

        fluxbox = subprocess.Popen(
            ["fluxbox"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.processes.append(fluxbox)

        x11vnc = subprocess.Popen(
            [
                "x11vnc",
                "-display", self.display,
                "-nopw",
                "-forever",
                "-rfbport", str(self.vnc_port),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.processes.append(x11vnc)

        websockify = subprocess.Popen(
            [
                "websockify",
                str(self.novnc_port),
                f"localhost:{self.vnc_port}"
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.processes.append(websockify)

        print(f"Live View available at http://localhost:{self.novnc_port}/vnc.html")

    def stop(self):
        for p in reversed(self.processes):
            try:
                p.terminate()
                p.wait(timeout=5)
            except Exception:
                p.kill()
