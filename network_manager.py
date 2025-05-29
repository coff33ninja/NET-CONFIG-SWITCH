import subprocess
import re
import xml.etree.ElementTree as ET
import tempfile
import os

# 1. Add WMI Import and Availability Check
# Requires: pip install WMI (for detailed adapter names on Windows)
# pywin32 is often a dependency for WMI and might be needed as well.
try:
    import wmi
    WMI_AVAILABLE = True
except ImportError:
    WMI_AVAILABLE = False
    # Optional: print a one-time warning for developers/users if needed
    # print("Warning: WMI library not found. Detailed adapter names will not be available. "
    #       "Install with: pip install WMI pywin32")


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
        return False, error_message
    except ValueError as e:
        return False, f"Invalid configuration value: {e}"


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
            elif "IP Address:" in line and not "IPv6" in line and not "Default" in line:
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
        return None, error_message
    except Exception as e:
        return None, f"Unexpected error getting current config for {adapter_name}: {e}"


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
        return False, error_message

# 2. Implement get_adapter_details_wmi()
def get_adapter_details_wmi() -> list[dict]:
    """
    Fetches detailed network adapter information using WMI (Windows Management Instrumentation).
    Returns a list of dictionaries, each containing 'short_name', 'detailed_name', and 'index'.
    Returns an empty list if WMI is not available or if an error occurs.
    """
    if not WMI_AVAILABLE:
        return []

    adapter_details = []
    try:
        c = wmi.WMI()
        # Query for adapters that have a NetConnectionID (usually implies they are configurable in Network Connections),
        # are physical adapters, and are network enabled.
        raw_adapters = c.Win32_NetworkAdapter(NetConnectionIDIsNotNull=True, PhysicalAdapter=True, NetEnabled=True)

        for adapter in raw_adapters:
            # Use Description if available and not None/empty, otherwise fallback to Name.
            # Some virtual adapters might have Name but no useful Description.
            # NetConnectionID is typically the "short name" seen in netsh or Network Connections UI.
            detailed_name = adapter.Description if adapter.Description else adapter.Name
            adapter_details.append({
                'short_name': adapter.NetConnectionID,
                'detailed_name': detailed_name,
                'index': adapter.InterfaceIndex # InterfaceIndex can be useful for other operations
            })
    except Exception as e:
        # Using print here as this is a utility function; logging would be better in a larger app.
        print(f"Error fetching WMI adapter details: {e}")
        return [] # Return empty list on error
    return adapter_details

# 3. Modify list_adapters()
def list_adapters() -> tuple[list[tuple[str, str]], str | None]:
    """
    List available and connected network adapters.
    Uses netsh for primary listing and WMI for detailed names if available.
    Returns a list of tuples (short_name, detailed_name) and an optional message string.
    """
    parsed_short_names = []
    netsh_message = None
    wmi_message = None
    result_adapters_list = []

    try:
        cmd = "netsh interface ip show interfaces"
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
            errors="ignore"
        )

        if result.returncode != 0:
            error_detail = result.stderr.strip() if result.stderr else result.stdout.strip()
            netsh_message = f"Error executing 'netsh interface ip show interfaces': RC={result.returncode}. Details: {error_detail}"
        else:
            line_regex = re.compile(r"^\s*\d+\s+\S+\s+\S+\s+(connected|disconnected|disabled)\s+(.+)$")
            for line in result.stdout.splitlines():
                match = line_regex.match(line.strip())
                if match:
                    state = match.group(1).strip().lower()
                    name = match.group(2).strip()
                    if state == "connected" and name.lower() != "loopback pseudo-interface 1":
                        parsed_short_names.append(name)
            if not parsed_short_names:
                netsh_message = "No connected adapters found via netsh."

    except FileNotFoundError:
        netsh_message = "Error: 'netsh' command not found."
    except Exception as e:
        netsh_message = f"Unexpected error in netsh part of list_adapters: {e}"

    # WMI part
    wmi_map = {}
    if WMI_AVAILABLE:
        wmi_details_list = get_adapter_details_wmi()
        if wmi_details_list:
            wmi_map = {item['short_name']: item['detailed_name'] for item in wmi_details_list}
        else:
            # WMI is available but returned no data or get_adapter_details_wmi itself had an internal error (already printed by it)
             wmi_message = "WMI query failed or returned no detailed adapter data."
    else:
        wmi_message = "WMI library not available; detailed adapter names could not be fetched."

    # Combine results
    for short_name in parsed_short_names:
        detailed_name = wmi_map.get(short_name, short_name) # Fallback to short_name
        result_adapters_list.append((short_name, detailed_name))

    # Combine messages
    final_message = None
    if netsh_message and wmi_message:
        final_message = f"{netsh_message} {wmi_message}"
    else:
        final_message = netsh_message or wmi_message

    if not result_adapters_list and not final_message: # If list is empty and no errors, means no adapters
        final_message = "No connected network adapters found."

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
        return [], f"Error retrieving Wi-Fi networks: {e}. Details: {error_detail}"
    except Exception as e:
        return [], f"Unexpected error retrieving Wi-Fi networks: {e}"

# 4. Update has_wifi_support()
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
        return [], f"Error retrieving Wi-Fi profiles: {e}. Details: {error_detail}"
    except Exception as e:
        return [], f"Unexpected error retrieving Wi-Fi profiles: {e}"


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
        return "WPA2PSK", f"Error retrieving Wi-Fi auth type for {ssid}: {e}. Details: {error_detail}"
    except Exception as e:
         return "WPA2PSK", f"Unexpected error retrieving Wi-Fi auth type for {ssid}: {e}"


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
        return None, f"Key Content not found for Wi-Fi profile {ssid}."
    except subprocess.CalledProcessError as e:
        error_detail = e.stderr.strip() if e.stderr else e.stdout.strip()
        return None, f"Error retrieving Wi-Fi password for {ssid}: {e}. Details: {error_detail}"
    except Exception as e:
        return None, f"Unexpected error retrieving Wi-Fi password for {ssid}: {e}"


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

        return True, f"Wi-Fi profile for {ssid} applied and connected successfully."
    except subprocess.CalledProcessError as e:
        error_detail = e.stderr.strip() if e.stderr else e.stdout.strip()
        return False, f"Error applying Wi-Fi profile for {ssid}: {e}. Details: {error_detail}"
    except Exception as e:
        return False, f"Unexpected error applying Wi-Fi profile for {ssid}: {e}"
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
