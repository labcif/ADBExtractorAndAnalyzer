"""
core.py — ADB Extractor & Analyser 2.0
Constants, logging, preferences, ADB helpers, and all extraction/analysis logic.
"""

import json
import os
import signal
import subprocess
import threading
import webbrowser
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from requests_toolbelt.multipart.encoder import MultipartEncoder


# ---------------------------------------------------------------------------
# Constants & Config
# ---------------------------------------------------------------------------

LOG_FILE = "logs.txt"
PREFS_FILE = "preferences.json"

DEFAULT_PREFS = {
    "aleapp_path": "",
    "output_path": "",
    "jadx_path": "",
    "mobsf_endpoint": "172.22.21.51:8000",
}


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log(message: str) -> None:
    """Append a timestamped message to the log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------

def load_prefs() -> dict:
    if os.path.exists(PREFS_FILE):
        try:
            with open(PREFS_FILE, "r", encoding="utf-8") as f:
                return {**DEFAULT_PREFS, **json.load(f)}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_PREFS)


def save_prefs(prefs: dict) -> None:
    try:
        with open(PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2)
    except OSError as e:
        log(f"Failed to save preferences: {e}")


# ---------------------------------------------------------------------------
# ADB / Shell helpers
# ---------------------------------------------------------------------------

CURRENT_DEVICE: str | None = None

ACTIVE_SUBPROCESSES: list[subprocess.Popen] = []
SUBPROCESS_LOCK = threading.Lock()
IS_CANCELLED = False


def set_cancelled(val: bool) -> None:
    global IS_CANCELLED
    IS_CANCELLED = val


def is_cancelled() -> bool:
    return IS_CANCELLED


def register_process(proc: subprocess.Popen) -> None:
    with SUBPROCESS_LOCK:
        ACTIVE_SUBPROCESSES.append(proc)


def unregister_process(proc: subprocess.Popen) -> None:
    with SUBPROCESS_LOCK:
        if proc in ACTIVE_SUBPROCESSES:
            ACTIVE_SUBPROCESSES.remove(proc)


def cancel_active_tasks() -> None:
    set_cancelled(True)
    with SUBPROCESS_LOCK:
        for proc in ACTIVE_SUBPROCESSES:
            try:
                if os.name != 'nt':
                    # Kill process group to stop both shell and actual adb/other child processes
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                else:
                    proc.terminate()
                    proc.kill()
            except Exception as e:
                log(f"Error terminating process group: {e}")
        ACTIVE_SUBPROCESSES.clear()


def run_tracked_subprocess(cmd: list[str] | str, shell: bool = False, timeout: float | None = None) -> tuple[int, bytes]:
    """Runs a subprocess, registers it for cancellation, and returns (returncode, stdout)."""
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
    register_process(proc)
    try:
        stdout, _ = proc.communicate(timeout=timeout)
        return proc.returncode, stdout
    except subprocess.TimeoutExpired:
        if os.name != 'nt':
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except OSError:
                pass
        else:
            proc.kill()
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
        output = subprocess.check_output(["adb", "devices"], stderr=subprocess.STDOUT)
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


def adb_shell_su(command: str) -> str | None:
    """Run a command via `adb shell su -c`. Returns stdout or None on error."""
    if not CURRENT_DEVICE:
        log(f"ADB command aborted: no device selected — {command!r}")
        return None
    try:
        cmd = ["adb", "-s", CURRENT_DEVICE, "shell", "su", "-c", command]
        code, output = run_tracked_subprocess(cmd, timeout=60)
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
    cmd = ["adb", "-s", CURRENT_DEVICE, "pull", remote]
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


def _pull_folder(remote: str, local_base: str | None) -> str:
    """Pull remote folder to local_base (or cwd). Returns the local destination."""
    dest = local_base if local_base else get_cwd()
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
    base = output_path if output_path else get_cwd()
    local_dir = os.path.join(base, folder_name)
    os.makedirs(local_dir, exist_ok=True)

    local_archive = os.path.join(local_dir, "search_extract.tar")
    adb_cmd = f"adb -s {CURRENT_DEVICE}" if CURRENT_DEVICE else "adb"

    # Quote each path to handle spaces or special characters safely
    quoted_paths = " ".join(f"'{p}'" for p in selected)

    # Stream the tar archive directly from the phone to the PC using su for root access
    cmd = f'{adb_cmd} exec-out su -c "stty raw 2>/dev/null; tar -cf - {quoted_paths} 2>/dev/null" > "{local_archive}"'
    log(f"Streaming searched files to local tar: {cmd}")
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
        extract_cmd = f'tar -xf "{local_archive}" -C "{local_dir}"'
        shell_local(extract_cmd)
        try:
            os.remove(local_archive)
        except OSError:
            pass
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
        return [], {}

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
    base = output_path if output_path else get_cwd()
    local_dir = os.path.join(base, folder_name)
    os.makedirs(local_dir, exist_ok=True)

    adb_cmd = f"adb -s {CURRENT_DEVICE}" if CURRENT_DEVICE else "adb"

    for pkg in selected:
        if is_cancelled():
            break
        local_archive = os.path.join(local_dir, f"{pkg}.tar")
        
        # Stream the tar archive directly from the phone to a local tar file on the PC
        cmd = f'{adb_cmd} exec-out su -c "stty raw 2>/dev/null; tar -cf - /data/data/{pkg} 2>/dev/null" > "{local_archive}"'
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
    base = output_path if output_path else get_cwd()
    local_base = os.path.join(base, folder_name)
    os.makedirs(local_base, exist_ok=True)

    adb_cmd = f"adb -s {CURRENT_DEVICE}" if CURRENT_DEVICE else "adb"

    extracted = []
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
        cmd = f'{adb_cmd} exec-out su -c "stty raw 2>/dev/null; tar -cf - -C \\"{pkg_dir}\\" . 2>/dev/null" > "{local_archive}"'
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
    base = output_path if output_path else get_cwd()
    local_dir = os.path.join(base, folder_name)
    os.makedirs(local_dir, exist_ok=True)

    adb_cmd = f"adb -s {CURRENT_DEVICE}" if CURRENT_DEVICE else "adb"

    for pkg in selected:
        if is_cancelled():
            break
        local_archive = os.path.join(local_dir, f"{pkg}.tar")
        
        # Stream the tar archive directly from the phone to the PC
        cmd = f'{adb_cmd} exec-out su -c "stty raw 2>/dev/null; tar -cf - /sdcard/Android/data/{pkg} 2>/dev/null" > "{local_archive}"'
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

    log(f"Public extraction complete → {local_dir}")
    return local_dir


# ---------------------------------------------------------------------------
# Extraction — All Data
# ---------------------------------------------------------------------------

def full_device_dump(output_path: str | None) -> str | None:
    base = output_path if output_path else get_cwd()
    local_file = os.path.join(base, f"full_system_dump_{_timestamp()}.tar")

    adb_cmd = f"adb -s {CURRENT_DEVICE}" if CURRENT_DEVICE else "adb"
    # Command matching user's exact specification
    cmd = f'{adb_cmd} exec-out su -c "stty raw 2>/dev/null; tar -cf - /data /sdcard 2>/dev/null" > "{local_file}"'
    log(f"Starting full system dump: {cmd}")
    shell_local(cmd)

    if is_cancelled():
        if os.path.exists(local_file):
            try:
                os.remove(local_file)
            except OSError:
                pass
        log("Full system dump cancelled by user: file removed.")
        return None

    if os.path.exists(local_file) and os.path.getsize(local_file) > 0:
        log(f"Full logical dump complete → {local_file}")
        return local_file
    else:
        log("Full logical dump failed (output file empty or not found).")
        return None


# ---------------------------------------------------------------------------
# Analysis — ALEAPP
# ---------------------------------------------------------------------------

def run_aleapp(aleapp_path: str, input_folder: str) -> None:
    """Run ALEAPP analysis and open the resulting HTML report."""
    cmd = f"python '{aleapp_path}' -t fs -i '{input_folder}' -o '{input_folder}'"
    log(f"Running ALEAPP: {cmd}")
    result = shell_local(cmd)
    if result:
        lines = [l for l in result.split("\n") if l.strip()]
        if lines:
            output_folder = lines[-1].split("/")[-1]
            report = os.path.join(input_folder, output_folder, "index.html")
            log(f"Opening report: {report}")
            webbrowser.open_new_tab(report)
    else:
        log("ALEAPP produced no output.")


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
    folder_name = f"decompiled_files_{_timestamp()}"
    decompile_base = os.path.join(os.path.dirname(local_base), folder_name)
    shell_local(f"mkdir -p '{decompile_base}'")
    log(f"JADX: Decompiling into {decompile_base}")

    for pkg in pkgs:
        if is_cancelled():
            break
        out_dir = os.path.join(decompile_base, pkg)
        apk = os.path.join(local_base, pkg, "base.apk")
        shell_local(f"mkdir -p '{out_dir}'")
        cmd = f"'{jadx_path}' -d '{out_dir}' '{apk}'"
        log(f"JADX: {cmd}")
        shell_local(cmd)
