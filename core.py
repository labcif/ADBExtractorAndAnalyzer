"""
core.py — ADB Extractor & Analyser 2.0
Constants, logging, preferences, ADB helpers, and all extraction/analysis logic.
"""

import json
import os
import subprocess
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

def adb_shell_su(command: str) -> str | None:
    """Run a command via `adb shell su -c`. Returns stdout or None on error."""
    try:
        output = subprocess.check_output(
            ["adb", "shell", "su", "-c", command],
            stderr=subprocess.STDOUT,
            timeout=60,
        )
        return output.decode("utf-8", errors="replace")
    except subprocess.CalledProcessError as e:
        log(f"ADB command failed: {command!r} — {e.output.decode('utf-8', errors='replace')}")
        return None
    except subprocess.TimeoutExpired:
        log(f"ADB command timed out: {command!r}")
        return None
    except FileNotFoundError:
        log("adb executable not found. Ensure ADB is installed and on PATH.")
        return None


def adb_pull(remote: str, local: str | None = None) -> bool:
    """Pull a path from the device. Returns True on success."""
    cmd = ["adb", "pull", remote]
    if local:
        cmd.append(local)
    try:
        subprocess.check_call(cmd, stderr=subprocess.STDOUT, timeout=300)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        log(f"adb pull failed: {e}")
        return False


def shell_local(command: str) -> str | None:
    """Run a local shell command. Returns stdout or None on error."""
    try:
        output = subprocess.check_output(
            command, shell=True, stderr=subprocess.STDOUT, timeout=300
        )
        return output.decode("utf-8", errors="replace")
    except subprocess.CalledProcessError as e:
        log(f"Local command failed: {command!r} — {e}")
        return None
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


