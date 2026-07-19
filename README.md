# ADBExtractorAndAnalyzer 

## Overview
ADB Extractor and Analyzer is a Linux desktop application for collecting Android data through ADB. It is intended for lab work and forensic examination of physical devices and Android Studio emulators.

The application can collect private app data, shared-storage app data, APKs, selected files, and logical device dumps. Rooted devices are acquired through a detected root interface. On a non-rooted device, the available actions are limited to data accessible to the ADB shell; a Full Dump collects readable shared storage only.

<p align="center">
  <img src="assets/icon.png"
       alt="ADB Extractor and Analyzer logo"
       width="512"
       height="512">
</p>

---

## Features
- Private data extraction from `/data/data` on rooted devices.
- Public app-data extraction from `/sdcard/Android/data`.
- APK extraction, MobSF scanning, and JADX decompilation.
- File search and extraction from `/data` and `/sdcard` when root is available; `/sdcard` only without root.
- Full logical dumps of `/data`, `/sdcard`, and `/data_mirror` on rooted devices; readable `/sdcard` data without root.
- Device-side SHA-256 manifests where the selected acquisition method can read the source files, local MD5/SHA-256 manifests, and acquisition metadata.
- ALEAPP filesystem analysis for private-data extractions and full dumps.

<img width="1922" height="1052" alt="imagem" src="https://github.com/user-attachments/assets/b45c150b-62a4-484c-ac4b-8d996c5a2a01" />

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
- **Google APIs images** may support `adb root`, depending on the system image.
  Production-style builds still require a separate root solution.

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
RootAVD launcher. The Flatpak bundle includes RootAVD; for a source checkout,
select `rootAVD.sh` from a RootAVD installation. The application resolves the
AVD system-image `ramdisk.img` or `ramdisk-qemu.img` from the selected
emulator's configuration and Android SDK.

RootAVD modifies the AVD system image and runs interactively in a terminal.
Back up the AVD first. Complete the RootAVD workflow, restart the emulator,
then select it again in the application.


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

## Flatpak
The Flatpak manifest is `flatpak/io.github.labcif.adbextractorandanalyzer.yml`.
It bundles ALEAPP, JADX, Android platform-tools, a Java runtime, and RootAVD.
It has access to USB ADB devices, the home directory, removable-media mount
points, X11/XWayland, and Wayland session integration. RootAVD uses a host
terminal because it must modify the host AVD system image.

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

To create the portable bundle:

```bash
flatpak-builder --repo=repo-current --force-clean build \
  flatpak/io.github.labcif.adbextractorandanalyzer.yml
flatpak build-bundle repo-current adbextractorandanalyzer.flatpak \
  io.github.labcif.adbextractorandanalyzer master
```

`adbextractorandanalyzer.flatpak` is the only portable bundle maintained in
the project root. The manifest builds from the local checkout.


## Authors
- Guilherme dos Reis Guilherme (https://github.com/guilhermegui08)
- Ricardo Bento Santos (https://github.com/RicardoBeny)
- We sincerely thank everyone who has contributed to this project.


## License
This project is licensed under the [GPL-3.0](LICENSE).
