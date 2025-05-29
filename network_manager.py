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
        subprocess.run(ip_cmd, shell=True, check=True, capture_output=True)

        dns_cmd = f'netsh interface ip set dns name="{adapter_name}" source=static addr={config["dns_primary"]}'
        subprocess.run(dns_cmd, shell=True, check=True, capture_output=True)

        if config.get("dns_secondary"):
            dns_sec_cmd = f'netsh interface ip add dns name="{adapter_name}" addr={config["dns_secondary"]} index=2'
            subprocess.run(dns_sec_cmd, shell=True, check=True, capture_output=True)

        return True
    except (subprocess.CalledProcessError, ValueError) as e:
        print(f"Error applying configuration: {str(e)}")
        return False


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

        return config
    except subprocess.CalledProcessError as e:
        print(
            f"Error getting current config for {adapter_name}: {e.stderr if e.stderr else e.stdout}"
        )
        return None
    except Exception as e:
        print(f"Unexpected error getting current config for {adapter_name}: {e}")
        return None


def set_adapter_to_dhcp(adapter_name):
    """Set the specified network adapter to obtain IP and DNS automatically (DHCP)."""
    try:
        subprocess.run(
            f'netsh interface ip set address name="{adapter_name}" source=dhcp',
            shell=True,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            f'netsh interface ipv4 set dnsservers name="{adapter_name}" source=dhcp',
            shell=True,
            check=True,
            capture_output=True,
        )
        print(f"Adapter {adapter_name} set to DHCP successfully.")
        return True
    except subprocess.CalledProcessError as e:
        print(
            f"Error setting {adapter_name} to DHCP: {e.stderr.decode() if e.stderr else e.stdout.decode()}"
        )
        return False


def list_adapters():
    """List available and connected network adapters using 'netsh interface ip show interfaces'."""
    adapters = []
    try:
        cmd = "netsh interface ip show interfaces"
        # Using text=True implies default system encoding. errors='ignore' handles potential decoding issues.
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False, errors="ignore")

        if result.returncode != 0:
            print(f"Error executing '{cmd}': RC={result.returncode}, Stderr: {result.stderr}, Stdout: {result.stdout}")
            return [] # Return empty list on command failure

        # Regex to parse each line of the output.
        # Example line:  16          25        1500  connected     Ethernet
        # Example line:  14          35        1500  connected     VMware Network Adapter VMnet1
        # This regex captures the state and the full name of the interface.
        line_regex = re.compile(r"^\s*\d+\s+\S+\s+\S+\s+(connected|disconnected|disabled)\s+(.+)$")

        for line in result.stdout.splitlines():
            match = line_regex.match(line.strip())
            if match:
                state = match.group(1).strip().lower()
                name = match.group(2).strip()
                # Only include adapters that are 'connected' and not the loopback interface.
                if state == "connected" and name.lower() != "loopback pseudo-interface 1":
                    adapters.append(name)

    except FileNotFoundError:
        print(f"Error: 'netsh' command not found.")
        return []
    except Exception as e:
        print(f"Unexpected error in list_adapters: {e}")
        return adapters

    return adapters


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
    except Exception as e: # General catch for other unexpected issues
        print(f"Error in is_wifi_adapter for '{adapter_name}': {e}")
        return False


def get_available_networks():
    """Retrieve nearby Wi-Fi networks with SSID, auth type, and signal strength."""
    try:
        result = subprocess.run(
            "netsh wlan show networks mode=bssid",
            shell=True,
            capture_output=True,
            text=True,
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
                elif auth == "WPA-PSK":
                    auth_type = "WPAPSK"
                elif auth == "WPA2-PSK":
                    auth_type = "WPA2PSK"
                elif auth == "WPA3-SAE":
                    auth_type = "WPA3SAE"
                else:
                    auth_type = "WPA2PSK"  # Default
            elif "Signal" in line:
                signal = line.split(":", 1)[1].strip()

        if current_ssid and auth_type:
            networks.append((current_ssid, auth_type, signal or "Unknown"))

        return networks
    except subprocess.CalledProcessError as e:
        print(f"Error retrieving networks: {e.stderr.decode()}")
        return []


def has_wifi_support():
    """Check if the system has Wi-Fi support (Wi-Fi adapter or profiles)."""
    adapters = list_adapters()
    has_wifi_adapter = any(is_wifi_adapter(adapter) for adapter in adapters)
    has_profiles = bool(get_wifi_profiles())
    return has_wifi_adapter or has_profiles


def get_wifi_profiles():
    """Retrieve available Wi-Fi profiles from the system with auth types."""
    try:
        result = subprocess.run(
            "netsh wlan show profiles", shell=True, capture_output=True, text=True
        )
        profiles = []
        for line in result.stdout.splitlines():
            if "All User Profile" in line:
                ssid = line.split(":")[1].strip()
                auth_type = get_wifi_auth_type(ssid)
                profiles.append((ssid, auth_type))
        return profiles
    except subprocess.CalledProcessError as e:
        print(f"Error retrieving Wi-Fi profiles: {e.stderr.decode()}")
        return []


def get_wifi_auth_type(ssid):
    """Retrieve the authentication type for a Wi-Fi profile."""
    try:
        result = subprocess.run(
            f'netsh wlan show profile name="{ssid}" key=clear',
            shell=True,
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            if "Authentication" in line:
                auth = line.split(":")[1].strip()
                if auth == "Open":
                    return "open"
                elif auth == "WEP":
                    return "WEP"
                elif auth == "WPA-PSK":
                    return "WPAPSK"
                elif auth == "WPA2-PSK":
                    return "WPA2PSK"
                elif auth == "WPA3-SAE":
                    return "WPA3SAE"
        return "WPA2PSK"  # Default
    except subprocess.CalledProcessError:
        return "WPA2PSK"


def get_wifi_password(ssid):
    """Retrieve the password for a Wi-Fi profile."""
    try:
        result = subprocess.run(
            f'netsh wlan show profile name="{ssid}" key=clear',
            shell=True,
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            if "Key Content" in line:
                return line.split(":")[1].strip()
        return None
    except subprocess.CalledProcessError:
        return None


def apply_wifi_profile(ssid, password, adapter_name, auth_type="WPA2PSK"):
    """Apply a Wi-Fi profile to connect to a network."""
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            profile_xml = generate_wifi_profile_xml(ssid, password, auth_type)
            f.write(profile_xml)
            temp_file = f.name

        subprocess.run(
            f'netsh wlan add profile filename="{temp_file}" interface="{adapter_name}"',
            shell=True,
            check=True,
        )
        subprocess.run(
            f'netsh wlan connect name="{ssid}" interface="{adapter_name}"',
            shell=True,
            check=True,
        )
        os.unlink(temp_file)
        return True
    except subprocess.CalledProcessError as e:
        print(
            f"Error applying Wi-Fi profile: {e.stderr.decode() if e.stderr else e.stdout.decode()}"
        )
        return False
    finally:
        if os.path.exists(temp_file):
            os.unlink(temp_file)


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