# ---------------------------------------------------------------------------
# Device listing helpers (used by the GUI to populate checklists)
# ---------------------------------------------------------------------------

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
    Extract /data/data/<pkg> for each selected package via tar → sdcard → pull.
    Returns the local folder path, or None if nothing was selected.
    """
    if not selected:
        return None

    folder_name = f"private_data_{_timestamp()}"
    remote_folder = _device_temp_folder(folder_name)

    adb_shell_su(f"mkdir -p {remote_folder}")
    log(f"Created device folder: {remote_folder}")

    for pkg in selected:
        archive = f"/sdcard/Download/{pkg}.tar.gz"
        adb_shell_su(f"tar -czf {archive} /data/data/{pkg}")
        log(f"Compressed /data/data/{pkg}")
        adb_shell_su(f"tar -xzf {archive} -C {remote_folder}")
        log(f"Extracted to {remote_folder}")
        adb_shell_su(f"rm -rf {archive}")

    local_path = _pull_folder(remote_folder, output_path)
    adb_shell_su(f"rm -rf {remote_folder}")
    log(f"Private extraction complete → {local_path}")
    return local_path


# ---------------------------------------------------------------------------
# Extraction — APK Files
# ---------------------------------------------------------------------------

def extract_apk_files(
    selected: list[str],
    apk_dir_map: dict[str, str],
    output_path: str | None,
) -> tuple[str, list[str]]:
    """
    Extract ALL contents of each selected package's APK directory.
    apk_dir_map maps display label → absolute device path of the package dir,
    e.g. 'com.example.app' → '/data/app/~~abc==/com.example.app-XYZ'

    Returns (local_output_folder, [package_names_extracted]).
    """
    folder_name = f"apk_files_{_timestamp()}"
    staging = f"/sdcard/Download/{folder_name}"
    base = output_path if output_path else get_cwd()
    local_base = os.path.join(base, folder_name)

    adb_shell_su(f"mkdir -p '{staging}'")
    log(f"APK staging folder created: {staging}")

    extracted = []
    for pkg in selected:
        pkg_dir = apk_dir_map.get(pkg)
        if not pkg_dir:
            log(f"APK: no device directory mapped for '{pkg}', skipping.")
            continue

        dest_dir = f"{staging}/{pkg}"
        adb_shell_su(f"mkdir -p '{dest_dir}'")

        # Copy ALL contents (splits, configs, etc.) instead of just base.apk
        result = adb_shell_su(f"cp -r '{pkg_dir}/.' '{dest_dir}/'")
        if result is None:
            log(f"APK: cp failed for {pkg_dir}, trying archive mode")
            adb_shell_su(f"cp -a '{pkg_dir}/.' '{dest_dir}/'")

        log(f"APK: {pkg_dir} → {dest_dir}/ (full directory copy)")
        extracted.append(pkg)

    ok = adb_pull(staging, base)
    adb_shell_su(f"rm -rf '{staging}'")
    if ok:
        log(f"APK extraction complete → {local_base}")
    else:
        log(f"APK: adb pull failed or partially failed for {staging}")

    return local_base, extracted


# ---------------------------------------------------------------------------
# Extraction — Public Data
# ---------------------------------------------------------------------------

def extract_public_data(selected: list[str], output_path: str | None) -> str | None:
    """Extract /sdcard/Android/data/<pkg> for each selected package."""
    if not selected:
        return None

    folder_name = f"public_data_{_timestamp()}"
    remote_folder = _device_temp_folder(folder_name)
    adb_shell_su(f"mkdir -p {remote_folder}")
    log(f"Created device folder: {remote_folder}")

    for pkg in selected:
        archive = f"/sdcard/Download/{pkg}.tar.gz"
        adb_shell_su(f"tar -czf {archive} /sdcard/Android/data/{pkg}")
        adb_shell_su(f"tar -xzf {archive} -C {remote_folder}")
        adb_shell_su(f"rm -rf {archive}")
        log(f"Packed {pkg}")

    local_path = _pull_folder(remote_folder, output_path)
    adb_shell_su(f"rm -rf {remote_folder}")
    log(f"Public extraction complete → {local_path}")
    return local_path


# ---------------------------------------------------------------------------
# Extraction — All Data
# ---------------------------------------------------------------------------

def full_device_dump(output_path: str | None) -> str | None:
    folder_name = f"full_logical_backup_{_timestamp()}"
    base = output_path if output_path else get_cwd()
    local_dir = os.path.join(base, folder_name)
    os.makedirs(local_dir, exist_ok=True)

    # Step 1: get mount points
    mounts = adb_shell_su("cat /proc/mounts")
    if not mounts:
        log("Failed to read mount points")
        return None

    valid_mounts = []

    for line in mounts.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue

        mount_point = parts[1]
        fs_type = parts[2]

        # Exclude virtual/system mounts
        if fs_type in ("proc", "sysfs", "tmpfs", "devpts", "selinuxfs", "debugfs"):
            continue

        # Exclude problematic paths
        if mount_point.startswith(("/proc", "/sys", "/dev")):
            continue

        valid_mounts.append(mount_point)

    # Remove duplicates and sort
    valid_mounts = sorted(set(valid_mounts))

    log(f"Discovered mount points: {valid_mounts}")

    # Step 2: stream each mount
    for mount in valid_mounts:
        safe_name = mount.strip("/").replace("/", "_") or "root"
        local_file = os.path.join(local_dir, f"{safe_name}.tar")

        cmd = f'adb exec-out su -c "tar -cf - \\"{mount}\\"" > "{local_file}"'
        shell_local(cmd)

        log(f"Dumped mount: {mount}")

    log(f"Full logical dump complete → {local_dir}")
    return local_dir


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
        out_dir = os.path.join(decompile_base, pkg)
        apk = os.path.join(local_base, pkg, "base.apk")
        shell_local(f"mkdir -p '{out_dir}'")
        cmd = f"'{jadx_path}' -d '{out_dir}' '{apk}'"
        log(f"JADX: {cmd}")
        shell_local(cmd)
