"""
core.py — ADB Extractor & Analyser 2.0
Constants, logging, preferences, ADB helpers, and all extraction/analysis logic.
"""

import hashlib
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tarfile
import threading
import webbrowser
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from requests_toolbelt.multipart.encoder import MultipartEncoder


# ---------------------------------------------------------------------------
# Constants & Config
# ---------------------------------------------------------------------------

IS_FLATPAK = os.path.exists("/.flatpak-info")

if IS_FLATPAK:
    _xdg_config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    _xdg_state_home = os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state"))
    LOG_FILE = os.path.join(_xdg_state_home, "adbextractorandanalyzer", "logs.txt")
    PREFS_FILE = os.path.join(_xdg_config_home, "adbextractorandanalyzer", "preferences.json")
else:
    LOG_FILE = "logs.txt"
    PREFS_FILE = "preferences.json"


def _bundled_tool(path: str, fallback: str) -> str:
    return path if os.path.exists(path) else fallback


ADB_COMMAND = _bundled_tool("/app/bin/adb", "adb")
BUNDLED_ALEAPP = _bundled_tool("/app/libexec/aleapp/aleapp.py", "")
BUNDLED_JADX = _bundled_tool("/app/bin/jadx", "")

if IS_FLATPAK:
    _xdg_data_home = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    DEFAULT_OUTPUT_PATH = os.path.join(_xdg_data_home, "adbextractorandanalyzer", "evidence")
else:
    DEFAULT_OUTPUT_PATH = os.path.expanduser("~")

