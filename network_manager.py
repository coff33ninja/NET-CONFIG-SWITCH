import subprocess
import re
import tempfile
import os
import json # For parsing PowerShell JSON output

# Maximum message length for pystray notifications (Windows Shell_NotifyIcon szInfo limit is 256 WCHARs)
MAX_MESSAGE_LENGTH_FOR_NOTIFY = 250

def _sanitize_message_for_notification(message: str) -> str:
    """Ensures a message is suitable for pystray notification by truncating if too long."""
    if len(message) > MAX_MESSAGE_LENGTH_FOR_NOTIFY:
        return message[:MAX_MESSAGE_LENGTH_FOR_NOTIFY - 3] + "..."
    return message

def validate_ip(ip):
    """Validate IP address: each octet must be 0–255."""
    if not ip:
        return True
    pattern = r"^(?:(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$"
    return bool(re.match(pattern, ip))


def apply_network_config(adapter_name, config):
    """Apply network configuration using netsh."""
    try:
        for field in ["ip_address", "subnet_mask", "gateway", "dns_primary"]:
            if not validate_ip(config[field]):
                raise ValueError(f"Invalid {field}: {config[field]}")
        if config["dns_secondary"] and not validate_ip(config["dns_secondary"]):
            raise ValueError(f"Invalid dns_secondary: {config['dns_secondary']}")
        if config["router_ip"] and not validate_ip(config["router_ip"]):
            raise ValueError(f"Invalid router_ip: {config['router_ip']}")

        ip_cmd = f'netsh interface ip set address name="{adapter_name}" source=static addr={config["ip_address"]} mask={config["subnet_mask"]} gateway={config["gateway"]}'
        subprocess.run(ip_cmd, shell=True, check=True, capture_output=True, text=True)

        dns_cmd = f'netsh interface ip set dns name="{adapter_name}" source=static addr={config["dns_primary"]}'
        subprocess.run(dns_cmd, shell=True, check=True, capture_output=True, text=True)

        if config.get("dns_secondary"):
            dns_sec_cmd = f'netsh interface ip add dns name="{adapter_name}" addr={config["dns_secondary"]} index=2'
            subprocess.run(dns_sec_cmd, shell=True, check=True, capture_output=True, text=True)

        return True, "Network configuration applied successfully."
    except subprocess.CalledProcessError as e:
        error_message = f"Error applying configuration: {e}."
        if e.stderr:
            error_message += f" Details: {e.stderr.strip()}"
        elif e.stdout: # Some commands might output errors to stdout
            error_message += f" Details: {e.stdout.strip()}"
        return False, _sanitize_message_for_notification(error_message)
    except ValueError as e:
        return False, _sanitize_message_for_notification(f"Invalid configuration value: {e}")
    

