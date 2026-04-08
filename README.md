# ADBExtractorAndAnalyzer 

## Overview
This Python program provides a comprehensive solution for extracting, analyzing, and decompiling data from Android devices using ADB (Android Debug Bridge) shell commands. It facilitates the extraction of public, private, and APK data from Android devices, followed by analysis and decompilation using JADX, ALEAPP, and MobSF.
<img width="1922" height="1082" alt="imagem" src="https://github.com/user-attachments/assets/86b4e7ff-3d24-4660-9936-c509586c33b6" />



## Features
- **Data Extraction:** Extracts public, private, and APK data from Android devices using ADB shell commands.
- **Data Analysis:** Utilizes ALEAPP, and MobSF for analyzing the extracted data.
- **Decompilation:** Decompiles APK files using JADX to provide insights into their inner workings.
- **User-Friendly Interface:** Offers a user-friendly interface for ease of use.

## Requirements
- *Python 3.x (3.10 recommended)
- *ADB (Android Debug Bridge) installed on the system
- JADX, ALEAPP installed and configured

## Usage
1. Clone the repository.

```bash
    git clone https://github.com/labcif/ADBExtractorAndAnalyzer.git
    cd ADBExtractorAndAnalyzer
    pip install -r requirements.txt
    python main.py
```

2. Install the necessary dependencies using `pip install -r requirements.txt`.
3. Turn on your Android Virtual Device or connect the device to the computer via USB debugging.
4. Run the Python program and select the desired extraction options (public, private, APK). `python main.py`

## OS
Tested on Linux.

## Contributors
- Ricardo Bento Santos (https://github.com/RicardoBeny) - Creator and main developer
- Guilherme dos Reis Guilherme (https://github.com/guilhermegui08) - Creator and main developer

## License
This project is licensed under the [GPL-3.0](LICENSE).