DEFAULT_PREFS = {
    "aleapp_path": BUNDLED_ALEAPP,
    "output_path": DEFAULT_OUTPUT_PATH,
    "jadx_path": BUNDLED_JADX,
    "mobsf_endpoint": "172.22.21.51:8000",
    "rootavd_path": "",
}


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log(message: str) -> None:
    """Append a timestamped message to the log file and print to terminal."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {message}"
    log_dir = os.path.dirname(LOG_FILE)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(formatted + "\n")
    print(formatted, flush=True)


def write_hash_manifests(extraction_dir: str) -> None:
    """Write MD5 and SHA-256 manifests for all files in an extraction directory."""
    manifest_names = {"md5_hashes.txt", "sha256_hashes.txt"}
    files: list[tuple[str, str]] = []

    for root, dirs, filenames in os.walk(extraction_dir):
        dirs.sort()
        for filename in sorted(filenames):
            if root == extraction_dir and filename in manifest_names:
                continue
            path = os.path.join(root, filename)
            if os.path.isfile(path):
                relative_path = os.path.relpath(path, extraction_dir).replace(os.sep, "/")
                files.append((relative_path, path))

    md5_lines: list[str] = []
    sha256_lines: list[str] = []
    for relative_path, path in files:
        md5_hash = hashlib.md5(usedforsecurity=False)
        sha256_hash = hashlib.sha256()
        try:
            with open(path, "rb") as extracted_file:
                while chunk := extracted_file.read(1024 * 1024):
                    md5_hash.update(chunk)
                    sha256_hash.update(chunk)
        except OSError as exc:
            log(f"Hashing failed for {path}: {exc}")
            raise

        md5_lines.append(f"{md5_hash.hexdigest()}  {relative_path}\n")
        sha256_lines.append(f"{sha256_hash.hexdigest()}  {relative_path}\n")

    try:
        with open(os.path.join(extraction_dir, "md5_hashes.txt"), "w", encoding="utf-8") as md5_file:
            md5_file.writelines(md5_lines)
        with open(os.path.join(extraction_dir, "sha256_hashes.txt"), "w", encoding="utf-8") as sha256_file:
            sha256_file.writelines(sha256_lines)
    except OSError as exc:
        log(f"Could not write hash manifests in {extraction_dir}: {exc}")
        raise

    log(f"Hash manifests created in {extraction_dir}: {len(files)} file(s)")


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------

def load_prefs() -> dict:
    log("Loading preferences...")
    default_prefs = dict(DEFAULT_PREFS)
    if not default_prefs.get("output_path"):
        default_prefs["output_path"] = DEFAULT_OUTPUT_PATH

    if os.path.exists(PREFS_FILE):
        try:
            with open(PREFS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if not isinstance(loaded, dict):
                    loaded = {}
                prefs = {**default_prefs, **loaded}
                if not prefs.get("output_path"):
                    prefs["output_path"] = DEFAULT_OUTPUT_PATH
                if not prefs.get("aleapp_path"):
                    prefs["aleapp_path"] = BUNDLED_ALEAPP
                if not prefs.get("jadx_path"):
                    prefs["jadx_path"] = BUNDLED_JADX
                log(f"Preferences loaded successfully from {PREFS_FILE}: {prefs}")
                return prefs
        except (json.JSONDecodeError, OSError) as e:
            log(f"Error reading preferences from {PREFS_FILE}: {e}. Falling back to defaults.")
            pass
    log(f"Using default preferences: {default_prefs}")
    return default_prefs


def save_prefs(prefs: dict) -> None:
    log(f"Saving preferences: {prefs}")
    try:
        with open(PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2)
        log(f"Preferences successfully saved to {PREFS_FILE}")
    except OSError as e:
        log(f"Failed to save preferences to {PREFS_FILE}: {e}")


# ---------------------------------------------------------------------------
# ADB / Shell helpers
# ---------------------------------------------------------------------------

CURRENT_DEVICE: str | None = None
ROOT_METHODS: dict[str, str] = {}

ACTIVE_SUBPROCESSES: list[subprocess.Popen] = []
SUBPROCESS_LOCK = threading.Lock()
IS_CANCELLED = False


def set_cancelled(val: bool) -> None:
    global IS_CANCELLED
    IS_CANCELLED = val
    log(f"Task cancellation flag set to: {val}")


def is_cancelled() -> bool:
    return IS_CANCELLED


def register_process(proc: subprocess.Popen) -> None:
    with SUBPROCESS_LOCK:
        ACTIVE_SUBPROCESSES.append(proc)
        log(f"Registered active subprocess pid={proc.pid}. Total active processes: {len(ACTIVE_SUBPROCESSES)}")


def unregister_process(proc: subprocess.Popen) -> None:
    with SUBPROCESS_LOCK:
        if proc in ACTIVE_SUBPROCESSES:
            ACTIVE_SUBPROCESSES.remove(proc)
            log(f"Unregistered subprocess pid={proc.pid}. Total active processes: {len(ACTIVE_SUBPROCESSES)}")


def cancel_active_tasks() -> None:
    set_cancelled(True)
    log("User requested task cancellation. Terminating active background subprocesses...")
    with SUBPROCESS_LOCK:
        log(f"Found {len(ACTIVE_SUBPROCESSES)} active subprocess(es) to terminate.")
        for proc in ACTIVE_SUBPROCESSES:
            try:
                log(f"Terminating subprocess pid={proc.pid}...")
                if os.name != 'nt':
                    # Kill process group to stop both shell and actual adb/other child processes
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    log(f"Sent SIGKILL to process group of pid={proc.pid}")
                else:
                    proc.terminate()
                    proc.kill()
                    log(f"Terminated/killed process pid={proc.pid}")
            except Exception as e:
                log(f"Error terminating process group for pid={proc.pid}: {e}")
        ACTIVE_SUBPROCESSES.clear()


def run_tracked_subprocess(cmd: list[str] | str, shell: bool = False, timeout: float | None = None) -> tuple[int, bytes]:
    """Runs a subprocess, registers it for cancellation, and returns (returncode, stdout)."""
    log(f"Launching subprocess: command={cmd!r}, shell={shell}, timeout={timeout}")
    kwargs = {}
    if os.name != 'nt':
        kwargs['preexec_fn'] = os.setsid
        
    proc = subprocess.Popen(
        cmd,
        shell=shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        **kwargs
    )
    log(f"Subprocess successfully spawned with pid={proc.pid}")
    register_process(proc)
    try:
        stdout, _ = proc.communicate(timeout=timeout)
        log(f"Subprocess completed: pid={proc.pid}, returncode={proc.returncode}, output={len(stdout)} bytes")
        return proc.returncode, stdout
    except subprocess.TimeoutExpired:
        log(f"Subprocess timeout expired: pid={proc.pid}, command={cmd!r}")
        if os.name != 'nt':
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                log(f"Sent SIGKILL to process group of pid={proc.pid}")
            except OSError as e:
                log(f"Failed to kill process group for pid={proc.pid}: {e}")
        else:
            proc.kill()
            log(f"Killed subprocess: pid={proc.pid}")
        stdout, _ = proc.communicate()
        raise subprocess.TimeoutExpired(cmd, timeout, output=stdout)
    finally:
        unregister_process(proc)


def set_current_device(device_id: str | None) -> None:
    global CURRENT_DEVICE
    if device_id == "None":
        CURRENT_DEVICE = None
    else:
        CURRENT_DEVICE = device_id


def get_current_device() -> str | None:
    return CURRENT_DEVICE


def list_adb_devices() -> list[str]:
    """Returns a list of connected device IDs from `adb devices`."""
    try:
        output = subprocess.check_output([ADB_COMMAND, "devices"], stderr=subprocess.STDOUT)
        lines = output.decode("utf-8", errors="replace").splitlines()
        devices = []
        for line in lines[1:]:
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        return devices
    except Exception as e:
        log(f"Failed to list adb devices: {e}")
        return []


def _run_adb_shell(command: str, root_method: str = "shell") -> tuple[int, bytes]:
    """Run an ADB shell command using the requested root method."""
    if not CURRENT_DEVICE:
        return 1, b"No device selected"

    cmd = [ADB_COMMAND, "-s", CURRENT_DEVICE, "shell"]
    if root_method == "su_c":
        cmd.extend(["su", "-c", command])
    elif root_method == "su_0_c":
        cmd.extend(["su", "0", "-c", command])
    elif root_method == "su_0":
        cmd.extend(["su", "0", command])
    else:
        cmd.append(command)
    return run_tracked_subprocess(cmd, timeout=60)


def _detect_root_method() -> str:
    """Detect one usable root command form for the current device."""
    if not CURRENT_DEVICE:
        return "NONE"
    if CURRENT_DEVICE in ROOT_METHODS:
        return ROOT_METHODS[CURRENT_DEVICE]

    def works(method: str) -> bool:
        try:
            code, output = _run_adb_shell("id", method)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        return code == 0 and "uid=0" in output.decode("utf-8", errors="replace")

    # `adb root` is harmless on production devices and enables direct exec-out
    # acquisition on userdebug emulators when supported.
    try:
        run_tracked_subprocess([ADB_COMMAND, "-s", CURRENT_DEVICE, "root"], timeout=15)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    for method in ("shell_root", "su_c", "su_0_c", "su_0"):
        if works(method):
            ROOT_METHODS[CURRENT_DEVICE] = method
            log(f"Root method detected for {CURRENT_DEVICE}: {method}")
            return method

    ROOT_METHODS[CURRENT_DEVICE] = "NONE"
    log(f"No usable root method detected for {CURRENT_DEVICE}.")
    return "NONE"


def is_android_virtual_device() -> bool:
    """Return whether the selected ADB target identifies as an Android emulator."""
    if not CURRENT_DEVICE:
        return False
    if CURRENT_DEVICE.startswith("emulator-"):
        return True
    try:
        code, output = _run_adb_shell("getprop ro.kernel.qemu")
        return code == 0 and output.decode("utf-8", errors="replace").strip() == "1"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def adb_shell(command: str) -> str | None:
    """Run a shell command without root and return stdout."""
    if not CURRENT_DEVICE:
        return None
    try:
        code, output = _run_adb_shell(command)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return output.decode("utf-8", errors="replace") if code == 0 else None


def find_selected_avd_ramdisk() -> str | None:
    """Resolve the selected emulator's system-image ramdisk from its AVD config."""
    if not is_android_virtual_device():
        return None
    avd_name = ""
    for property_name in ("ro.boot.qemu.avd_name", "ro.kernel.qemu.avd_name"):
        avd_name = (adb_shell(f"getprop {property_name}") or "").strip()
        if avd_name:
            break
    if not avd_name:
        log("Could not determine the selected emulator's AVD name.")
        return None

    android_user_home = os.environ.get("ANDROID_USER_HOME", os.path.expanduser("~/.android"))
    avd_roots = [
        os.environ.get("ANDROID_AVD_HOME", ""),
        os.path.join(os.environ["ANDROID_EMULATOR_HOME"], "avd")
        if os.environ.get("ANDROID_EMULATOR_HOME") else "",
        os.path.join(android_user_home, "avd"),
        os.path.expanduser("~/.android/avd"),
        os.path.expanduser("~/snap/android-studio/common/.android/avd"),
        os.path.expanduser("~/.var/app/com.google.AndroidStudio/config/.android/avd"),
    ]
    config_path = ""
    for avd_root in dict.fromkeys(os.path.abspath(path) for path in avd_roots if path):
        direct_config = os.path.join(avd_root, f"{avd_name}.avd", "config.ini")
        if os.path.isfile(direct_config):
            config_path = direct_config
            break
        pointer_path = os.path.join(avd_root, f"{avd_name}.ini")
        try:
            with open(pointer_path, encoding="utf-8") as pointer_file:
                pointer = dict(
                    line.strip().split("=", 1) for line in pointer_file
                    if "=" in line and not line.lstrip().startswith("#")
                )
            avd_path = os.path.expanduser(pointer.get("path", ""))
            if avd_path and not os.path.isabs(avd_path):
                avd_path = os.path.join(avd_root, avd_path)
            candidate = os.path.join(avd_path, "config.ini")
            if avd_path and os.path.isfile(candidate):
                config_path = candidate
                break
        except OSError:
            continue

    if not config_path:
        return _find_ramdisk_by_running_image(avd_name)

    try:
        with open(config_path, encoding="utf-8") as config_file:
            config = dict(
                line.strip().split("=", 1) for line in config_file
                if "=" in line and not line.lstrip().startswith("#")
            )
    except OSError as exc:
        log(f"Could not read AVD config for {avd_name}: {exc}")
        return None

    system_dir = config.get("image.sysdir.1", "").strip().strip("/")
    if not system_dir:
        log(f"AVD config for {avd_name} has no image.sysdir.1 entry.")
        return None
    if system_dir.startswith("system-images/"):
        system_dir = system_dir[len("system-images/"):]
    configured_sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    sdk_roots = [configured_sdk] if configured_sdk else [os.path.expanduser("~/Android/Sdk")]
    for sdk_root in sdk_roots:
        if not sdk_root:
            continue
        image_dir = os.path.join(sdk_root, "system-images", system_dir)
        for filename in ("ramdisk.img", "ramdisk-qemu.img"):
            ramdisk_path = os.path.join(image_dir, filename)
            if os.path.isfile(ramdisk_path):
                log(f"Resolved RootAVD ramdisk for {avd_name}: {ramdisk_path}")
                return ramdisk_path

    log(f"Could not find a ramdisk image for AVD {avd_name} ({system_dir}).")
    return None