def get_current_adapter_config(adapter_name):
    """Get current IP, subnet, gateway, and DNS settings for an adapter."""
    config = {
        "adapter_name": adapter_name,
        "ip_address": "",
        "subnet_mask": "",
        "gateway": "",
        "dns_primary": "",
        "dns": "",
        "dns_servers": "",
    }

    try:
        ip_config_cmd = f'netsh interface ip show config name="{adapter_name}"'
        result = subprocess.run(
            ip_config_cmd,
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            errors="ignore",
        )

        for line in result.stdout.splitlines():
            line = line.strip()
            if "DHCP enabled:" in line:
                config["dhcp_enabled"] = "Yes" in line
            elif "IP Address:" in line and "IPv6" not in line and "Default" not in line:
                match = re.search(r"IP Address:\s+([\d\.]+)", line)
                if match and not config["ip_address"]:
                    config["ip_address"] = match.group(1)
            elif "Subnet Mask:" in line or "Subnet Prefix:" in line:
                match = re.search(r"Subnet Mask:\s+([\d\.]+)", line)
                if not match:
                    match_prefix = re.search(r"\(mask ([\d\.]+)\)", line)
                    if match_prefix:
                        config["subnet_mask"] = match_prefix.group(1)
                elif match:
                    config["subnet_mask"] = match.group(1)
            elif "Default Gateway:" in line:
                match = re.search(r"Default Gateway:\s+([\d\.]+)", line)
                if match and not config["gateway"]:
                    config["gateway"] = match.group(1)

        dns_config_cmd = f'netsh interface ipv4 show dnsservers name="{adapter_name}"'
        result_dns = subprocess.run(
            dns_config_cmd,
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            errors="ignore",
        )
        dns_servers = []
        for line in result_dns.stdout.splitlines():
            line = line.strip()
            match = re.search(r"DHCP:\s+([\d\.]+)", line)
            if not match:
                match = re.search(r"Servers:\s+([\d\.]+)", line)
            if not match:
                match = re.match(r"([\d\.]+)", line)
            if match and validate_ip(match.group(1).strip()):
                dns_servers.append(match.group(1).strip())

        if dns_servers:
            config["dns_primary"] = dns_servers[0]
            if len(dns_servers) > 1:
                config["dns"] = dns_servers[1]

        return config, None
    except subprocess.CalledProcessError as e:
        error_message = f"Error getting current config for {adapter_name}: {e}."
        if e.stderr:
            error_message += f" Details: {e.stderr.strip()}"
        elif e.stdout:
            error_message += f" Details: {e.stdout.strip()}"
        return None, _sanitize_message_for_notification(error_message)
    except Exception as e:
        return None, _sanitize_message_for_notification(f"Unexpected error getting current config for {adapter_name}: {e}")
    

def set_adapter_to_dhcp(adapter_name):
    """Set the specified network adapter to obtain IP and DNS automatically (DHCP)."""
    try:
        subprocess.run(
            f'netsh interface ip set address name="{adapter_name}" source=dhcp',
            shell=True,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            f'netsh interface ipv4 set dnsservers name="{adapter_name}" source=dhcp',
            shell=True,
            check=True,
            capture_output=True,
            text=True,
        )
        return True, f"Adapter {adapter_name} set to DHCP successfully."
    except subprocess.CalledProcessError as e:
        error_message = f"Error setting {adapter_name} to DHCP: {e}."
        if e.stderr:
            error_message += f" Details: {e.stderr.strip()}"
        elif e.stdout:
            error_message += f" Details: {e.stdout.strip()}"
        return False, _sanitize_message_for_notification(error_message)

def _get_adapter_details_powershell() -> tuple[list[dict] | None, str | None]:
    """
    Fetches detailed network adapter information using PowerShell.
    Returns a list of dictionaries (each with 'Name' and 'InterfaceDescription')
    for connected adapters, or None and an error message.
    """
    try:
        # PowerShell command to get connected adapters and select Name and InterfaceDescription
        # Output is converted to JSON for easy parsing in Python
        ps_command = (
            "Get-NetAdapter | "
            "Where-Object {$_.Status -eq 'Up'} | "
            "Select-Object Name, InterfaceDescription | "
            "ConvertTo-Json -Compress"
        )
        full_command = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy", "Bypass",
            "-Command", ps_command
        ]

        result = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            check=True, # Raises CalledProcessError for non-zero exit codes
            errors="ignore"
        )
        
        if not result.stdout.strip(): # Handle empty output (no adapters found)
            return [], None

        adapters_data = json.loads(result.stdout)
        # If PowerShell returns a single object not in a list, wrap it
        if isinstance(adapters_data, dict):
            adapters_data = [adapters_data]
        return adapters_data, None
        
    except FileNotFoundError:
        return None, _sanitize_message_for_notification("PowerShell executable not found. Please ensure it's in your system PATH.")
    except subprocess.CalledProcessError as e:
        error_detail = e.stderr.strip() if e.stderr else e.stdout.strip()
        return None, _sanitize_message_for_notification(f"PowerShell command failed: {e}. Details: {error_detail}")
    except json.JSONDecodeError as e:
        return None, _sanitize_message_for_notification(f"Failed to parse PowerShell output as JSON: {e}. Output: {result.stdout[:100]}...") # Show partial output
    except Exception as e:
        return None, _sanitize_message_for_notification(f"An unexpected error occurred while fetching adapter details via PowerShell: {e}")

