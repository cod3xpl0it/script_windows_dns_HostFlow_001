import socket
import subprocess
import platform
import re
import csv
import webbrowser
import ipaddress
import threading
import queue
from concurrent.futures import ThreadPoolExecutor
import os
import sys
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog


SYSTEM_NAME = platform.system().lower()

IS_WINDOWS = SYSTEM_NAME == "windows"
IS_LINUX = SYSTEM_NAME == "linux"
IS_BSD = "bsd" in SYSTEM_NAME

IS_UNIX = IS_LINUX or IS_BSD


# ========================================================================
# System Name: HostFlow
# Designed by: Carlos Bezerra Vilela (Key CDXL)
# Development: 12/05/2026
# System tests performed:
# Performance of 11 queries per second with 300 simultaneous threads
# Equipment:
# Intel i5-1345U
# 32GB RAM
# Windows 11 Enterprise
# ========================================================================

# Define maximum number of allowed hosts
MAX_HOSTS = 3000  # 11 per second with 300 simultaneous threads
# Thread usage limit
MAX_THREADS = 300  # 11 per second with 300 simultaneous threads
# TTL limits to determine operating system
TTL_MIN_LINUX = 1
TTL_MAX_LINUX = 100
TTL_MIN_WINDOWS = 101
TTL_MAX_WINDOWS = 255

# Global variable to store hosts
hosts_list = []
# Global variable to store opened file path
current_file_path = None

# Predefined domain
DOMAIN = ""
HOST_SUFFIXES = [
    "",   # normal
    "x"   # with x
]

# Functions

def build_host(host, suffix):
    """Builds the final host considering domain and suffix."""

    # If already has domain (FQDN)
    if "." in host:
        return f"{host}{suffix}"

    # If domain is configured
    if DOMAIN:
        return f"{host}{suffix}.{DOMAIN}"

    # Otherwise, use as is (local DNS)
    return f"{host}{suffix}"
    

def is_valid_host(host):
    """Checks if the host is a valid IP or hostname."""
    try:
        ipaddress.ip_address(host)  # Validates if it is an IP
        return True
    except ValueError:
        hostname_pattern = re.compile(r'^[a-zA-Z0-9.-]+$')  # Regex for hostname
        return bool(hostname_pattern.match(host))
        
        
def is_dns_compatible(host_input, dns_reverse):
    """Validates reverse DNS considering asymmetric rule for 'x' suffix."""

    if not host_input or not dns_reverse:
        return False

    # remove domain
    input_base = host_input.split('.')[0].lower()
    dns_base = dns_reverse.split('.')[0].lower()

    # CASE 1: user typed with "x" → must match exactly
    if input_base.endswith('x'):
        return input_base == dns_base

    # CASE 2: user typed without "x" → accepts with or without "x"
    if dns_base == input_base:
        return True
    if dns_base == input_base + 'x':
        return True

    return False
    

def ping(host):
    """Performs a ping on the host and returns result and TTL."""

    try:

        if IS_WINDOWS:
            command = ['ping', '-n', '1', '-w', '1000', host]

        elif IS_BSD:
            command = ['ping', '-c', '1', '-W', '1000', host]

        else:
            command = ['ping', '-c', '1', '-W', '1', host]

        output = subprocess.check_output(
            command,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )

        ttl_match = re.search(r'(?:ttl|hlim)[=\s:](\d+)', output, re.IGNORECASE)

        ttl = ttl_match.group(1) if ttl_match else 'Not found'

        return True, ttl

    except Exception:
        return False, 'Ping error'

def dns_lookup(host):
    """Performs IPv4 DNS resolution and reverse DNS."""

    try:

        ip = socket.gethostbyname(host)

    except Exception:
        return None, "DNS Error"

    reverse_host = "No PTR"

    try:

        result = subprocess.run(
            ['host', ip],
            capture_output=True,
            text=True,
            timeout=5
        )

        output = result.stdout.strip()

        if "pointer" in output:

            reverse_host = (
                output.split("pointer")[-1]
                .strip()
                .rstrip('.')
            )

    except Exception:
        pass

    return ip, reverse_host

