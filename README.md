# ADBExtractorAndAnalyzer 

## Overview
This Python program provides a comprehensive solution for extracting, analyzing, and decompiling data from Android devices using ADB (Android Debug Bridge) shell commands. It facilitates the extraction of public, private, and APK data from Android devices, followed by analysis and decompilation using JADX, ALEAPP, and MobSF.
<img width="1922" height="1052" alt="imagem" src="https://github.com/user-attachments/assets/b45c150b-62a4-484c-ac4b-8d996c5a2a01" />


---

## Features
- **Data Extraction:** All public, private, APK, search, and full-dump extractions are treated as forensic acquisitions and use ADB shell commands.
- **Evidence Manifests:** Records device and package metadata plus device-side SHA-256 hashes before transfer.
- **Data Analysis:** Utilizes ALEAPP, and MobSF for analyzing the extracted data.
- **Decompilation:** Decompiles APK files using JADX to provide insights into their inner workings.
- **User-Friendly Interface:** Offers a user-friendly interface for ease of use.


## Requirements
- Python 3.x (3.10 recommended)
- ADB (Android Debug Bridge)
- Tkinter (required for GUI — installed via system packages)
- JADX (for APK decompilation)
- ALEAPP (for forensic analysis)

## Android emulator root requirements
The application detects and uses `adb root`, `su -c`, `su 0 -c`, or `su 0`
for extraction commands. Therefore, an emulator being visible to ADB is not
enough: it must provide one of these working root interfaces.

Standard Android Studio images usually do not meet this requirement:

- **Google Play images** use production-style builds and normally cannot be
  rooted with the standard AVD configuration.
- **Google APIs images** may support `adb root` on some system-image builds,
and can therefore be acquired directly. A root-enabled image or a properly
configured root solution is still required for production-style builds.

Without root, the application may connect to the emulator and list the device,
but private data extraction is unavailable. Full Dump automatically becomes an
accessible logical acquisition of readable shared storage (`/sdcard`); Android
storage restrictions still limit which public files are available.

For a practical emulator setup, use a root-enabled AOSP or compatible Google
APIs image and an emulator-compatible version of [Magisk](https://github.com/topjohnwu/Magisk).
After installing and configuring Magisk, allow superuser access for ADB and
verify a root interface before running the application:

```bash
adb shell su -c id
```

The command should report `uid=0`. For userdebug builds, `adb root` followed
by `adb shell id` is also supported.

### Rooting an Android Studio AVD
When a selected emulator has no root interface, the application offers a guided
RootAVD launcher. Download RootAVD separately from
https://gitlab.com/newbit/rootAVD, then select its `rootAVD.sh` script and the
application resolves the AVD system-image `ramdisk.img` (or
`ramdisk-qemu.img`) from the selected emulator's AVD configuration. RootAVD
opens in a terminal because its Magisk selection is interactive. Back up the
AVD system image, complete the terminal workflow, restart the emulator, and
select it again in the application.


## Dependencies
### Ubuntu / Debian
```bash
sudo apt install python3 python3-pip python3-tk adb
```
### Fedora
```bash
sudo dnf install python3 python3-pip python3-tkinter android-tools
```
### Arch Linux
```bash
sudo pacman -S python python-pip tk android-tools
```


## Installation & Usage
1. Clone the repository:
```bash
git clone https://github.com/labcif/ADBExtractorAndAnalyzer.git
cd ADBExtractorAndAnalyzer
```
2. Install Python dependencies:
```bash
pip install -r requirements.txt
```
3. Run the application:
```bash
python main.py
```


## OS
Developed for Linux.

## Private Flatpak build
The repository includes a private Flatpak manifest under `flatpak/`. It bundles
the application dependencies, ALEAPP, Android platform-tools, JADX, and a Java
runtime for JADX. The manifest currently pins ALEAPP `v2026.1.0`, Android
platform-tools `r37.0.1`, JADX `1.5.6`, and a Temurin Java 17 runtime. USB ADB
access is enabled for the sandbox.

Install Flatpak and the builder, then install the SDK/runtime:

```bash
sudo apt install flatpak flatpak-builder
flatpak install flathub org.freedesktop.Platform//24.08 org.freedesktop.Sdk//24.08
```

Build and run the application:

```bash
flatpak-builder --user --install --force-clean build \
  flatpak/io.github.labcif.adbextractorandanalyzer.yml
flatpak run io.github.labcif.adbextractorandanalyzer
```

To create a portable private bundle:

```bash
flatpak-builder --repo=repo --force-clean build \
  flatpak/io.github.labcif.adbextractorandanalyzer.yml
flatpak build-bundle repo adbextractorandanalyzer.flatpak \
  io.github.labcif.adbextractorandanalyzer master
```

The manifest uses the local checkout as its application source. For a release
build from the official repository, replace that source with a pinned commit
from https://github.com/labcif/ADBExtractorAndAnalyzer.


## Authors
- Guilherme dos Reis Guilherme (https://github.com/guilhermegui08)
- Ricardo Bento Santos (https://github.com/RicardoBeny)
- We sincerely thank everyone who has contributed to this project.


## License
This project is licensed under the [GPL-3.0](LICENSE).