def _find_ramdisk_by_running_image(avd_name: str) -> str | None:
    """Fall back to one unambiguous SDK image matching the running emulator."""
    api_level = (adb_shell("getprop ro.build.version.sdk") or "").strip()
    abi = (adb_shell("getprop ro.product.cpu.abi") or "").strip()
    if not api_level or not abi:
        log(f"Could not determine API level and ABI for AVD {avd_name}.")
        return None

    configured_sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    sdk_roots = [configured_sdk] if configured_sdk else [os.path.expanduser("~/Android/Sdk")]
    candidates = []
    for sdk_root in sdk_roots:
        image_root = os.path.join(sdk_root, "system-images", f"android-{api_level}")
        if not os.path.isdir(image_root):
            continue
        for tag in os.listdir(image_root):
            image_dir = os.path.join(image_root, tag, abi)
            for filename in ("ramdisk.img", "ramdisk-qemu.img"):
                ramdisk_path = os.path.join(image_dir, filename)
                if os.path.isfile(ramdisk_path):
                    candidates.append(ramdisk_path)

    if len(candidates) == 1:
        log(f"Resolved RootAVD ramdisk by API/ABI fallback for {avd_name}: {candidates[0]}")
        return candidates[0]
    if candidates:
        log(f"Could not safely choose one ramdisk for {avd_name}; matching images: {candidates}")
    else:
        log(f"No SDK ramdisk matches AVD {avd_name} (API {api_level}, ABI {abi}).")
    return None


def has_root_access() -> bool:
    """Return whether a supported root interface is available on the selected device."""
    return _detect_root_method() != "NONE"