def check_port(ip, port):
    """Checks if the port is open on the given IP."""
    try:
        with socket.create_connection((ip, port), timeout=2) as sock:
            return True
    except (socket.timeout,
        ConnectionRefusedError,
        OSError):
        return False

def get_os(ttl):
    """Determines the operating system based on TTL."""

    try:

        ttl_value = int(ttl)

        if TTL_MIN_LINUX <= ttl_value <= TTL_MAX_LINUX:
            return 'Linux'

        elif TTL_MIN_WINDOWS <= ttl_value <= TTL_MAX_WINDOWS:
            return 'Windows'

    except:
        pass

    return 'Unknown'

def analyze_host(host, result_queue):
    """Analyzes a single host and puts results into the queue."""

    # Generates all possible variations
    hosts_to_test = [
        build_host(host, suffix) for suffix in HOST_SUFFIXES
    ]

    pinging_host = None
    ttl_value = 'Not found'

    # Tests hosts
    for h in hosts_to_test:
        result, ttl = ping(h)
        if result:
            pinging_host = h
            ttl_value = ttl
            break

    # Collects information
    if pinging_host:
        ip, reverse_host = dns_lookup(pinging_host)
        ssh_open = check_port(ip, 22) if ip else False
        rdp_open = check_port(ip, 3389) if ip else False
        os_name = get_os(ttl_value)
    else:
        ip, reverse_host = dns_lookup(hosts_to_test[0])
        ssh_open = check_port(ip, 22) if ip else False
        rdp_open = check_port(ip, 3389) if ip else False
        os_name = 'Not found'

    result_queue.put((
        host,
        pinging_host,
        reverse_host,
        'True' if pinging_host else 'False',
        ip or 'Not resolved',
        ttl_value,
        os_name,
        ssh_open,
        rdp_open
    ))

def analyze_hosts():
    """Analyzes hosts in the table and fills results."""
    global hosts_list

    if not hosts_list:
        messagebox.showwarning("Warning", "No hosts found in the table!")
        return

    progress['value'] = 0
    progress['maximum'] = len(hosts_list)
    app.update_idletasks()

    result_queue = queue.Queue()

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        for host in hosts_list:
            executor.submit(analyze_host, host, result_queue)

    def update_results():
        while not result_queue.empty():
            result = result_queue.get()

            for item in results_tree.get_children():
                if results_tree.item(item)['values'][0] == result[0]:
                    results_tree.item(item, values=result)

                    SO = result[6]
                    RDP_Aberta = result[8]
                    SSH_Aberta = result[7]
                    PING = result[3] == 'True'
                    DNS_Reverso = result[2]
                    HOST_PINGANDO = result[0]

                    DNS_INEXISTENTE = DNS_Reverso is None

                    Erro_DNS = (
                        DNS_Reverso is not None and not is_dns_compatible(HOST_PINGANDO, DNS_Reverso)
                    )

                    C_Windows_Acessivel_Remotamente = (
                        (SO == "Windows") and
                        is_dns_compatible(HOST_PINGANDO, DNS_Reverso) and
                        (RDP_Aberta is True)
                    )

                    C_Windows_Sem_Acesso_Remoto = (
                        (SO == "Windows") and
                        is_dns_compatible(HOST_PINGANDO, DNS_Reverso) and
                        (RDP_Aberta is False)
                    )

                    C_Linux_Acessivel_Remotamente = (
                        (SO == "Linux") and
                        is_dns_compatible(HOST_PINGANDO, DNS_Reverso) and
                        (SSH_Aberta is True)
                    )

                    C_Linux_Sem_Acesso_Remotamente = (
                        (SO == "Linux") and
                        is_dns_compatible(HOST_PINGANDO, DNS_Reverso) and
                        (SSH_Aberta is False)
                    )

                    Erro_DNS = (DNS_Reverso is not None and not is_dns_compatible(HOST_PINGANDO, DNS_Reverso))

                    if Erro_DNS:
                        results_tree.item(item, tags=('orange',))

                    elif C_Windows_Acessivel_Remotamente or C_Linux_Acessivel_Remotamente:
                        results_tree.item(item, tags=('green',))

                    elif C_Windows_Sem_Acesso_Remoto or C_Linux_Sem_Acesso_Remotamente:
                        results_tree.item(item, tags=('yellow',))

                    else:
                        results_tree.item(item, tags=('red',))

                    break

            progress['value'] += 1
            app.update_idletasks()

        app.after(100, update_results)

    app.after(100, update_results)
    

