# ADBExtractorAndAnalyzer 

## Overview
This Python program provides a comprehensive solution for extracting, analyzing, and decompiling data from Android devices using ADB (Android Debug Bridge) shell commands. It facilitates the extraction of public, private, and APK data from Android devices, followed by analysis and decompilation using JADX, ALEAPP, and MobSF.

## Features
- **Data Extraction:** Extracts public, private, and APK data from Android devices using ADB shell commands.
- **Data Analysis:** Utilizes JADX, ALEAPP, and MobSF for analyzing the extracted data.
- **Decompilation:** Decompiles APK files using JADX to provide insights into their inner workings.
- **User-Friendly Interface:** Offers a user-friendly interface for ease of use.

## Requirements
- *Python 3.x
- *ADB (Android Debug Bridge) installed on the system
- JADX, ALEAPP installed and configured

## Usage
1. Clone the repository.
`git clone https://github.com/labcif/ADBExtractorAndAnalyzer.git
cd ADBExtractorAndAnalyzer
pip install -r requirements.txt
python main.py`.
3. Install the necessary dependencies using `pip install -r requirements.txt`.
4. Connect your Android device to the computer via USB debugging.
5. Run the Python program and select the desired extraction options (public, private, APK).
`python main.py`

## Contributors
- Ricardo Bento Santos (https://github.com/RicardoBeny) - Creator and main developer
- Guilherme dos Reis Guilherme (https://github.com/guilhermegui08) - Creator and main developer
