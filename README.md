# Network Configuration Manager

## Overview
The Network Configuration Manager is a Python-based tool for managing network configurations, Wi-Fi profiles, and router login pages. It provides a system tray application, a PyQt6-based GUI, and a custom browser for router login with HTTPS and cookie support. The application dynamically adapts its interface to support Wi-Fi management only when Wi-Fi adapters or profiles are detected, replacing the Windows’ built-in Wi-Fi manager with database-backed profile management. It includes nearby Wi-Fi network scanning to connect to or save discovered networks and enhanced router browser features for improved usability.

## Key Features
- **SQLite Database**: Stores network configurations, Wi-Fi profiles, bookmarks, history, and snapshots.
- **System Tray Application**: Quick access to network configurations, Wi-Fi profiles, and nearby Wi-Fi networks (when Wi-Fi is supported).
- **Custom Router Browser**:
  - HTTPS support with automatic fallback to HTTP fallback.
  - Cookie persistence and auto-fill for login forms.
  - Page snapshots to save current router configuration pages.
  - Quick credential switching between saved logins.
  - Network status display for current adapter settings.
- **PyQt6 GUI**: Manage network configurations and Wi-Fi profiles with an intuitive, dynamic interface.
- **Dynamic Wi-Fi Management**:
  - Wi-Fi section appears only if a Wi-Fi adapter or profiles are detected.
  - Replaces Windows’ Wi-Fi manager with database-backed profile storage.
  - Supports multiple profiles per configuration with authentication types (Open, WEP, WPA-PSK, WPA2-PSK, WPA3-SAE).
- **Nearby Network Scanning**:
  - Scans for nearby Wi-Fi networks with SSID, authentication type, and signal strength.
  - Connect to or save scanned networks via the GUI or system tray.
- **Dynamic Menu Updates**: Automatically refreshes the system tray menu when configurations or profiles change.
- **Cross-Module Integration**: Combines database management, network configuration, Wi-Fi management, and browser functionality seamlessly.

## Project Structure
```
project_folder/
├── network.ico           # System Tray icon for the system tray
├── cookies/             # Directory for cookies and snapshots
├── db_manager.py              # SQLite database operations
├── network_manager.py         # Network configuration and Wi-Fi management using netsh
├── router_browser.py      # Custom browser for router login
├── settings_gui.py         # PyQt6-based GUI for managing configurations
├── tray_app.py           # Main script for the system tray application
```

## Prerequisites
- **Python Version**: 3.8 or higher.
- **Dependencies**:
  ```bash
  pip install PyQt6 pystray pillow keyring PyQt6-WebEngine pyinstaller cryptography WMI pywin32
  python .venv\Lib\site-packages\win32\scripts\pywin32_postinstall.py -install
  ```
- **Administrator Privileges**: Required for `netsh` commands.
- **Network Icon**: Ensure `network.ico` is in the project root.

## Setup Instructions
1. Clone the repository and navigate to the project folder.
2. Ensure the following are present:
   - `network.ico`: System Tray icon.
   - `cookies/`: Directory for cookie and snapshot storage.
   - Python modules: `db_manager.py`, `network_manager.py`, `router_browser.py`, `settings_gui.py`, `tray_app.py`.
3. Run the application with administrator privileges:
   ```bash
   python tray_app.py
   ```

## Features and Usage

### 1. System Tray Application
- **Access Configurations**: Right-click to apply network configurations (e.g., "Office").
- **Wi-Fi Profiles (Wi-Fi Supported)**: Manage saved Wi-Fi profiles in the "Wi-Fi Profiles" submenu.
- **Nearby Networks (Wi-Fi Supported)**: View and connect to nearby Wi-Fi networks, prompting for credentials in the GUI.
- **Settings**: Open the PyQt6 GUI for advanced management.
- **Exit**: Close the application.