def paste_and_analyze(event=None):
    """Gets clipboard text, clears table, fills it and starts analysis."""
    global hosts_list
    try:
        clipboard_content = app.clipboard_get()
        hosts = clipboard_content.strip().splitlines()

        if len(hosts) > MAX_HOSTS:
            messagebox.showwarning("Warning", f"Maximum number of hosts allowed is {MAX_HOSTS}.")
            return

        results_tree.delete(*results_tree.get_children())
        hosts_list = []

        for host in hosts:
            if is_valid_host(host):
                results_tree.insert('', tk.END, values=(host, "", "", "", "", "", "", "", ""))
                hosts_list.append(host)

        app.after(1000, analyze_hosts)

    except tk.TclError:
        messagebox.showerror("Error", "Could not access clipboard.")
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred: {str(e)}")

def extract_report():
    """Generates an HTML report with host analysis summary."""
    hosts_data = []

    for item in results_tree.get_children():
        host_info = results_tree.item(item)['values']
        hosts_data.append({
            'host': host_info[0],
            'ping_result': host_info[3],
            'dns_reverse': host_info[2],
            'os_name': host_info[6],
            'tags': results_tree.item(item)['tags']
        })

    categories = {
        'Windows Remotely Accessible': [],
        'Linux Remotely Accessible': [],
        'Windows No Remote Access': [],
        'Linux No Remote Access': [],
        'Other Errors': []
    }

    for host in hosts_data:
        if 'green' in host['tags']:
            if host['os_name'] == 'Windows':
                categories['Windows Remotely Accessible'].append(host)
            elif host['os_name'] == 'Linux':
                categories['Linux Remotely Accessible'].append(host)
        elif 'yellow' in host['tags']:
            if host['os_name'] == 'Windows':
                categories['Windows No Remote Access'].append(host)
            elif host['os_name'] == 'Linux':
                categories['Linux No Remote Access'].append(host)
        else:
            categories['Other Errors'].append(host)

    html_content = """
    <html>
    <head>
    <title>Host Analysis Report</title>
    <style>
    body { font-family: Arial, sans-serif; }
    h1 { color: #007bff; }
    h2 { color: #343a40; }
    table { width: 100%; border-collapse: collapse; margin: 20px 0; }
    th, td { border: 1px solid #ddd; padding: 8px; }
    th { background-color: #f2f2f2; }
    </style>
    </head>
    <body>
    <h1>Host Analysis Report</h1>
    """

    for category, hosts in categories.items():
        html_content += f"<h2>{category}</h2>"
        if hosts:
            html_content += "<table><tr><th>Host</th><th>OS</th><th>Reverse DNS</th></tr>"
            for host in hosts:
                html_content += f"""
                <tr>
                <td>{host['host']}</td>
                <td>{host['os_name']}</td>
                <td>{host['dns_reverse']}</td>
                </tr>
                """
            html_content += "</table>"
        else:
            html_content += "<p>No hosts found in this category.</p>"

    html_content += "</body></html>"

    report_file_path = "hosts_report.html"
    with open(report_file_path, "w") as report_file:
        report_file.write(html_content)

    webbrowser.open(report_file_path)
    messagebox.showinfo("Report Generated", "Report generated successfully!")

