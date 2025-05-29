import subprocess
import re
import xml.etree.ElementTree as ET
import tempfile
import os


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
            text=True, # Ensure text=True for stderr/stdout decoding
        )
        subprocess.run(
            f'netsh interface ipv4 set dnsservers name="{adapter_name}" source=dhcp',
            shell=True,
            check=True,
            capture_output=True,
            text=True, # Ensure text=True for stderr/stdout decoding
        )
        return True, f"Adapter {adapter_name} set to DHCP successfully."
    except subprocess.CalledProcessError as e:
        error_message = f"Error setting {adapter_name} to DHCP: {e}."
        if e.stderr:
            error_message += f" Details: {e.stderr.strip()}"
        elif e.stdout: # Some commands might output errors to stdout
            error_message += f" Details: {e.stdout.strip()}"
        return False, error_message


def list_adapters():
    """List available and connected network adapters using 'netsh interface ip show interfaces'."""
    adapters = []
    try:
        cmd = "netsh interface ip show interfaces"
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            check=False,  # check=False to handle return codes manually
            errors="ignore"
        )

        if result.returncode != 0:
            error_detail = result.stderr.strip() if result.stderr else result.stdout.strip()
            return [], f"Error executing '{cmd}': RC={result.returncode}. Details: {error_detail}"

        line_regex = re.compile(r"^\s*\d+\s+\S+\s+\S+\s+(connected|disconnected|disabled)\s+(.+)$")
        for line in result.stdout.splitlines():
            match = line_regex.match(line.strip())
            if match:
                state = match.group(1).strip().lower()
                name = match.group(2).strip()
                if state == "connected" and name.lower() != "loopback pseudo-interface 1":
                    adapters.append(name)
        return adapters, None
    except FileNotFoundError:
        return [], "Error: 'netsh' command not found."
    except Exception as e:
        return [], f"Unexpected error in list_adapters: {e}"


def is_wifi_adapter(adapter_name):
    """Check if an adapter is a Wi-Fi adapter."""
    try:
        result = subprocess.run(
            f'netsh interface show interface name="{adapter_name}"',
            shell=True,
            capture_output=True,
            text=True,
        )
        # Check if stdout is not None before checking "Wireless" in it
        return result.stdout is not None and "Wireless" in result.stdout
    except subprocess.CalledProcessError: # Specific error for command failure
        return False
    except Exception: # General catch for other unexpected issues
        return False


def get_available_networks():
    """Retrieve nearby Wi-Fi networks with SSID, auth type, and signal strength."""
    try:
        # The command `netsh wlan show networks mode=bssid` should have check=True
        # as a failure to run this command means no networks can be retrieved.
        result = subprocess.run(
            "netsh wlan show networks mode=bssid",
            shell=True,
            check=True, # Ensure command success is checked
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
                auth_type = None # Reset for the new network
                signal = None    # Reset for the new network
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
                    auth_type = "WPA2PSK"  # Default or handle as unknown
            elif "Signal" in line:
                signal = line.split(":", 1)[1].strip()

        if current_ssid and auth_type: # Add the last network found
            networks.append((current_ssid, auth_type, signal or "Unknown"))

        return networks, None
    except subprocess.CalledProcessError as e:
        error_detail = e.stderr.strip() if e.stderr else e.stdout.strip()
        return [], f"Error retrieving Wi-Fi networks: {e}. Details: {error_detail}"
    except Exception as e: # Catch other potential errors
        return [], f"Unexpected error retrieving Wi-Fi networks: {e}"


def has_wifi_support():
    """Check if the system has Wi-Fi support (Wi-Fi adapter or profiles)."""
    adapters, _ = list_adapters()
    has_wifi_adapter = any(is_wifi_adapter(adapter) for adapter in adapters)

    profiles, _ = get_wifi_profiles() # Adjusted to handle new return type
    has_profiles = bool(profiles)
    return has_wifi_adapter or has_profiles


def get_wifi_profiles():
    """Retrieve available Wi-Fi profiles from the system with auth types."""
    try:
        # Ensure check=True for critical command
        result = subprocess.run(
            "netsh wlan show profiles",
            shell=True,
            check=True, # Ensure command success is checked
            capture_output=True,
            text=True,
            errors="ignore"
        )
        profiles = []
        for line in result.stdout.splitlines():
            if "All User Profile" in line:
                ssid = line.split(":")[1].strip()
                # get_wifi_auth_type now also returns a tuple (auth_type, error_message)
                # We only need auth_type here, or handle error if necessary
                auth_type, _ = get_wifi_auth_type(ssid) # Assuming success for now
                profiles.append((ssid, auth_type))
        return profiles, None
    except subprocess.CalledProcessError as e:
        error_detail = e.stderr.strip() if e.stderr else e.stdout.strip()
        return [], f"Error retrieving Wi-Fi profiles: {e}. Details: {error_detail}"
    except Exception as e: # Catch other potential errors
        return [], f"Unexpected error retrieving Wi-Fi profiles: {e}"


def get_wifi_auth_type(ssid):
    """Retrieve the authentication type for a Wi-Fi profile."""
    try:
        result = subprocess.run(
            f'netsh wlan show profile name="{ssid}" key=clear',
            shell=True,
            check=True, # Ensure command success is checked
            capture_output=True,
            text=True,
            errors="ignore",
        )
        auth_type = "WPA2PSK" # Default
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
                break # Found authentication, no need to parse further
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
            check=True, # Ensure command success is checked
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
    except Exception as e: # Catch other potential errors
        return None, f"Unexpected error retrieving Wi-Fi password for {ssid}: {e}"


def apply_wifi_profile(ssid, password, adapter_name, auth_type="WPA2PSK"):
    """Apply a Wi-Fi profile to connect to a network."""
    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            profile_xml = generate_wifi_profile_xml(ssid, password, auth_type)
            f.write(profile_xml)
            temp_file_path = f.name

        # Add profile
        add_profile_cmd = f'netsh wlan add profile filename="{temp_file_path}" interface="{adapter_name}"'
        subprocess.run(add_profile_cmd, shell=True, check=True, capture_output=True, text=True, errors="ignore")

        # Connect to network
        connect_cmd = f'netsh wlan connect name="{ssid}" interface="{adapter_name}"'
        subprocess.run(connect_cmd, shell=True, check=True, capture_output=True, text=True, errors="ignore")

        return True, f"Wi-Fi profile for {ssid} applied and connected successfully."
    except subprocess.CalledProcessError as e:
        error_detail = e.stderr.strip() if e.stderr else e.stdout.strip()
        return False, f"Error applying Wi-Fi profile for {ssid}: {e}. Details: {error_detail}"
    except Exception as e: # Catch other errors like tempfile issues
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
    else:  # WPAPSK, WPA2PSK, WPA3SAE
        auth_map = {
            "WPAPSK": ("WPA-PSK", "TKIP"),  # Corrected
            "WPA2PSK": ("WPA2-PSK", "AES"), # Corrected
            "WPA3SAE": ("WPA3-SAE", "AES"), # Corrected
        }
        # The default in .get should also use the corrected form if it's meant to be a fallback for "WPA2PSK" itself
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
