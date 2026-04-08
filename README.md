# ADBExtractorAndAnalyzer 

## Overview
This Python program provides a comprehensive solution for extracting, analyzing, and decompiling data from Android devices using ADB (Android Debug Bridge) shell commands. It facilitates the extraction of public, private, and APK data from Android devices, followed by analysis and decompilation using JADX, ALEAPP, and MobSF.
<img width="1922" height="1082" alt="imagem" src="https://github.com/user-attachments/assets/86b4e7ff-3d24-4660-9936-c509586c33b6" />

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


## Authors
- Guilherme dos Reis Guilherme (https://github.com/guilhermegui08)
- Ricardo Bento Santos (https://github.com/RicardoBeny)
- We sincerely thank everyone who has contributed to this project.


## License
This project is licensed under the [GPL-3.0](LICENSE).