def show_credits():
    """Opens a credits window."""
    credits_window = tk.Toplevel(app)
    credits_window.title("Credits")
    credits_window.geometry("400x300")
    credits_window.resizable(False, False)

    credits_frame = ttk.Frame(credits_window, padding="10")
    credits_frame.pack(expand=True, fill=tk.BOTH)

    title_label = tk.Label(credits_frame, text="Credits", font=("Helvetica", 16, "bold"))
    title_label.pack(pady=(0, 10))

    system_name = "System Name: HostFlow"
    description = "Description: Connectivity analysis system."
    author = "Designed by: Carlos Bezerra Vilela (Key: CDXL)"
    creation_date = "Creation Date: 27/03/2025"
    version = "Version: 0.1.0 (Beta)"
    license_info = "License: MIT"

    tk.Label(credits_frame, text=system_name, font=("Helvetica", 10)).pack(anchor='w', padx=5, pady=2)
    tk.Label(credits_frame, text=description, font=("Helvetica", 10)).pack(anchor='w', padx=5, pady=2)
    tk.Label(credits_frame, text=author, font=("Helvetica", 10)).pack(anchor='w', padx=5, pady=2)
    tk.Label(credits_frame, text=creation_date, font=("Helvetica", 10)).pack(anchor='w', padx=5, pady=2)
    tk.Label(credits_frame, text=version, font=("Helvetica", 10)).pack(anchor='w', padx=5, pady=2)
    tk.Label(credits_frame, text=license_info, font=("Helvetica", 10)).pack(anchor='w', padx=5, pady=2)

    close_button = ttk.Button(credits_frame, text="Close", command=credits_window.destroy)
    close_button.pack(pady=(10, 0))

    credits_window.transient(app)
    credits_window.grab_set()
    credits_window.focus_set()
    credits_window.wait_window()

def open_rdp(event, host_pingando):
    """Opens RDP connection for selected host."""

    if not host_pingando:
        messagebox.showwarning(
            "Warning",
            "No available pinging host for RDP connection."
        )
        return

    try:

        if IS_WINDOWS:

            subprocess.Popen(
                ['mstsc', f'/v:{host_pingando}']
            )

        else:

            rdp_client = shutil.which("xfreerdp")

            if not rdp_client:
                messagebox.showerror(
                    "Error",
                    "xfreerdp is not installed."
                )
                return

            subprocess.Popen(
                [rdp_client, f'/v:{host_pingando}']
            )

    except Exception as e:
        messagebox.showerror(
            "Error",
            f"Could not open RDP connection: {e}"
        )

def open_file():
    """Opens a file dialog and loads hosts."""
    global hosts_list, current_file_path

    file_path = filedialog.askopenfilename(title="Open Hosts File",
                                           filetypes=[("Text Files", "*.txt"), ("CSV Files", "*.csv")])
    if file_path:
        try:
            with open(file_path, 'r') as file:
                hosts = file.readlines()
                hosts = [host.strip() for host in hosts if is_valid_host(host.strip())]

            if len(hosts) > MAX_HOSTS:
                messagebox.showwarning("Warning", f"Maximum number of hosts allowed is {MAX_HOSTS}.")
                return

            results_tree.delete(*results_tree.get_children())
            hosts_list = []

            for host in hosts:
                results_tree.insert('', tk.END,
                                    values=(host, "", "", "", "", "", "", "", "", "", "", "", "", "", ""))
                hosts_list.append(host)

            current_file_path = file_path
            app.title(f"HostFlow - {os.path.splitext(os.path.basename(current_file_path))[0]}")

            app.after(1000, analyze_hosts)

        except Exception as e:
            messagebox.showerror("Error", f"Error opening file: {str(e)}")

def save_hosts():
    """Saves current hosts to the open file."""
    global current_file_path

    if current_file_path:
        try:
            with open(current_file_path, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file, delimiter=';')
                for item in results_tree.get_children():
                    host_info = results_tree.item(item)['values']
                    writer.writerow([host_info[0]])

            messagebox.showinfo("Success", f"Hosts saved successfully to: {current_file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Error saving hosts: {str(e)}")
    else:
        save_hosts_as()