def list_adapters() -> tuple[list[tuple[str, str]], str | None]:
    """
    List available and connected network adapters.
    Uses PowerShell to get adapter names (short_name, detailed_name).
    Returns a list of tuples (short_name, detailed_name) and an optional message string.
    """
    result_adapters_list = []
    
    adapters_data, error_msg = _get_adapter_details_powershell()

    if error_msg:
        return [], error_msg
    
    if adapters_data is None: # Should be caught by error_msg, but as a safeguard
        return [], _sanitize_message_for_notification("Failed to retrieve adapter details from PowerShell (no data).")

    for adapter_info in adapters_data:
        # Ensure 'Name' and 'InterfaceDescription' keys exist, though Select-Object should guarantee them
        short_name = adapter_info.get("Name")
        detailed_name = adapter_info.get("InterfaceDescription")
        if short_name and detailed_name:
            result_adapters_list.append((short_name, detailed_name))
        elif short_name: # Fallback if InterfaceDescription is missing for some reason
            result_adapters_list.append((short_name, short_name))

    final_message = None
    if not result_adapters_list and not error_msg:
        final_message = _sanitize_message_for_notification("No connected (Status 'Up') network adapters found via PowerShell.")
        
    return result_adapters_list, final_message


def is_wifi_adapter(adapter_name):
    """Check if an adapter is a Wi-Fi adapter."""
    # This function might also benefit from WMI for more robust checking,
    # but for now, it uses netsh as per original.
    # Adapter name here is the 'short_name'.
    try:
        result = subprocess.run(
            f'netsh interface show interface name="{adapter_name}"',
            shell=True,
            capture_output=True,
            text=True,
            check=True, # Check=True to catch errors if adapter name is invalid for this command
            errors="ignore"
        )
        return result.stdout is not None and "Wireless" in result.stdout
    except subprocess.CalledProcessError:
        # This can happen if adapter_name is not recognized by 'netsh interface show interface'
        # or other command errors.
        return False
    except Exception:
        return False

# 4. Update has_wifi_support()
def get_available_networks():
    """Retrieve nearby Wi-Fi networks with SSID, auth type, and signal strength."""
    try:
        result = subprocess.run(
            "netsh wlan show networks mode=bssid",
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            errors="ignore",
        )
        networks = []
        current_ssid = None
        auth_type = None
        signal = None

        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("SSID"):
                if current_ssid and auth_type:
                    networks.append((current_ssid, auth_type, signal or "Unknown"))
                current_ssid = line.split(":", 1)[1].strip()
                auth_type = None
                signal = None
            elif "Authentication" in line:
                auth = line.split(":", 1)[1].strip()
                if auth == "Open":
                    auth_type = "open"
                elif auth == "WEP":
                    auth_type = "WEP"
                elif "WPA-PSK" in auth:
                    auth_type = "WPAPSK"
                elif "WPA2-PSK" in auth:
                    auth_type = "WPA2PSK"
                elif "WPA3-SAE" in auth:
                    auth_type = "WPA3SAE"
                else:
                    auth_type = "WPA2PSK"
            elif "Signal" in line:
                signal = line.split(":", 1)[1].strip()

        if current_ssid and auth_type:
            networks.append((current_ssid, auth_type, signal or "Unknown"))

        return networks, None
    except subprocess.CalledProcessError as e:
        error_detail = e.stderr.strip() if e.stderr else e.stdout.strip()
        return [], _sanitize_message_for_notification(f"Error retrieving Wi-Fi networks: {e}. Details: {error_detail}")
    except Exception as e:
        return [], _sanitize_message_for_notification(f"Unexpected error retrieving Wi-Fi networks: {e}")

