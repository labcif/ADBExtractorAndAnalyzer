# ADBExtractorAndAnalyzer 

## Overview
This Python program provides a comprehensive solution for extracting, analyzing, and decompiling data from Android devices using ADB (Android Debug Bridge) shell commands. It facilitates the extraction of public, private, and APK data from Android devices, followed by analysis and decompilation using JADX, ALEAPP, and MobSF.
<img width="1922" height="1052" alt="imagem" src="https://github.com/user-attachments/assets/b45c150b-62a4-484c-ac4b-8d996c5a2a01" />


---

## Features
- **Data Extraction:** Extracts public, private, and APK data from Android devices using ADB shell commands.
- **Data Analysis:** Utilizes ALEAPP, and MobSF for analyzing the extracted data.
- **Decompilation:** Decompiles APK files using JADX to provide insights into their inner workings.
- **User-Friendly Interface:** Offers a user-friendly interface for ease of use.


## Requirements
- Python 3.x (3.10 recommended)
- ADB (Android Debug Bridge)
- Tkinter (required for GUI — installed via system packages)
- JADX (for APK decompilation)
- ALEAPP (for forensic analysis)


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