def save_hosts_as():
    """Saves hosts to a user-selected file."""
    global current_file_path

    file_path = filedialog.asksaveasfilename(defaultextension=".csv",
                                             filetypes=[("CSV Files", "*.csv"), ("Text Files", "*.txt")])
    if file_path:
        current_file_path = file_path
        save_hosts()

def open_ssh(host):
    """Opens SSH connection."""

    ssh_key = simpledialog.askstring(
        "Access Key",
        "Enter access key:"
    )

    if not ssh_key:
        return

    try:

        if IS_WINDOWS:

            subprocess.Popen(
                f'start cmd /k ssh {ssh_key}@{host}',
                shell=True
            )

        else:

            terminal = (
                shutil.which("xterm")
                or shutil.which("konsole")
                or shutil.which("gnome-terminal")
            )

            if terminal:

                subprocess.Popen([
                    terminal,
                    '-e',
                    f'ssh {ssh_key}@{host}'
                ])

            else:

                subprocess.Popen([
                    'ssh',
                    f'{ssh_key}@{host}'
                ])

    except Exception as e:

        messagebox.showerror(
            "Error",
            f"Could not open SSH connection: {e}"
        )

def edit_host():
    """Edits selected host."""
    selected_items = results_tree.selection()

    if selected_items:
        selected_item = selected_items[0]
        current_host = results_tree.item(selected_item)['values'][0]

        new_host = simpledialog.askstring("Edit Host", "Edit host:", initialvalue=current_host)

        if new_host and is_valid_host(new_host):
            new_values = (new_host,) + tuple(results_tree.item(selected_item)['values'][1:])
            results_tree.item(selected_item, values=new_values)

            global hosts_list
            hosts_list = [new_host if host == current_host else host for host in hosts_list]
        else:
            messagebox.showerror("Error", "Invalid host. Please enter a valid host.")

def show_context_menu(event):
    """Shows context menu."""
    context_menu = tk.Menu(app, tearoff=0)

    item = results_tree.identify_row(event.y)

    if item:
        context_menu.add_command(label="Copy",
                                 command=lambda: copy_to_clipboard(results_tree.item(item)['values'][0]))

        edit_menu = tk.Menu(context_menu, tearoff=0)
        edit_menu.add_command(label="Modify", command=edit_host)
        context_menu.add_cascade(label="Edit", menu=edit_menu)

        connection_menu = tk.Menu(context_menu, tearoff=0)
        connection_menu.add_command(label="RDP Access",
                                    command=lambda: open_rdp(None, results_tree.item(item)['values'][1]))
        connection_menu.add_command(label="SSH Access",
                                    command=lambda: open_ssh(results_tree.item(item)['values'][1]))

        context_menu.add_cascade(label="Connection", menu=connection_menu)

        context_menu.add_command(label="Remove", command=lambda: remove_selected_row(None))

        context_menu.post(event.x_root, event.y_root)

def copy_to_clipboard(text):
    """Copies text to clipboard."""
    app.clipboard_clear()
    app.clipboard_append(text)

def remove_selected_row(event=None):
    """Removes selected rows from table."""
    selected_items = results_tree.selection()

    if selected_items:
        for selected_item in selected_items:
            item_value = results_tree.item(selected_item)['values'][0] if selected_item else None
            if item_value:
                results_tree.delete(selected_item)

        global hosts_list
        hosts_list = [host for host in hosts_list if
                      host not in [results_tree.item(item)['values'][0] for item in selected_items]]

dragged_item = None
dragged_item_index = None

def on_tree_select(event):
    """Captures selected item."""
    global dragged_item, dragged_item_index
    selected_item = results_tree.selection()
    if selected_item:
        dragged_item = selected_item[0]
        dragged_item_index = results_tree.index(dragged_item)