def has_wifi_support():
    """Check if the system has Wi-Fi support (Wi-Fi adapter or profiles)."""
    adapters_tuples, _ = list_adapters() # list_adapters now returns list of tuples and msg
    has_wifi_adapter_flag = False
    if adapters_tuples: # Check if list is not empty
        has_wifi_adapter_flag = any(is_wifi_adapter(adapter_tuple[0]) for adapter_tuple in adapters_tuples)

    # get_wifi_profiles still returns (list, msg_or_none)
    profiles, _ = get_wifi_profiles()
    has_profiles_flag = bool(profiles) # True if profiles list is not empty

    return has_wifi_adapter_flag or has_profiles_flag


def get_wifi_profiles():
    """Retrieve available Wi-Fi profiles from the system with auth types."""
    try:
        result = subprocess.run(
            "netsh wlan show profiles",
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            errors="ignore"
        )
        profiles = []
        for line in result.stdout.splitlines():
            if "All User Profile" in line:
                ssid = line.split(":")[1].strip()
                auth_type, _ = get_wifi_auth_type(ssid)
                profiles.append((ssid, auth_type))
        return profiles, None
    except subprocess.CalledProcessError as e:
        error_detail = e.stderr.strip() if e.stderr else e.stdout.strip()
        return [], _sanitize_message_for_notification(f"Error retrieving Wi-Fi profiles: {e}. Details: {error_detail}")
    except Exception as e:
        return [], _sanitize_message_for_notification(f"Unexpected error retrieving Wi-Fi profiles: {e}")


def get_wifi_auth_type(ssid):
    """Retrieve the authentication type for a Wi-Fi profile."""
    try:
        result = subprocess.run(
            f'netsh wlan show profile name="{ssid}" key=clear',
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            errors="ignore",
        )
        auth_type = "WPA2PSK"
        for line in result.stdout.splitlines():
            if "Authentication" in line:
                auth = line.split(":")[1].strip()
                if auth == "Open":
                    auth_type = "open"
                elif auth == "WEP":
                    auth_type = "WEP"
                elif "WPA-PSK" in auth:
                    auth_type = "WPAPSK"
                elif "WPA2-PSK" in auth:
                    auth_type = "WPA2PSK"
                elif "WPA3-SAE" in auth:
                    auth_type = "WPA3SAE"
                break
        return auth_type, None
    except subprocess.CalledProcessError as e:
        error_detail = e.stderr.strip() if e.stderr else e.stdout.strip()
        return "WPA2PSK", _sanitize_message_for_notification(f"Error retrieving Wi-Fi auth type for {ssid}: {e}. Details: {error_detail}")
    except Exception as e:
         return "WPA2PSK", _sanitize_message_for_notification(f"Unexpected error retrieving Wi-Fi auth type for {ssid}: {e}")


def get_wifi_password(ssid):
    """Retrieve the password for a Wi-Fi profile."""
    try:
        result = subprocess.run(
            f'netsh wlan show profile name="{ssid}" key=clear',
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            errors="ignore",
        )
        for line in result.stdout.splitlines():
            if "Key Content" in line:
                password = line.split(":")[1].strip()
                return password, None
        return None, _sanitize_message_for_notification(f"Key Content not found for Wi-Fi profile {ssid}.")
    except subprocess.CalledProcessError as e:
        error_detail = e.stderr.strip() if e.stderr else e.stdout.strip()
        return None, _sanitize_message_for_notification(f"Error retrieving Wi-Fi password for {ssid}: {e}. Details: {error_detail}")
    except Exception as e:
        return None, _sanitize_message_for_notification(f"Unexpected error retrieving Wi-Fi password for {ssid}: {e}")