def launch_rootavd(rootavd_path: str, ramdisk_path: str) -> bool:
    """Launch RootAVD in a terminal to patch a running Android Studio AVD."""
    if not os.path.isfile(rootavd_path):
        log(f"RootAVD script not found: {rootavd_path}")
        return False
    if not os.path.isfile(ramdisk_path):
        log(f"AVD ramdisk image not found: {ramdisk_path}")
        return False

    marker = f"{os.sep}system-images{os.sep}"
    absolute_ramdisk = os.path.abspath(ramdisk_path)
    if marker not in absolute_ramdisk:
        log(f"Could not determine Android SDK root from ramdisk path: {ramdisk_path}")
        return False
    sdk_root, image_suffix = absolute_ramdisk.split(marker, 1)
    rootavd_ramdisk = f"system-images/{image_suffix.replace(os.sep, '/')}"

    terminal = shutil.which("x-terminal-emulator") or shutil.which("gnome-terminal") or shutil.which("xterm")
    if not terminal:
        log("Could not launch RootAVD: no supported terminal emulator was found.")
        return False

    rootavd_dir = os.path.dirname(os.path.abspath(rootavd_path))
    command = (
        f"export ANDROID_HOME={shlex.quote(sdk_root)}; "
        "export PATH=\"$ANDROID_HOME/platform-tools:$PATH\"; "
        f"cd {shlex.quote(rootavd_dir)} && bash {shlex.quote(rootavd_path)} {shlex.quote(rootavd_ramdisk)}; "
        "status=$?; printf '\\nRootAVD finished with status %s. Press Enter to close.\\n' \"$status\"; read _"
    )
    try:
        subprocess.Popen([terminal, "-e", "bash", "-lc", command], start_new_session=True)
    except OSError as exc:
        log(f"Could not launch RootAVD: {exc}")
        return False

    if CURRENT_DEVICE:
        ROOT_METHODS.pop(CURRENT_DEVICE, None)
    log(f"Launched RootAVD for ramdisk image: {ramdisk_path}")
    return True


def _root_exec_out_command(remote_command: str) -> str | None:
    """Build a shell command that streams a root command through adb exec-out."""
    if not CURRENT_DEVICE:
        log("ADB exec-out aborted: no device selected.")
        return None
    method = _detect_root_method()
    if method == "NONE":
        log("ADB exec-out aborted: no usable root method detected.")
        return None

    adb_cmd = f"{shlex.quote(ADB_COMMAND)} -s {shlex.quote(CURRENT_DEVICE)} exec-out"
    if method == "su_c":
        return f"{adb_cmd} su -c {shlex.quote(remote_command)}"
    if method == "su_0_c":
        return f"{adb_cmd} su 0 -c {shlex.quote(remote_command)}"
    if method == "su_0":
        return f"{adb_cmd} su 0 {shlex.quote(remote_command)}"
    return f"{adb_cmd} {shlex.quote(remote_command)}"


def _adb_exec_out_command(remote_command: str) -> str | None:
    """Build an adb exec-out command without requiring root."""
    if not CURRENT_DEVICE:
        log("ADB exec-out aborted: no device selected.")
        return None
    adb_cmd = f"{shlex.quote(ADB_COMMAND)} -s {shlex.quote(CURRENT_DEVICE)} exec-out"
    return f"{adb_cmd} {shlex.quote(remote_command)}"


def adb_shell_su(command: str) -> str | None:
    """Run a command with a detected root method. Returns stdout or None on error."""
    if not CURRENT_DEVICE:
        log(f"ADB command aborted: no device selected — {command!r}")
        return None
    method = _detect_root_method()
    if method == "NONE":
        log(f"ADB command aborted: no usable root method — {command!r}")
        return None
    try:
        code, output = _run_adb_shell(command, method)
        if code != 0:
            log(f"ADB command failed: {command!r} — code {code}, output: {output.decode('utf-8', errors='replace')}")
            return None
        return output.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        log(f"ADB command timed out: {command!r}")
        return None
    except FileNotFoundError:
        log("adb executable not found. Ensure ADB is installed and on PATH.")
        return None


def adb_pull(remote: str, local: str | None = None) -> bool:
    """Pull a path from the device. Returns True on success."""
    if not CURRENT_DEVICE:
        log(f"adb pull aborted: no device selected — {remote}")
        return False
    cmd = [ADB_COMMAND, "-s", CURRENT_DEVICE, "pull", remote]
    if local:
        cmd.append(local)
    try:
        code, output = run_tracked_subprocess(cmd, timeout=300)
        if code != 0:
            log(f"adb pull failed: code {code}, output: {output.decode('utf-8', errors='replace')}")
            return False
        return True
    except Exception as e:
        log(f"adb pull failed: {e}")
        return False


def shell_local(command: str, timeout: float | None = None) -> str | None:
    """Run a local shell command. Returns stdout or None on error."""
    try:
        code, output = run_tracked_subprocess(command, shell=True, timeout=timeout)
        if code != 0:
            log(f"Local command failed: {command!r} — code {code}")
            return None
        return output.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        log(f"Local command timed out: {command!r}")
        return None


def get_cwd() -> str:
    """Return the current working directory."""
    return os.getcwd()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _device_temp_folder(name: str) -> str:
    return f"/sdcard/Download/{name}"