def on_tree_drag(event):
    """Updates dragged item position."""
    global dragged_item, dragged_item_index
    if dragged_item and dragged_item_index is not None:
        y = event.y
        item = results_tree.identify_row(y)
        if item and item != dragged_item:
            current_index = results_tree.index(item)
            if current_index != dragged_item_index:
                results_tree.move(dragged_item, '', current_index)
                dragged_item_index = current_index

def on_tree_release(event):
    """Releases dragged item."""
    global dragged_item
    dragged_item = None


def organize_by_color():
    """Organizes table items by tag colors."""
    items = results_tree.get_children()

    colored_items = {'red': [], 'green': [], 'yellow': [], 'orange': []}
    item_values = {}
    item_tags = {}

    for item in items:
        tags = results_tree.item(item)['tags']
        item_values[item] = results_tree.item(item)['values']
        item_tags[item] = tags
        if 'red' in tags:
            colored_items['red'].append(item)
        elif 'green' in tags:
            colored_items['green'].append(item)
        elif 'yellow' in tags:
            colored_items['yellow'].append(item)
        elif 'orange' in tags:
            colored_items['orange'].append(item)

    results_tree.delete(*items)

    for color in ['green', 'yellow', 'orange', 'red']:
        for item in colored_items[color]:
            new_item = results_tree.insert('', 'end', values=item_values[item])
            for tag in item_tags[item]:
                results_tree.item(new_item, tags=(tag,))


def show_quantitative_report():
    """Shows host count by category."""
    categories_count = {
        'Remotely Accessible': 0,
        'No Remote Access': 0,
        'DNS Error': 0,
        'Other Errors': 0
    }

    for item in results_tree.get_children():
        tags = results_tree.item(item)['tags']
        if 'green' in tags:
            categories_count['Remotely Accessible'] += 1
        elif 'yellow' in tags:
            categories_count['No Remote Access'] += 1
        elif 'orange' in tags or 'red' in tags:
            categories_count['Other Errors'] += 1
        else:
            categories_count['DNS Error'] += 1

    report_message = "\n".join(f"{category}: {count}" for category, count in categories_count.items())
    messagebox.showinfo("Host Summary", report_message)

def run_ping_script():
    try:
        subprocess.Popen([sys.executable, 'ping.py'])
    except Exception as e:
        messagebox.showerror("Error", f"Could not run ping test: {e}")


app = tk.Tk()

if IS_UNIX:
    app.tk.call('tk', 'scaling', 1.0)

from tkinter import font

default_font = font.nametofont("TkDefaultFont")
default_font.configure(size=8)

text_font = font.nametofont("TkTextFont")
text_font.configure(size=8)

fixed_font = font.nametofont("TkFixedFont")
fixed_font.configure(size=8)

menu_font = font.nametofont("TkMenuFont")
menu_font.configure(size=8)

heading_font = font.nametofont("TkHeadingFont")
heading_font.configure(size=8)


app.title("HostFlow")
app.geometry("1000x600")

menu_bar = tk.Menu(app)

file_menu = tk.Menu(menu_bar, tearoff=0)
file_menu.add_command(label="Open", command=open_file)
file_menu.add_command(label="Save Hosts", command=save_hosts)
file_menu.add_command(label="Save As", command=save_hosts_as)
menu_bar.add_cascade(label="File", menu=file_menu)

network_test_menu = tk.Menu(menu_bar, tearoff=0)
network_test_menu.add_command(label="Ping Test", command=run_ping_script)
menu_bar.add_cascade(label="Network Test", menu=network_test_menu)

organize_menu = tk.Menu(menu_bar, tearoff=0)
organize_menu.add_command(label="Organize by Color", command=organize_by_color)
menu_bar.add_cascade(label="Organize", menu=organize_menu)

analysis_menu = tk.Menu(menu_bar, tearoff=0)
analysis_menu.add_command(label="Quantitative", command=show_quantitative_report)
menu_bar.add_cascade(label="Analysis", menu=analysis_menu)