def apply_wifi_profile(ssid, password, adapter_name, auth_type="WPA2PSK"):
    """Apply a Wi-Fi profile to connect to a network."""
    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            profile_xml = generate_wifi_profile_xml(ssid, password, auth_type)
            f.write(profile_xml)
            temp_file_path = f.name

        add_profile_cmd = f'netsh wlan add profile filename="{temp_file_path}" interface="{adapter_name}"'
        subprocess.run(add_profile_cmd, shell=True, check=True, capture_output=True, text=True, errors="ignore")

        connect_cmd = f'netsh wlan connect name="{ssid}" interface="{adapter_name}"'
        subprocess.run(connect_cmd, shell=True, check=True, capture_output=True, text=True, errors="ignore")

        return True, _sanitize_message_for_notification(f"Wi-Fi profile for {ssid} applied and connected successfully.")
    except subprocess.CalledProcessError as e:
        error_detail = e.stderr.strip() if e.stderr else e.stdout.strip()
        return False, _sanitize_message_for_notification(f"Error applying Wi-Fi profile for {ssid}: {e}. Details: {error_detail}")
    except Exception as e:
        return False, _sanitize_message_for_notification(f"Unexpected error applying Wi-Fi profile for {ssid}: {e}")
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)


def generate_wifi_profile_xml(ssid, password, auth_type):
    """Generate Wi-Fi profile XML based on authentication type."""
    if auth_type == "open":
        security = """
            <security>
                <authEncryption>
                    <authentication>open</authentication>
                    <encryption>none</encryption>
                    <useOneX>false</useOneX>
                </authEncryption>
            </security>
        """
    elif auth_type == "WEP":
        security = f"""
            <security>
                <authEncryption>
                    <authentication>open</authentication>
                    <encryption>WEP</encryption>
                    <useOneX>false</useOneX>
                </authEncryption>
                <sharedKey>
                    <keyType>networkKey</keyType>
                    <protected>false</protected>
                    <keyMaterial>{password}</keyMaterial>
                </sharedKey>
            </security>
        """
    else:
        auth_map = {
            "WPAPSK": ("WPA-PSK", "TKIP"),
            "WPA2PSK": ("WPA2-PSK", "AES"),
            "WPA3SAE": ("WPA3-SAE", "AES"),
        }
        auth, enc = auth_map.get(auth_type, ("WPA2-PSK", "AES"))
        security = f"""
            <security>
                <authEncryption>
                    <authentication>{auth}</authentication>
                    <encryption>{enc}</encryption>
                    <useOneX>false</useOneX>
                </authEncryption>
                <sharedKey>
                    <keyType>passPhrase</keyType>
                    <protected>false</protected>
                    <keyMaterial>{password}</keyMaterial>
                </sharedKey>
            </security>
        """

    return f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{ssid}</name>
    <SSIDConfig>
        <SSID>
            <name>{ssid}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>auto</connectionMode>
    <MSM>
        {security}
    </MSM>
</WLANProfile>"""

def get_adapter_statuses(saved_configs):
    """
    Fetch the statuses of all active adapters and compare them with saved configurations.
    Returns a dictionary of adapter statuses and an optional error message.
    """
    adapter_statuses = {}
    active_adapters, list_err = list_adapters()
    if list_err:
        return adapter_statuses, list_err

    for short_name, detailed_name in active_adapters:
        live_config, get_err = get_current_adapter_config(short_name)
        if get_err and not live_config:
            adapter_statuses[short_name] = _sanitize_message_for_notification(f"Error: {get_err}")
        elif live_config:
            if live_config.get('dhcp_enabled'):
                adapter_statuses[short_name] = "DHCP"
            else:
                status_found = False
                for profile_name, saved_profile_data in saved_configs.get("networks", {}).items():
                    if (saved_profile_data.get('adapter_name') == short_name and
                        saved_profile_data.get('ip_address') == live_config.get('ip_address') and
                        saved_profile_data.get('subnet_mask') == live_config.get('subnet_mask') and
                        saved_profile_data.get('gateway') == live_config.get('gateway')):
                        adapter_statuses[short_name] = f"Static: {profile_name}"
                        status_found = True
                        break
                if not status_found:
                    adapter_statuses[short_name] = "Static: (Custom/Unsaved)"
    return adapter_statuses, None