def write_acquisition_metadata(extraction_dir: str, packages: list[str] | None = None) -> None:
    """Record device and package details alongside the acquired evidence."""
    def shell(command: str) -> str:
        try:
            code, output = _run_adb_shell(command)
            return output.decode("utf-8", errors="replace").strip() if code == 0 else ""
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ""

    package_details = {}
    for package in packages or []:
        details = shell(f"dumpsys package {shlex.quote(package)}")
        version = next(
            (line.split("=", 1)[1].strip() for line in details.splitlines()
             if "versionName=" in line),
            "",
        )
        package_details[package] = {"version_name": version}

    metadata = {
        "acquired_at": datetime.now().isoformat(timespec="seconds"),
        "device_serial": CURRENT_DEVICE,
        "root_method": _detect_root_method(),
        "device": {
            "brand": shell("getprop ro.product.brand"),
            "model": shell("getprop ro.product.model"),
            "android_version": shell("getprop ro.build.version.release"),
            "build_fingerprint": shell("getprop ro.build.fingerprint"),
        },
        "packages": package_details,
    }
    with open(os.path.join(extraction_dir, "acquisition_metadata.json"), "w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=2)
    log(f"Acquisition metadata created in {extraction_dir}")


def write_device_sha256_manifest(
    paths: list[str], extraction_dir: str, require_root: bool = True
) -> None:
    """Save SHA-256 hashes calculated on the device before evidence transfer."""
    if not paths:
        return
    quoted_paths = " ".join(shlex.quote(path) for path in paths)
    remote_command = (
        f"find {quoted_paths} -type f -exec sha256sum {{}} + 2>/dev/null"
    )
    adb_command = (
        _root_exec_out_command(remote_command)
        if require_root else _adb_exec_out_command(remote_command)
    )
    if not adb_command:
        return

    manifest = os.path.join(extraction_dir, "device_sha256.txt")
    shell_local(f"{adb_command} > {shlex.quote(manifest)}")
    if os.path.exists(manifest):
        log(f"Device-side SHA-256 manifest created in {extraction_dir}")


def _pull_folder(remote: str, local_base: str | None) -> str:
    """Pull remote folder to local_base (or user home folder). Returns the local destination."""
    dest = local_base if local_base else os.path.expanduser("~")
    adb_pull(remote, dest)
    folder_name = remote.rstrip("/").split("/")[-1]
    return os.path.join(dest, folder_name)


def get_last_log_line() -> str:
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return lines[-1].strip() if lines else ""
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Device listing helpers (used by the GUI to populate checklists)
# ---------------------------------------------------------------------------

def find_files_on_device(query: str) -> list[str]:
    """Find all files on the device matching the query string under /data and /sdcard."""
    if not query:
        return []
    cmd = f"find /data /sdcard -name '*{query}*' 2>/dev/null"
    log(f"Searching for files matching '{query}': {cmd}")
    result = adb_shell_su(cmd)
    if not result:
        result = adb_shell(f"find /sdcard -name '*{query}*' 2>/dev/null")
    if result:
        return sorted(line.strip() for line in result.split("\n") if line.strip())
    return []


def extract_files_from_device(selected: list[str], output_path: str | None) -> str | None:
    """
    Extract selected files/folders from the device to the PC using root tar streaming.
    Recreates the directory structure locally and bypasses permission restrictions.
    """
    if not selected:
        return None

    folder_name = f"search_extraction_{_timestamp()}"
    base = output_path if output_path else os.path.expanduser("~")
    local_dir = os.path.join(base, folder_name)
    os.makedirs(local_dir, exist_ok=True)

    if not has_root_access():
        for remote_path in selected:
            if not remote_path.startswith("/sdcard/") or not adb_pull(remote_path, local_dir):
                log(f"Non-root extraction skipped inaccessible path: {remote_path}")
        write_acquisition_metadata(local_dir)
        write_hash_manifests(local_dir)
        log(f"Non-root public file extraction complete -> {local_dir}")
        return local_dir

    local_archive = os.path.join(local_dir, "search_extract.tar")
    # Quote each path to handle spaces or special characters safely
    quoted_paths = " ".join(shlex.quote(p) for p in selected)

    # Stream the tar archive directly from the phone to the PC using su for root access
    remote_command = f"stty raw 2>/dev/null; tar -cf - {quoted_paths} 2>/dev/null"
    adb_command = _root_exec_out_command(remote_command)
    if not adb_command:
        return None
    cmd = f"{adb_command} > {shlex.quote(local_archive)}"
    log(f"Streaming searched files to local tar: {cmd}")
    write_device_sha256_manifest(selected, local_dir)
    shell_local(cmd)

    if is_cancelled():
        import shutil
        if os.path.exists(local_dir):
            try:
                shutil.rmtree(local_dir)
            except OSError:
                pass
        log("Search file extraction cancelled: cleaned up local files.")
        return None

    # Extract locally on the PC
    if os.path.exists(local_archive) and os.path.getsize(local_archive) > 0:
        log(f"Extracting local search tar: {local_archive}")
        write_acquisition_metadata(local_dir)
        extract_cmd = f'tar -xf "{local_archive}" -C "{local_dir}"'
        shell_local(extract_cmd)
        try:
            os.remove(local_archive)
        except OSError:
            pass
        write_hash_manifests(local_dir)
        log(f"Search file extraction complete -> {local_dir}")
        return local_dir
    else:
        try:
            os.remove(local_archive)
        except OSError:
            pass
        log("Search file extraction failed: no data received or file not found.")
        return None


def list_private_packages() -> list[str]:
    """Return sorted list of package names under /data/data/."""
    result = adb_shell_su("ls /data/data/")
    if result:
        return sorted(line for line in result.split("\n") if line.strip())
    return []


def list_apk_packages() -> tuple[list[str], dict[str, str]]:
    """
    Return (sorted display labels, apk_dir_map) for all installed APKs.

    Modern Android (API 29+) structure:
      /data/app/~~<scrambled>==/com.example.app-<hash>/base.apk

    Older Android structure:
      /data/app/com.example.app-<hash>/base.apk

    Strategy: `find` every base.apk up to 3 levels deep, strip the filename
    to get the package dir, then parse the clean package name from the last
    path component by removing the trailing -<hash> suffix.

    Returns:
        labels      — sorted list of clean package names for display
        apk_dir_map — maps display label → absolute device path of the
                      directory that contains base.apk
    """
    result = adb_shell_su(
        "find /data/app -maxdepth 3 -name base.apk 2>/dev/null | sed 's|/base.apk||g'"
    )
    if not result:
        result = adb_shell("pm list packages -f")
        if not result:
            return [], {}
        apk_dir_map = {}
        labels = []
        for line in result.splitlines():
            if not line.startswith("package:") or "=" not in line:
                continue
            apk_path, package = line[8:].rsplit("=", 1)
            display = package
            count = 1
            while display in apk_dir_map:
                count += 1
                display = f"{package} ({count})"
            apk_dir_map[display] = f"APK:{apk_path}"
            labels.append(display)
        return sorted(labels), apk_dir_map

    apk_dir_map: dict[str, str] = {}
    labels: list[str] = []

    for line in result.strip().split("\n"):
        pkg_dir = line.strip()
        if not pkg_dir or "base.apk" in pkg_dir:
            continue

        # Last component is e.g. com.example.app-XYZ123
        last = pkg_dir.rstrip("/").split("/")[-1]

        # Strip the trailing -<hash>: hashes never contain dots,
        # valid package names always do.
        parts = last.rsplit("-", 1)
        pkg = parts[0] if len(parts) == 2 and "." in parts[0] else last

        # Deduplicate (split APKs / multiple users)
        display = pkg
        count = 1
        while display in apk_dir_map:
            count += 1
            display = f"{pkg} ({count})"

        apk_dir_map[display] = pkg_dir
        labels.append(display)

    return sorted(labels), apk_dir_map


def list_public_packages() -> list[str]:
    """Return sorted list of package names under /sdcard/Android/data/."""
    result = adb_shell_su("ls /sdcard/Android/data/")
    if not result:
        result = adb_shell("ls /sdcard/Android/data/")
    if result:
        return sorted(line for line in result.split("\n") if line.strip())
    return []


# ---------------------------------------------------------------------------
# Extraction — Private Data
# ---------------------------------------------------------------------------

def extract_private_data(selected: list[str], output_path: str | None) -> str | None:
    """
    Extract /data/data/<pkg> for each selected package by streaming tar directly to the PC.
    Uses 0 extra space on the phone.
    """
    if not selected:
        return None

    folder_name = f"private_data_{_timestamp()}"
    base = output_path if output_path else os.path.expanduser("~")
    local_dir = os.path.join(base, folder_name)
    os.makedirs(local_dir, exist_ok=True)

    write_device_sha256_manifest([f"/data/data/{pkg}" for pkg in selected], local_dir)
    for pkg in selected:
        if is_cancelled():
            break
        local_archive = os.path.join(local_dir, f"{pkg}.tar")
        
        # Stream the tar archive directly from the phone to a local tar file on the PC
        remote_command = f"stty raw 2>/dev/null; tar -cf - {shlex.quote(f'/data/data/{pkg}')} 2>/dev/null"
        adb_command = _root_exec_out_command(remote_command)
        if not adb_command:
            break
        cmd = f"{adb_command} > {shlex.quote(local_archive)}"
        log(f"Streaming /data/data/{pkg} to local tar")
        shell_local(cmd)

        if is_cancelled():
            break

        # Extract locally on the PC
        if os.path.exists(local_archive) and os.path.getsize(local_archive) > 0:
            log(f"Extracting local tar: {local_archive}")
            extract_cmd = f'tar -xf "{local_archive}" -C "{local_dir}"'
            shell_local(extract_cmd)
            try:
                os.remove(local_archive)
            except OSError:
                pass

    if is_cancelled():
        import shutil
        if os.path.exists(local_dir):
            try:
                shutil.rmtree(local_dir)
            except OSError:
                pass
        log("Private extraction cancelled: cleaned up local files.")
        return None

    write_acquisition_metadata(local_dir, selected)
    write_hash_manifests(local_dir)
    log(f"Private extraction complete → {local_dir}")
    return local_dir


# ---------------------------------------------------------------------------
# Extraction — APK Files
# ---------------------------------------------------------------------------

def extract_apk_files(
    selected: list[str],
    apk_dir_map: dict[str, str],
    output_path: str | None,
) -> tuple[str, list[str]]:
    """
    Extract ALL contents of each selected package's APK directory by streaming tar to the PC.
    Uses 0 extra space on the phone.
    """
    folder_name = f"apk_files_{_timestamp()}"
    base = output_path if output_path else os.path.expanduser("~")
    local_base = os.path.join(base, folder_name)
    os.makedirs(local_base, exist_ok=True)

    if not has_root_access():
        extracted = []
        for package in selected:
            apk_path = apk_dir_map.get(package, "")
            if not apk_path.startswith("APK:"):
                continue
            package_dir = os.path.join(local_base, package)
            os.makedirs(package_dir, exist_ok=True)
            if adb_pull(apk_path[4:], package_dir):
                extracted.append(package)
        write_acquisition_metadata(local_base, [pkg.rsplit(" (", 1)[0] for pkg in extracted])
        write_hash_manifests(local_base)
        log(f"Non-root APK extraction complete → {local_base}")
        return local_base, extracted

    extracted = []
    write_device_sha256_manifest(list(apk_dir_map[pkg] for pkg in selected if pkg in apk_dir_map), local_base)
    for pkg in selected:
        if is_cancelled():
            break
        pkg_dir = apk_dir_map.get(pkg)
        if not pkg_dir:
            log(f"APK: no device directory mapped for '{pkg}', skipping.")
            continue

        local_pkg_dir = os.path.join(local_base, pkg)
        os.makedirs(local_pkg_dir, exist_ok=True)
        local_archive = os.path.join(local_pkg_dir, "pkg.tar")

        # Stream the tar archive of the APK directory directly from the phone to the PC
        remote_command = f"stty raw 2>/dev/null; tar -cf - -C {shlex.quote(pkg_dir)} . 2>/dev/null"
        adb_command = _root_exec_out_command(remote_command)
        if not adb_command:
            break
        cmd = f"{adb_command} > {shlex.quote(local_archive)}"
        log(f"Streaming APK directory for {pkg} to local tar")
        shell_local(cmd)

        if is_cancelled():
            break

        # Extract locally on the PC
        if os.path.exists(local_archive) and os.path.getsize(local_archive) > 0:
            log(f"Extracting local APK tar: {local_archive}")
            extract_cmd = f'tar -xf "{local_archive}" -C "{local_pkg_dir}"'
            shell_local(extract_cmd)
            try:
                os.remove(local_archive)
            except OSError:
                pass
            extracted.append(pkg)

    if is_cancelled():
        import shutil
        if os.path.exists(local_base):
            try:
                shutil.rmtree(local_base)
            except OSError:
                pass
        log("APK extraction cancelled by user: output cleaned up.")
        return local_base, []

    write_acquisition_metadata(local_base, [pkg.rsplit(" (", 1)[0] for pkg in extracted])
    write_hash_manifests(local_base)
    log(f"APK extraction complete → {local_base}")
    return local_base, extracted


# ---------------------------------------------------------------------------
# Extraction — Public Data
# ---------------------------------------------------------------------------

def extract_public_data(selected: list[str], output_path: str | None) -> str | None:
    """
    Extract /sdcard/Android/data/<pkg> for each selected package by streaming tar to the PC.
    Uses 0 extra space on the phone.
    """
    if not selected:
        return None

    folder_name = f"public_data_{_timestamp()}"
    base = output_path if output_path else os.path.expanduser("~")
    local_dir = os.path.join(base, folder_name)
    os.makedirs(local_dir, exist_ok=True)

    if not has_root_access():
        for package in selected:
            adb_pull(f"/sdcard/Android/data/{package}", local_dir)
        write_acquisition_metadata(local_dir, selected)
        write_hash_manifests(local_dir)
        log(f"Non-root public extraction complete → {local_dir}")
        return local_dir

    write_device_sha256_manifest([f"/sdcard/Android/data/{pkg}" for pkg in selected], local_dir)
    for pkg in selected:
        if is_cancelled():
            break
        local_archive = os.path.join(local_dir, f"{pkg}.tar")
        
        # Stream the tar archive directly from the phone to the PC
        remote_command = f"stty raw 2>/dev/null; tar -cf - {shlex.quote(f'/sdcard/Android/data/{pkg}')} 2>/dev/null"
        adb_command = _root_exec_out_command(remote_command)
        if not adb_command:
            break
        cmd = f"{adb_command} > {shlex.quote(local_archive)}"
        log(f"Streaming /sdcard/Android/data/{pkg} to local tar")
        shell_local(cmd)

        if is_cancelled():
            break

        # Extract locally on the PC
        if os.path.exists(local_archive) and os.path.getsize(local_archive) > 0:
            log(f"Extracting local tar: {local_archive}")
            extract_cmd = f'tar -xf "{local_archive}" -C "{local_dir}"'
            shell_local(extract_cmd)
            try:
                os.remove(local_archive)
            except OSError:
                pass

    if is_cancelled():
        import shutil
        if os.path.exists(local_dir):
            try:
                shutil.rmtree(local_dir)
            except OSError:
                pass
        log("Public extraction cancelled: cleaned up local files.")
        return None

    write_acquisition_metadata(local_dir, selected)
    write_hash_manifests(local_dir)
    log(f"Public extraction complete → {local_dir}")
    return local_dir


# ---------------------------------------------------------------------------
# Extraction — All Data
# ---------------------------------------------------------------------------

def full_device_dump(output_path: str | None) -> str | None:
    base = output_path if output_path else os.path.expanduser("~")
    folder_name = f"full_system_dump_{_timestamp()}"
    local_dir = os.path.join(base, folder_name)
    os.makedirs(local_dir, exist_ok=True)
    local_file = os.path.join(local_dir, f"{folder_name}.tar")

    rooted = has_root_access()
    if rooted:
        dump_paths = ["/data", "/sdcard", "/data_mirror"]
        write_device_sha256_manifest(dump_paths, local_dir)
        remote_command = (
            "stty raw 2>/dev/null; paths='/data /sdcard'; "
            "[ -d /data_mirror ] && paths=\"$paths /data_mirror\"; tar -cf - $paths 2>/dev/null"
        )
        adb_command = _root_exec_out_command(remote_command)
        dump_kind = "full system"
    else:
        # ADB shell can acquire shared storage but cannot lawfully read /data.
        dump_paths = ["/sdcard"]
        write_device_sha256_manifest(dump_paths, local_dir, require_root=False)
        remote_command = "stty raw 2>/dev/null; tar -cf - /sdcard 2>/dev/null"
        adb_command = _adb_exec_out_command(remote_command)
        dump_kind = "accessible shared-storage"
    if not adb_command:
        return None
    cmd = f"{adb_command} > {shlex.quote(local_file)}"
    log(f"Starting {dump_kind} dump: {cmd}")
    shell_local(cmd)

    if is_cancelled():
        if os.path.exists(local_dir):
            try:
                import shutil
                shutil.rmtree(local_dir)
            except OSError:
                pass
        log("Full system dump cancelled by user: extraction folder removed.")
        return None

    if os.path.exists(local_file) and os.path.getsize(local_file) > 0:
        write_acquisition_metadata(local_dir)
        write_hash_manifests(local_dir)
        log(f"Full logical dump complete → {local_file}")
        return local_file
    else:
        log("Full logical dump failed (output file empty or not found).")
        return None


def extract_full_dump_for_aleapp(dump_archive: str) -> str | None:
    """Extract a full-dump archive to a filesystem directory for ALEAPP."""
    input_dir = os.path.join(
        os.path.dirname(dump_archive), f"aleapp_input_{_timestamp()}"
    )
    os.makedirs(input_dir, exist_ok=True)

    try:
        with tarfile.open(dump_archive) as archive:
            for member in archive:
                member_path = os.path.abspath(os.path.join(input_dir, member.name))
                if (
                    not member_path.startswith(os.path.abspath(input_dir) + os.sep)
                    or not (member.isdir() or member.isreg())
                ):
                    log(f"Skipping unsafe full-dump archive member: {member.name}")
                    continue
                # The dump records Android's restrictive ownership and modes.
                # This is an ALEAPP working copy; keep its directories readable.
                archive.extract(member, input_dir, set_attrs=False)
    except (OSError, tarfile.TarError) as exc:
        shutil.rmtree(input_dir, ignore_errors=True)
        log(f"Could not extract full dump for ALEAPP: {exc}")
        return None

    if is_cancelled():
        shutil.rmtree(input_dir, ignore_errors=True)
        log("Full-dump ALEAPP input preparation cancelled: extracted files removed.")
        return None

    log(f"Full dump extracted for ALEAPP → {input_dir}")
    return input_dir


# ---------------------------------------------------------------------------
# Analysis — ALEAPP
# ---------------------------------------------------------------------------

def run_aleapp(aleapp_path: str, input_folder: str) -> None:
    """Run the bundled or configured ALEAPP and open its HTML report."""
    aleapp_path = aleapp_path or BUNDLED_ALEAPP
    if not aleapp_path or not os.path.isfile(aleapp_path):
        log(f"ALEAPP executable not found: {aleapp_path or '(not configured)'}")
        return

    analysis_base = os.path.join(
        os.path.dirname(input_folder), f"aleapp_analysis_{_timestamp()}"
    )
    os.makedirs(analysis_base, exist_ok=True)
    cmd = [
        sys.executable,
        aleapp_path,
        "-t", "fs",
        "-i", input_folder,
        "-o", analysis_base,
    ]
    log(f"Running ALEAPP: {cmd}")
    try:
        code, output = run_tracked_subprocess(cmd, timeout=1800)
    except subprocess.TimeoutExpired:
        log("ALEAPP timed out.")
        return

    if code != 0:
        log(f"ALEAPP failed with exit code {code}: {output.decode('utf-8', errors='replace')}")
        return

    for root, _dirs, files in os.walk(analysis_base):
        if "index.html" in files:
            report = os.path.join(root, "index.html")
            log(f"Opening report: {report}")
            webbrowser.open_new_tab(report)
            return
    log("ALEAPP completed but produced no HTML report.")


# ---------------------------------------------------------------------------
# Analysis — MobSF
# ---------------------------------------------------------------------------

def _fetch_mobsf_api_key(endpoint: str) -> str | None:
    """Scrape the MobSF API key from the api_docs page."""
    try:
        resp = requests.get(f"http://{endpoint}/api_docs", timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        code = soup.find("code")
        if code:
            return code.text.strip()
        log("MobSF: API key element not found on page.")
    except requests.RequestException as e:
        log(f"MobSF: Failed to fetch API key — {e}")
    return None


def run_mobsf(endpoint: str, local_base: str, pkgs: list[str]) -> None:
    """Upload and scan APKs via MobSF REST API."""
    api_key = _fetch_mobsf_api_key(endpoint)
    if not api_key:
        log("MobSF: Aborting — no API key.")
        return

    for pkg in pkgs:
        if is_cancelled():
            break
        apk_path = os.path.join(local_base, pkg, "base.apk")
        if not os.path.exists(apk_path):
            log(f"MobSF: APK not found at {apk_path}, skipping.")
            continue
        try:
            log(f"MobSF: Uploading {apk_path}")
            with open(apk_path, "rb") as apk_file:
                mp = MultipartEncoder(
                    fields={"file": (apk_path, apk_file, "application/octet-stream")}
                )
                headers = {"Content-Type": mp.content_type, "Authorization": api_key}
                upload_resp = requests.post(
                    f"http://{endpoint}/api/v1/upload",
                    data=mp,
                    headers=headers,
                    timeout=120,
                )
            upload_data = upload_resp.json()
            log(f"MobSF: Scanning {apk_path}")
            requests.post(
                f"http://{endpoint}/api/v1/scan",
                data=upload_data,
                headers={"Authorization": api_key},
                timeout=120,
            )
            file_hash = upload_data.get("hash", "")
            webbrowser.open_new_tab(f"http://{endpoint}/static_analyzer/{file_hash}/")
            log(f"MobSF: Report opened for hash {file_hash}")
        except (requests.RequestException, OSError) as e:
            log(f"MobSF: Error processing {apk_path} — {e}")


# ---------------------------------------------------------------------------
# Analysis — JADX
# ---------------------------------------------------------------------------

def run_jadx(jadx_path: str, local_base: str, pkgs: list[str]) -> None:
    """Decompile APKs using JADX."""
    jadx_path = jadx_path or BUNDLED_JADX
    if not jadx_path or not os.path.isfile(jadx_path):
        log(f"JADX executable not found: {jadx_path or '(not configured)'}")
        return

    folder_name = f"decompiled_files_{_timestamp()}"
    decompile_base = os.path.join(os.path.dirname(local_base), folder_name)
    os.makedirs(decompile_base, exist_ok=True)
    log(f"JADX: Decompiling into {decompile_base}")

    for pkg in pkgs:
        if is_cancelled():
            break
        out_dir = os.path.join(decompile_base, pkg)
        apk = os.path.join(local_base, pkg, "base.apk")
        os.makedirs(out_dir, exist_ok=True)
        cmd = [jadx_path, "-d", out_dir, apk]
        log(f"JADX: {cmd}")
        try:
            code, output = run_tracked_subprocess(cmd, timeout=1800)
        except subprocess.TimeoutExpired:
            log(f"JADX timed out for {apk}")
            continue
        if code != 0:
            log(f"JADX failed for {apk} with exit code {code}: {output.decode('utf-8', errors='replace')}")
