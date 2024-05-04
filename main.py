import subprocess
import tkinter as tk
import shutil
from datetime import datetime
import os
from tkinter import filedialog
import webbrowser
from tkinter import messagebox
import platform
import json
import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder
from bs4 import BeautifulSoup

def applicationGUI():
    def adb_shell_su_command(command):
        adb_command = ["adb", "shell", "su", "-c", command]
        try:
            output = subprocess.check_output(adb_command, stderr=subprocess.STDOUT)
            return output.decode("utf-8")
        except subprocess.CalledProcessError as e:
            print("Error executing command:", e)
            return None

    def log_procedure(message):
        with open("logs.txt", "a") as logfile:
            logfile.write(f"{datetime.now()} - {message}\n")

    def extract_selected_files():
        selected_values = []
        for widget in listbox.winfo_children():
            if isinstance(widget, tk.Checkbutton) and widget.var.get() == 1:
                selected_values.append(widget["text"])

        current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        folder_name = f"private_data_{current_time}"

        path = shell_command("pwd").strip()

        adb_shell_su_command(f"mkdir -p /sdcard/Download/{folder_name}")
        log_procedure(f"Created folder '/sdcard/Download/{folder_name}' on the device")
        
        for file_name in selected_values:
            adb_shell_su_command(f"tar -czf /sdcard/Download/{file_name}.tar.gz /data/data/{file_name}")
            log_procedure(f"Compressed '/data/data/{file_name}' to '/sdcard/Download/{file_name}.tar.gz'")
            
            adb_shell_su_command(f"tar -xzf /sdcard/Download/{file_name}.tar.gz -C /sdcard/Download/{folder_name}")
            log_procedure(f"Extracted '/sdcard/Download/{file_name}.tar.gz' to '/sdcard/Download/{folder_name}'")
            
            adb_shell_su_command(f"rm -r /sdcard/Download/{file_name}.tar.gz")
            log_procedure(f"Deleted '/sdcard/Download/{file_name}.tar.gz' from the device")
        
        if output_entry.get():
            subprocess.run(["adb", "pull", f"/sdcard/Download/{folder_name}", f"{output_entry.get()}"])
            path = output_entry.get()
            log_procedure(f"Copied folder '/sdcard/Download/{folder_name}' to '{output_entry.get()}'")
        else:
            subprocess.run(["adb", "pull", f"/sdcard/Download/{folder_name}"])
            log_procedure(f"Copied folder '/sdcard/Download/{folder_name}' to current directory")

        adb_shell_su_command(f"rm -r /sdcard/Download/{folder_name}")
        log_procedure(f"Deleted folder '/sdcard/Download/{folder_name}' from the device")

        print("Files copied successfully")
        log_procedure("Extraction completed successfully")
        
        return path+f"/{folder_name}/"

    def extract_and_analyse():
        log_procedure("Starting extraction and analysis process")
        
        path = aleapp_entry.get().strip()
        if not path:
            messagebox.showerror("ALEAPP file not given", "There are no inserted files. Please select a file!")
            log_procedure("No ALEAPP file provided. Aborting extraction and analysis process.")
            return
        
        folder_path = extract_selected_files()
        log_procedure(f"Selected files extracted to folder: '{folder_path}'")
        
        print(folder_path)
        
        command = f"python '{path}' -t fs -i '{folder_path}' -o '{folder_path}'"
        log_procedure(f"Executing ALEAPP analysis command: '{command}'")
        
        result = shell_command2(command)
        ultima_linha = ""
        if result:
            lines = result.split("\n")[0:-1]
            for i, line in enumerate(lines):
                ultima_linha = line
            output_folder = ultima_linha.split("/")[-1]
            print(folder_path + output_folder + "/index.html")
            log_procedure(f"Analysis completed. Opening HTML report in web browser: '{folder_path}{output_folder}/index.html'")
            webbrowser.open_new_tab(folder_path + output_folder + "/index.html")
        else:
            log_procedure("Analysis failed. No result obtained.")
        
        log_procedure("Extraction and analysis process completed")

    def extract_and_analyse2():
        log_procedure("Starting extraction and analysis process")
        
        url = "http://192.144.168.75/api_docs"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                api_key_element = soup.find('code')
                if api_key_element:
                    api_key_value = api_key_element.text.strip()
                    log_procedure(f"API Key Value: {api_key_value}")
                else:
                    log_procedure("API key element not found on the page.")
            else:
                log_procedure(f"Failed to fetch the webpage. Status code: {response.status_code}")

        except requests.exceptions.RequestException as e:
            log_procedure(f"An error occurred: {e}")
            
        SERVER = "http://192.144.168.75"
        APIKEY = api_key_value
        paths = extract_selected_files2()
        log_procedure(f"Selected files to process: {paths}")
        
        if len(paths) > 1:
            for i in range(1, len(paths)):
                try:
                    FILE = paths[0] + paths[i] + "/base.apk"

                    """Upload File"""
                    log_procedure("Uploading file")
                    multipart_data = MultipartEncoder(fields={'file': (FILE, open(FILE, 'rb'), 'application/octet-stream')})
                    headers = {'Content-Type': multipart_data.content_type, 'Authorization': APIKEY}
                    response = requests.post(SERVER + '/api/v1/upload', data=multipart_data, headers=headers)
                    data0 = response.text

                    """Scan the file"""
                    log_procedure("Scanning file")
                    post_dict = json.loads(data0)
                    headers = {'Authorization': APIKEY}
                    response = requests.post(SERVER + '/api/v1/scan', data=post_dict, headers=headers)
                    
                    data = {"hash": json.loads(data0)["hash"]}
                    webbrowser.open_new_tab(f"http://192.144.168.75/StaticAnalyzer/?name=base.apk&type=apk&checksum={data['hash']}")
                    log_procedure("HTML report opened in web browser")

                except requests.exceptions.RequestException as e:
                    log_procedure(f"An exception occurred during the request: {str(e)}")

    def extract_and_decompile():
        log_procedure("Starting extraction and decompilation process")
        
        path = jadx_entry.get().strip()
        if not path:
            log_procedure("JADX file not provided")
            messagebox.showerror("jadx file not given", "There are no inserted files. Please select a file!")
            return
        
        paths = extract_selected_files2()
        log_procedure(f"Selected files to process: {paths}")
        
        current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        folder_name = f"decompiled_files_{current_time}"
        first_name = '/'.join(paths[0].split('/')[:-1])
        log_procedure(f"Creating decompiled files folder: {first_name}/{folder_name}")
        shell_command2(f"mkdir -p '{first_name}/{folder_name}'")
        
        if len(paths) > 1:
            for i in range(1, len(paths)):
                last_name = paths[i].split("/")[-1]
                log_procedure(f"Creating folder for {last_name} in decompiled files directory")
                shell_command2(f"mkdir -p '{first_name}/{folder_name}/{last_name}'")
                command = f"'{path}' -d '{first_name}/{folder_name}/{last_name}' '{paths[0]}{paths[i]}/base.apk'"
                log_procedure(f"Decompiling {paths[0]}{paths[i]}/base.apk using JADX")
                shell_command2(command)


    def extract_selected_files2():
        log_procedure("Starting extraction of selected files")
        
        selected_values = []
        for widget in listbox2.winfo_children():
            if isinstance(widget, tk.Checkbutton) and widget.var.get() == 1:
                selected_values.append(widget["text"])
        log_procedure(f"Selected files: {selected_values}")

        current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        folder_name = f"apk_files_{current_time}"
        log_procedure(f"Creating folder: {folder_name}")
        
        paths = []
        if output_entry.get():
            output_path = output_entry.get() + f"/{folder_name}"
            log_procedure(f"Output path specified: {output_path}")
            paths.append(output_path)
        else:
            default_output_path = shell_command("pwd").strip() + f"/{folder_name}"
            log_procedure(f"Default output path: {default_output_path}")
            paths.append(default_output_path)
            
        adb_shell_su_command(f"mkdir -p /sdcard/Download/{folder_name}")
        log_procedure(f"Created folder on device: /sdcard/Download/{folder_name}")
        
        for file_name in selected_values:
            paths.append(file_name)
            file_name2 = file_name.split("/")[-1]
            log_procedure(f"Compressing file: {file_name} -> {file_name2}.tar.gz")
            adb_shell_su_command(f"tar -czf /sdcard/Download/{file_name2}.tar.gz {file_name}")
            log_procedure(f"Extracting compressed file to device folder: /sdcard/Download/{folder_name}")
            adb_shell_su_command(f"tar -xzf /sdcard/Download/{file_name2}.tar.gz -C /sdcard/Download/{folder_name}")
            log_procedure(f"Removing compressed file from device: /sdcard/Download/{file_name2}.tar.gz")
            adb_shell_su_command(f"rm -r /sdcard/Download/{file_name2}.tar.gz")
        
        if output_entry.get():
            subprocess.run(["adb", "pull", f"/sdcard/Download/{folder_name}",f"{output_entry.get()}"])
            path = output_entry.get()
            log_procedure(f"Files pulled from device to specified output path: {output_entry.get()}")
        else:
            subprocess.run(["adb", "pull", f"/sdcard/Download/{folder_name}"])
            log_procedure(f"Files pulled from device to default output path: {default_output_path}")
        
        adb_shell_su_command(f"rm -r /sdcard/Download/{folder_name}")
        log_procedure("Files copied successfully")
        
        return paths

    def extract_selected_files3():
        log_procedure("Starting extraction of selected files")

        selected_values = []
        for widget in listbox3.winfo_children():
            if isinstance(widget, tk.Checkbutton) and widget.var.get() == 1:
                selected_values.append(widget["text"])

        current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        folder_name = f"public_data_{current_time}"
        
        log_procedure(f"Creating folder on device: /sdcard/Download/{folder_name}")
        adb_shell_su_command(f"mkdir -p /sdcard/Download/{folder_name}")

        for file_name in selected_values:
            log_procedure(f"Compressing {file_name} on device")
            adb_shell_su_command(f"tar -czf /sdcard/Download/{file_name}.tar.gz /sdcard/Android/data/{file_name}")
            log_procedure(f"Extracting {file_name} on device to /sdcard/Download/{folder_name}")
            adb_shell_su_command(f"tar -xzf /sdcard/Download/{file_name}.tar.gz -C /sdcard/Download/{folder_name}")
            log_procedure(f"Removing compressed file {file_name}.tar.gz from device")
            adb_shell_su_command(f"rm -r /sdcard/Download/{file_name}.tar.gz")
        
        if output_entry.get():
            log_procedure(f"Pulling folder /sdcard/Download/{folder_name} from device to {output_entry.get()}")
            subprocess.run(["adb", "pull", f"/sdcard/Download/{folder_name}",f"{output_entry.get()}"])
            path = output_entry.get()
        else:
            log_procedure(f"Pulling folder /sdcard/Download/{folder_name} from device to current directory")
            subprocess.run(["adb", "pull", f"/sdcard/Download/{folder_name}"])
        
        log_procedure(f"Removing folder /sdcard/Download/{folder_name} from device")
        adb_shell_su_command(f"rm -r /sdcard/Download/{folder_name}")
        
        log_procedure("Files copied successfully")

    def shell_command2(command):
        try:
            output = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT)
            return output.decode("utf-8")
        except subprocess.CalledProcessError as e:
            print("Error executing command:", e)
            return None

    def shell_command(command):
        command = [command]
        try:
            output = subprocess.check_output(command, stderr=subprocess.STDOUT)
            return output.decode("utf-8")
        except subprocess.CalledProcessError as e:
            print("Error executing command:", e)
            return None

    def toggle_select_all():
        all_selected = True
        # Check if all items are selected
        for widget in listbox.winfo_children():
            if isinstance(widget, tk.Checkbutton) and widget.var.get() == 0:
                all_selected = False
                break
        
        # Toggle selection based on the current state
        if all_selected:
            deselect_all_items()
        else:
            select_all_items()

    def select_all_items():
        # Iterate through all items in the listbox
        for widget in listbox.winfo_children():
            if isinstance(widget, tk.Checkbutton):
                widget.var.set(1)

    def deselect_all_items():
        # Iterate through all items in the listbox
        for widget in listbox.winfo_children():
            if isinstance(widget, tk.Checkbutton):
                widget.var.set(0)

    def populate_listbox():
        # Clear previous items
        for widget in listbox.winfo_children():
            widget.destroy()

        filter = private_entry.get().replace(" ", '')
        # Execute adb command and split the result into lines
        result = adb_shell_su_command("ls /data/data/")
        if result:
            lines = result.split("\n")[0:-1]
            for i, line in enumerate(lines):
                # Apply filter if provided
                if filter and filter.lower() not in line.lower():
                    continue
                
                var = tk.IntVar()
                cb = tk.Checkbutton(listbox, text=line, variable=var, onvalue=1, offvalue=0)
                cb.var = var  # Store a reference to the IntVar object in the Checkbutton widget
                listbox.create_window(10, i * 20, anchor="nw", window=cb)

            # Update the scroll region of the canvas
            listbox.update_idletasks()  # Ensure all widgets are drawn
            listbox.config(scrollregion=listbox.bbox("all"))

    def toggle_select_all2():
        all_selected = True
        # Check if all items are selected
        for widget in listbox2.winfo_children():
            if isinstance(widget, tk.Checkbutton) and widget.var.get() == 0:
                all_selected = False
                break
        
        # Toggle selection based on the current state
        if all_selected:
            deselect_all_items2()
        else:
            select_all_items2()

    def select_all_items2():
        # Iterate through all items in the listbox
        for widget in listbox2.winfo_children():
            if isinstance(widget, tk.Checkbutton):
                widget.var.set(1)

    def deselect_all_items2():
        # Iterate through all items in the listbox
        for widget in listbox2.winfo_children():
            if isinstance(widget, tk.Checkbutton):
                widget.var.set(0)

    def populate_listbox2():
        # Clear previous items
        for widget in listbox2.winfo_children():
            widget.destroy()

        filter = apk_entry.get().replace(" ", '')
        # Execute adb command and split the result into lines
        result = adb_shell_su_command("ls /data/app/*/")
        if result:
            lines = result.strip().split("\n")  # Split the result into lines and remove leading/trailing whitespaces
            concatenated_lines = []

            # Iterate through the lines in groups of 3 and concatenate them without spaces
            for i in range(0, len(lines), 3):
                concatenated_line = ":".join(map(str.strip, lines[i:i+3]))  # Join the lines with ":" as separator
                concatenated_lines.append(concatenated_line.replace(':',''))

            # Display concatenated lines in the listbox
            for i, line in enumerate(concatenated_lines):
                if filter and filter.lower() not in line.lower():
                    continue

                var2 = tk.IntVar()
                cb2 = tk.Checkbutton(listbox2, text=line, variable=var2, onvalue=1, offvalue=0)
                cb2.var = var2  # Store a reference to the IntVar object in the Checkbutton widget
                listbox2.create_window(10, i * 20, anchor="nw", window=cb2)
            
            # Update the scroll region of the canvas
            listbox2.update_idletasks()  # Ensure all widgets are drawn
            listbox2.config(scrollregion=listbox2.bbox("all"))

    def toggle_select_all3():
        all_selected = True
        # Check if all items are selected
        for widget in listbox3.winfo_children():
            if isinstance(widget, tk.Checkbutton) and widget.var.get() == 0:
                all_selected = False
                break
        
        # Toggle selection based on the current state
        if all_selected:
            deselect_all_items3()
        else:
            select_all_items3()

    def select_all_items3():
        # Iterate through all items in the listbox
        for widget in listbox3.winfo_children():
            if isinstance(widget, tk.Checkbutton):
                widget.var.set(1)

    def deselect_all_items3():
        # Iterate through all items in the listbox
        for widget in listbox3.winfo_children():
            if isinstance(widget, tk.Checkbutton):
                widget.var.set(0)

    def populate_listbox3():
        # Clear previous items
        for widget in listbox3.winfo_children():
            widget.destroy()

        filter = public_entry.get().replace(" ", '')
        # Execute adb command and split the result into lines
        result = adb_shell_su_command("ls /sdcard/Android/data/")
        if result:
            lines = result.split("\n")[0:-1]
            for i, line in enumerate(lines):
                if filter and filter.lower() not in line.lower():
                    continue

                var = tk.IntVar()
                cb = tk.Checkbutton(listbox3, text=line, variable=var, onvalue=1, offvalue=0)
                cb.var = var  # Store a reference to the IntVar object in the Checkbutton widget
                listbox3.create_window(10, i * 20, anchor="nw", window=cb)

            # Update the scroll region of the canvas
            listbox3.update_idletasks()  # Ensure all widgets are drawn
            listbox3.config(scrollregion=listbox3.bbox("all"))

    # Function to save the file path to a file
    def save_file_path(file_path):
        with open("last_selected_file.txt", "w") as file:
            file.write(file_path)

    # Function to read the last selected file path from the file
    def read_last_file_path():
        if os.path.exists("last_selected_file.txt"):
            with open("last_selected_file.txt", "r") as file:
                return file.read().strip()
        else:
            return ""

    def browse_file():
        filename = filedialog.askopenfilename()
        aleapp_entry.delete(0, tk.END)
        aleapp_entry.insert(0, filename)
        save_file_path(filename)
    
    # Function to save the file path to a file
    def save_file_path2(file_path):
        with open("last_output_file.txt", "w") as file:
            file.write(file_path)

    # Function to read the last selected file path from the file
    def read_last_file_path2():
        if os.path.exists("last_output_file.txt"):
            with open("last_output_file.txt", "r") as file:
                return file.read().strip()
        else:
            return ""

    def browse_file2():
        filename = filedialog.askdirectory()
        output_entry.delete(0, tk.END)
        output_entry.insert(0, filename)
        save_file_path2(filename)

    # Function to save the file path to a file
    def save_file_path3(file_path):
        with open("last_jadx_file.txt", "w") as file:
            file.write(file_path)

    # Function to read the last selected file path from the file
    def read_last_file_path3():
        if os.path.exists("last_jadx_file.txt"):
            with open("last_jadx_file.txt", "r") as file:
                return file.read().strip()
        else:
            return ""

    def browse_file3():
        filename = filedialog.askopenfilename()
        jadx_entry.delete(0, tk.END)
        jadx_entry.insert(0, filename)
        save_file_path3(filename)

    root = tk.Tk()
    root.title("ADB extractor and analyser")
    root.geometry("1280x960")

    title_frame = tk.Frame(root)
    title_frame.pack(side=tk.TOP)
    window_frame = tk.Frame(root)
    window_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True) 
    left_frame = tk.Frame(window_frame)
    left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    right_main_frame = tk.Frame(window_frame)
    right_main_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
    center_frame = tk.Frame(right_main_frame)
    center_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
    right_frame = tk.Frame(right_main_frame)
    right_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)

    top_left_frame = tk.Frame(left_frame)
    top_left_frame.pack(padx=10, pady=10, side=tk.TOP, fill=tk.BOTH, expand=True)
    top_bot_left_frame = tk.Frame(top_left_frame)
    top_bot_left_frame.pack(padx=10, pady=10, side=tk.BOTTOM, fill=tk.BOTH, expand=True)
    bot_left_frame = tk.Frame(left_frame)
    bot_left_frame.pack(padx=10, pady=10, side=tk.BOTTOM)

    top_center_frame = tk.Frame(center_frame)
    top_center_frame.pack(padx=10, pady=10, side=tk.TOP, fill=tk.BOTH, expand=True)
    top_bot_center_frame = tk.Frame(top_center_frame)
    top_bot_center_frame.pack(padx=10, pady=10, side=tk.BOTTOM, fill=tk.BOTH, expand=True)
    bot_center_frame = tk.Frame(center_frame)
    bot_center_frame.pack(padx=10, pady=10, side=tk.BOTTOM)

    top_right_frame = tk.Frame(right_frame)
    top_right_frame.pack(padx=10, pady=10, side=tk.TOP, fill=tk.BOTH, expand=True)
    top_bot_right_frame = tk.Frame(top_right_frame)
    top_bot_right_frame.pack(padx=10, pady=10, side=tk.BOTTOM, fill=tk.BOTH, expand=True)
    bot_right_frame = tk.Frame(right_frame)
    bot_right_frame.pack(padx=10, pady=10, side=tk.BOTTOM)

    initial_frame = tk.Frame(root)
    initial_frame.pack(side=tk.TOP, fill=tk.X)
    initial_label_frame = tk.Frame(initial_frame)
    initial_label_frame.pack(side=tk.LEFT, fill=tk.X)
    name_label = tk.Label(initial_label_frame, text="ADB Extractor and Analyser 1.0", font=("consolas", 20, "bold"))
    name_label.pack(side=tk.TOP, padx=5, pady=5, anchor='w')
    initial_button_frame = tk.Frame(initial_frame)
    initial_button_frame.pack(side=tk.RIGHT, fill=tk.X, expand=True)
    output_label = tk.Label(initial_button_frame, text="Output path:")
    output_label.pack(side=tk.LEFT, padx=5, pady=5)
    output_entry = tk.Entry(initial_button_frame)
    output_entry.pack(side=tk.LEFT, padx=5, pady=5, fill=tk.BOTH, expand=True)
    last_file_path2 = read_last_file_path2()
    output_entry.insert(0, last_file_path2)
    browse_button2 = tk.Button(initial_button_frame, text="Browse", command=browse_file2)
    browse_button2.pack(side=tk.LEFT, padx=5, pady=5)

    top_top_left_frame = tk.Label(top_left_frame)
    top_top_left_frame.pack(side=tk.TOP, fill=tk.X)
    top_top_left_left_frame = tk.Label(top_top_left_frame)
    top_top_left_left_frame.pack(side=tk.LEFT, fill=tk.X)
    top_top_left_right_frame = tk.Label(top_top_left_frame)
    top_top_left_right_frame.pack(side=tk.RIGHT, fill=tk.X)
    private_data_label = tk.Label(top_top_left_left_frame, text="Private Data", font=("consolas", 16))
    private_data_label.pack(side=tk.TOP, padx=5, pady=5)
    select_all_button = tk.Button(top_top_left_right_frame, text="Select ALL", command=toggle_select_all)
    select_all_button.pack(side=tk.RIGHT, padx=5, pady=5)
    private_button = tk.Button(top_top_left_right_frame, text="Apply Filter", command=populate_listbox)
    private_button.pack(side=tk.RIGHT, padx=5, pady=5)
    private_entry = tk.Entry(top_top_left_right_frame)
    private_entry.pack(side=tk.RIGHT ,padx=5, pady=5)
    private_filter_label = tk.Label(top_top_left_frame, text="Filter:")
    private_filter_label.pack(padx=5, pady=5, side=tk.RIGHT)

    top_center_left_frame = tk.Label(top_center_frame)
    top_center_left_frame.pack(side=tk.TOP, fill=tk.X)
    top_center_left_left_frame = tk.Label(top_center_left_frame)
    top_center_left_left_frame.pack(side=tk.LEFT, fill=tk.X)
    top_center_left_right_frame = tk.Label(top_center_left_frame)
    top_center_left_right_frame.pack(side=tk.RIGHT, fill=tk.X)
    apk_file_label = tk.Label(top_center_left_left_frame, text="APK Files", font=("consolas", 16))
    apk_file_label.pack(side=tk.TOP, padx=5, pady=5)
    select_all_button2 = tk.Button(top_center_left_right_frame, text="Select ALL", command=toggle_select_all2)
    select_all_button2.pack(side=tk.RIGHT, padx=5, pady=5)
    apk_button = tk.Button(top_center_left_right_frame, text="Apply Filter", command=populate_listbox2)
    apk_button.pack(side=tk.RIGHT, padx=5, pady=5)
    apk_entry = tk.Entry(top_center_left_right_frame)
    apk_entry.pack(side=tk.RIGHT ,padx=5, pady=5)
    apk_filter_label = tk.Label(top_center_left_frame, text="Filter:")
    apk_filter_label.pack(padx=5, pady=5, side=tk.RIGHT)

    top_right_left_frame = tk.Label(top_right_frame)
    top_right_left_frame.pack(side=tk.TOP, fill=tk.X)
    top_right_left_left_frame = tk.Label(top_right_left_frame)
    top_right_left_left_frame.pack(side=tk.LEFT, fill=tk.X)
    top_right_left_right_frame = tk.Label(top_right_left_frame)
    top_right_left_right_frame.pack(side=tk.RIGHT, fill=tk.X)
    public_data_label = tk.Label(top_right_left_left_frame, text="Public Data", font=("consolas", 16))
    public_data_label.pack(side=tk.TOP, padx=5, pady=5)
    select_all_button3 = tk.Button(top_right_left_right_frame, text="Select ALL", command=toggle_select_all3)
    select_all_button3.pack(side=tk.RIGHT, padx=5, pady=5)
    public_button = tk.Button(top_right_left_right_frame, text="Apply Filter", command=populate_listbox3)
    public_button.pack(side=tk.RIGHT, padx=5, pady=5)
    public_entry = tk.Entry(top_right_left_right_frame)
    public_entry.pack(side=tk.RIGHT ,padx=5, pady=5)
    public_filter_label = tk.Label(top_right_left_frame, text="Filter:")
    public_filter_label.pack(padx=5, pady=5, side=tk.RIGHT)

    aleapp_label = tk.Label(top_left_frame, text="ALEAPP path:*")
    aleapp_label.pack(side=tk.LEFT, padx=5, pady=5)
    aleapp_entry = tk.Entry(top_left_frame)
    aleapp_entry.pack(side=tk.LEFT, padx=5, pady=5, fill=tk.BOTH, expand=True)
    last_file_path = read_last_file_path()
    aleapp_entry.insert(0, last_file_path)
    browse_button = tk.Button(top_left_frame, text="Browse", command=browse_file)
    browse_button.pack(side=tk.LEFT, padx=5, pady=5)

    scrollbar = tk.Scrollbar(top_bot_left_frame, orient="vertical")
    scrollbar.pack(side="right", fill="y")
    listbox = tk.Canvas(top_bot_left_frame, yscrollcommand=scrollbar.set, width=300)
    listbox.pack(side="left", fill="both", expand=True)
    scrollbar.config(command=listbox.yview)

    populate_listbox()

    extract_button = tk.Button(bot_left_frame, text="Extract Selected Files", command=extract_selected_files)
    extract_button.pack(padx=5, pady=5, side=tk.LEFT)
    extract_button_and_analyse = tk.Button(bot_left_frame, text="Extract and Analyse Selected Files", command=extract_and_analyse)
    extract_button_and_analyse.pack(padx=5, pady=5, side=tk.RIGHT) 

    jadx_label = tk.Label(top_center_frame, text="jadx path:*")
    jadx_label.pack(side=tk.LEFT, padx=5, pady=5)
    jadx_entry = tk.Entry(top_center_frame)
    jadx_entry.pack(side=tk.LEFT, padx=5, pady=5, fill=tk.BOTH, expand=True)
    last_jadx_path = read_last_file_path3()
    jadx_entry.insert(0, last_jadx_path)
    browse_button3 = tk.Button(top_center_frame, text="Browse", command=browse_file3)
    browse_button3.pack(side=tk.LEFT, padx=5, pady=5)

    scrollbar2 = tk.Scrollbar(top_bot_center_frame, orient="vertical")
    scrollbar2.pack(side="right", fill="y")
    listbox2 = tk.Canvas(top_bot_center_frame, yscrollcommand=scrollbar2.set, width=300)
    listbox2.pack(side="left", fill="both", expand=True)
    scrollbar2.config(command=listbox2.yview)

    populate_listbox2()

    extract_button2 = tk.Button(bot_center_frame, text="Extract Selected Files", command=extract_selected_files2)
    extract_button2.pack(padx=5, pady=5, side=tk.LEFT)
    extract_button_and_analyse2 = tk.Button(bot_center_frame, text="Extract and Analyse Selected Files", command=extract_and_analyse2)
    extract_button_and_analyse2.pack(padx=5, pady=5, side=tk.RIGHT)
    extract_button_and_analyse3 = tk.Button(bot_center_frame, text="Extract and Decompile Selected Files", command=extract_and_decompile)
    extract_button_and_analyse3.pack(padx=5, pady=5, side=tk.RIGHT) 

    scrollbar3 = tk.Scrollbar(top_bot_right_frame, orient="vertical")
    scrollbar3.pack(side="right", fill="y")
    listbox3 = tk.Canvas(top_bot_right_frame, yscrollcommand=scrollbar3.set, width=300)
    listbox3.pack(side="left", fill="both", expand=True)
    scrollbar3.config(command=listbox3.yview)

    populate_listbox3()

    extract_button3 = tk.Button(bot_right_frame, text="Extract Selected Files", command=extract_selected_files3)
    extract_button3.pack(pady=5)

    # Run the GUI
    root.mainloop()

if __name__ == '__main__':
    applicationGUI()