report_menu = tk.Menu(menu_bar, tearoff=0)
report_menu.add_command(label="Generate Report", command=extract_report)
menu_bar.add_cascade(label="Reports", menu=report_menu)

help_menu = tk.Menu(menu_bar, tearoff=0)
help_menu.add_command(label="About", command=show_credits)
menu_bar.add_cascade(label="Help", menu=help_menu)

app.config(menu=menu_bar)

frame = ttk.Frame(app)
frame.pack(pady=5, fill=tk.BOTH, expand=True)

columns = ("Host", "Pinging Host", "Reverse DNS", "Ping", "IP", "TTL", "OS", "SSH Open", "RDP Open")

results_tree = ttk.Treeview(frame, columns=columns, show='headings')

for col in columns:
    results_tree.heading(col, text=col)

fixed_width = 100

for col in columns:
    results_tree.column(col, width=fixed_width)

scrollbar_vertical = ttk.Scrollbar(frame, orient="vertical", command=results_tree.yview)
results_tree.configure(yscrollcommand=scrollbar_vertical.set)
scrollbar_vertical.pack(side='right', fill='y')

scrollbar_horizontal = ttk.Scrollbar(frame, orient="horizontal", command=results_tree.xview)
results_tree.configure(xscrollcommand=scrollbar_horizontal.set)
scrollbar_horizontal.pack(side='bottom', fill='x')

results_tree.pack(pady=5, fill=tk.BOTH, expand=True)

progress = ttk.Progressbar(app, orient="horizontal", length=400, mode="determinate")
progress.pack(pady=10)

results_tree.bind('<ButtonPress-1>', on_tree_select)
results_tree.bind('<B1-Motion>', on_tree_drag)
results_tree.bind('<ButtonRelease-1>', on_tree_release)

legend_frame = ttk.Frame(app)
legend_frame.pack(pady=5)

checkbox_vars = {
    'green': tk.BooleanVar(value=True),
    'yellow': tk.BooleanVar(value=True),
    'orange': tk.BooleanVar(value=True),
    'red': tk.BooleanVar(value=True)
}

def update_table_visibility():

    for item in results_tree.get_children(''):

        tags = results_tree.item(item)['tags']

        visible = any(
            checkbox_vars[color].get() and color in tags
            for color in checkbox_vars
        )

        if visible:

            try:
                results_tree.reattach(item, '', 'end')
            except:
                pass

        else:

            results_tree.detach(item)

def create_legend_item_with_checkbox(color, text):
    color_box = tk.Canvas(legend_frame, width=20, height=20, bg=color)
    color_box.pack(side=tk.LEFT, padx=5)
    checkbox = ttk.Checkbutton(legend_frame, text=text, variable=checkbox_vars[color],
                               command=update_table_visibility)
    checkbox.pack(side=tk.LEFT)

create_legend_item_with_checkbox('green', 'Remotely Accessible')
create_legend_item_with_checkbox('yellow', 'No Remote Access')
create_legend_item_with_checkbox('orange', 'DNS Error')
create_legend_item_with_checkbox('red', 'Other Errors')

update_table_visibility()

button_frame = ttk.Frame(app)
button_frame.pack(pady=10)

analyze_button = ttk.Button(button_frame, text="Analyze Hosts", command=analyze_hosts)
analyze_button.pack(side=tk.LEFT, padx=5)

app.bind('<Control-v>', paste_and_analyze)

results_tree.bind('<Double-1>', lambda event: open_rdp(event, results_tree.item(results_tree.selection())['values'][1]))
if IS_WINDOWS:
    results_tree.bind('<Button-3>', show_context_menu)
else:
    results_tree.bind('<ButtonRelease-3>', show_context_menu)
app.bind('<Delete>', remove_selected_row)

results_tree.tag_configure('red', background='red')
results_tree.tag_configure('green', background='green')
results_tree.tag_configure('yellow', background='yellow')
results_tree.tag_configure('orange', background='orange')



app.mainloop()