### 2. Wi-Fi Management (Dynamic)
Available when Wi-Fi is detected, replacing Windows’ Wi-Fi manager:
- **Import System Profiles**: Import existing Wi-Fi profiles with authentication types and passwords.
- **Scan Nearby Networks**: List available Wi-Fi networks with SSID, authentication type, and signal strength.
- **Save Profiles**: Save multiple profiles per configuration (Open, WEP, WPA-PSK, WPA2-PSK, WPA3-SAE).
- **Apply Profiles**: Connect via GUI or tray menu.
- **Delete Profiles**: Remove profiles, persisted in the database.
- **Database Backup**: Profiles stored in SQLite for persistence.

### 3. PyQt6 Settings GUI
- **Dynamic Interface**: Wi-Fi section shown only with Wi-Fi support.
- **Add/Edit/Delete Configurations**: Specify adapter, IP, subnet, gateway, DHCP, DNS, and router details.
- **Wi-Fi Profile Management**:
  - Import system profiles or scan nearby networks.
  - Save, delete, or apply profiles with authentication types.
- **View Configurations**: Display configurations and Wi-Fi profiles in a table.

### 4. Custom Router Browser
- **HTTPS Support**: Starts with HTTPS, falls back to HTTP with a "Try HTTP" button.
- **Cookie Persistence**: Stores cookies in `cookies/<router_ip>` for session reuse.
- **Redirect Handling**: Refreshes to original IP if redirected to `.com`, `.net`, etc.
- **Bookmarks and History**: Save and access bookmarks and history for the router.
- **Page Snapshots**: Save screenshots of router pages to `cookies/<router_ip>/snapshot_<timestamp>.png`.
- **Quick Credential Switch**: Cycle through saved credentials with a button.
- **Network Status**: Shows current IP and gateway in the status bar.

## Example Workflow
### With Wi-Fi Support
1. **Run Application**:
   - Start `tray_app.py` as admin; tray icon appears.
   - Apply configuration (e.g., "Office"), connecting to associated Wi-Fi.
   - Open router login page if enabled.
   - Manage configurations in GUI (e.g., add "Lab" with IP `10.0.0.100`).
   - Scan nearby networks, save a profile (e.g., "MyWiFi (WPA2PSK)"), and connect.
   - Use router browser, save a snapshot, or switch credentials.

### Without Wi-Fi Support
- Same as above, but Wi-Fi and nearby network options are hidden.

## Example Database Structure
```python
{
    "networks": {
        "Office": {
            "adapter_name": "Wi-Fi",
            "ip_address": "192.168.1.100",
            "subnet_mask": "255.255.255.255.0",
            "gateway": "192.168.1.1",
            "dns_primary": "8.8.8.8",
            "dns": "8.8.4.4",
            "router_ip": "192.168.1.254",
            "router_port": "8080",
            "open_router": True
        }
    },
    "wifi_profiles": [
        {"config_name": "Office", "ssid": "MyWiFi", "password": "pass123", "auth_type": "WPA2PSK"},
        {"config_name": "Office", "ssid": "GuestWiFi", "password": "", "auth_type": "open"}
    ]
}
```

## Notes
- **Dynamic Wi-Fi Support**: Detects Wi-Fi adapters/profiles using `netsh`.
- **Network Adapter Detection**: For general network configurations, the application relies on `netsh` to identify network adapters. While common types like Ethernet and Wi-Fi are generally supported, detection of all adapter types (e.g., virtual, VPN adapters) may not be exhaustive. Ensure your specific adapter is recognized by the application before applying configurations.
- **Nearby Network Scanning**: Uses `netsh wlan show networks` to list SSID, auth type, and signal strength.
- **Wi-Fi Management**: Supports multiple profiles per configuration.
- **HTTPS Support**: Attempts HTTPS first, supports custom ports.
- **Cookie Support**: Stored per router IP; auto-fill may need customization.
- **Redirect Handling**: Monitors `.com`, `.net`, `.lan`, `.io`; refresh interval configurable (default: 5s).
- **Security**: Wi-Fi passwords stored in plain text; consider `keyring`
