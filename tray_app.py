import pystray
from PIL import Image
import sys
from PyQt6.QtWidgets import QApplication, QMessageBox # Added QMessageBox
from PyQt6.QtCore import QObject, pyqtSignal
import threading
from functools import partial
from datetime import datetime
from db_manager import DBManager
from network_manager import (
    apply_network_config,
    list_adapters,
    get_current_adapter_config,
    set_adapter_to_dhcp,
    apply_wifi_profile,
    has_wifi_support,
    is_wifi_adapter,
    get_available_networks,
    get_wifi_profiles as get_wifi_profiles,
    get_wifi_password as get_wifi_password
)
from router_browser import open_router_page
from settings_gui import SettingsGUI

ICON_PATH = "network.ico"


class TrayApp(QObject):
    """System tray application for network configuration."""

    show_settings_signal = pyqtSignal()
    prepare_settings_for_save_current_signal = pyqtSignal(str)
    request_tray_menu_refresh_signal = pyqtSignal()
    open_router_signal = pyqtSignal(str, str, str, int, str)

    def __init__(self):
        super().__init__()
        self.db = DBManager()
        self.icon = None
        self.settings_window = None
        self.router_windows = []
        self.wifi_supported = has_wifi_support()
        self.show_settings_signal.connect(self._slot_run_settings_gui)
        self.prepare_settings_for_save_current_signal.connect(
            self._slot_prepare_settings_for_save_current
        )
        self.request_tray_menu_refresh_signal.connect(self.update_tray_menu)
        self.open_router_signal.connect(self._slot_open_router_page)

    def _internal_save_current_settings_handler(self, adapter_name, icon, item):
        """Handler for saving current settings menu item."""
        self._request_save_current_settings(adapter_name)

    def get_pystray_menu(self):
        """Update the tray menu with current configurations and adapter statuses."""
        menu_items = []

        # 1. Determine Active Configurations and DHCP Status
        adapter_statuses = {}
        saved_configs_all = self.db.load_configs() # Assuming this doesn't fail critically or returns empty on error

        active_adapters, list_err = list_adapters()
        if list_err:
            if self.icon:
                self.icon.notify(list_err, "Adapter Listing Error")
            # Add an error item to the menu if adapter listing fails
            menu_items.append(pystray.MenuItem(f"Error listing adapters: {list_err}", None, enabled=False))

        if active_adapters: # Proceed only if adapters were listed
            for adapter_name in active_adapters:
                live_config, get_err = get_current_adapter_config(adapter_name)
                if get_err and not live_config: # Error and no config data
                    adapter_statuses[adapter_name] = f"Error: {get_err}"
                    if self.icon: # Notify user about specific adapter error
                         self.icon.notify(get_err, f"Config Error ({adapter_name})")
                elif live_config:
                    if live_config.get('dhcp_enabled'):
                        adapter_statuses[adapter_name] = "DHCP"
                    else:
                        status_found = False
                        for profile_name, saved_profile_data in saved_configs_all.get("networks", {}).items():
                            if (saved_profile_data.get('adapter_name') == adapter_name and
                                saved_profile_data.get('ip_address') == live_config.get('ip_address') and
                                saved_profile_data.get('subnet_mask') == live_config.get('subnet_mask') and
                                saved_profile_data.get('gateway') == live_config.get('gateway')):
                                adapter_statuses[adapter_name] = f"Static: {profile_name}"
                                status_found = True
                                break
                        if not status_found:
                            adapter_statuses[adapter_name] = "Static: (Custom/Unsaved)"
                else: # No error message but also no live_config (should ideally not happen)
                    adapter_statuses[adapter_name] = "Status Unknown"

        # 2. Indicate Active Profile in Main Menu
        for name, profile_data in saved_configs_all.get("networks", {}).items():
            is_active = any(status == f"Static: {name}" for status in adapter_statuses.values())
            display_name = f"✔ {name}" if is_active else name
            menu_items.append(pystray.MenuItem(display_name, partial(self._internal_apply_config_handler, name)))

        # --- Wi-Fi Section (unchanged from previous logic regarding active status) ---
        if self.wifi_supported:
            wifi_profiles_data, wifi_profiles_msg = self.db.get_wifi_profiles()
            if wifi_profiles_msg and self.icon:
                self.icon.notify(wifi_profiles_msg, "Wi-Fi Profile Loading Error")

            if wifi_profiles_data:
                wifi_menu_items = []
                for profile in wifi_profiles_data:
                    config_name, ssid, password, auth_type = profile
                    wifi_menu_items.append(
                        pystray.MenuItem(
                            f"{config_name}: {ssid} ({auth_type})",
                            partial(
                                self._internal_apply_wifi_handler,
                                config_name,
                                ssid,
                                password,
                                auth_type,
                            ),
                        )
                    )
                if wifi_menu_items:
                    menu_items.append(pystray.Menu.SEPARATOR)
                    menu_items.append(
                        pystray.MenuItem("Wi-Fi Profiles", pystray.Menu(*wifi_menu_items))
                    )

            networks_data, networks_msg = get_available_networks()
            if networks_msg and self.icon:
                self.icon.notify(networks_msg, "Nearby Wi-Fi Scan Error")

            if networks_data:
                nearby_menu_items = []
                for ssid, auth_type, signal in networks_data:
                    nearby_menu_items.append(
                        pystray.MenuItem(
                            f"{ssid} ({auth_type}, {signal})",
                            partial(self._internal_connect_nearby_network, ssid, auth_type),
                        )
                    )
                if nearby_menu_items:
                    menu_items.append(
                        pystray.MenuItem("Nearby Networks", pystray.Menu(*nearby_menu_items)))

        # --- Adapter Actions Section ---
        adapter_actions_menu_items = []
        if active_adapters: # Only add this section if adapters were successfully listed
            for adapter in active_adapters:
                current_adapter_submenu_items = []

                # 3. Indicate Adapter Status in "Adapter Actions" Submenu
                status_str = adapter_statuses.get(adapter, "Status Unknown")
                current_adapter_submenu_items.append(pystray.MenuItem(f"Current: {status_str}", None, enabled=False))
                current_adapter_submenu_items.append(pystray.Menu.SEPARATOR)

                action_set_dhcp = partial(self._internal_dhcp, adapter)
                action_save_current = partial(self._internal_save_current_settings_handler, adapter)
                current_adapter_submenu_items.extend([
                    pystray.MenuItem(f"Set '{adapter}' to DHCP", action_set_dhcp),
                    pystray.MenuItem(
                        f"Save Current Settings for '{adapter}'", action_save_current
                    ),
                ])

                # Logic for "Open Router" based on active config for *this* adapter
                # This part needs to use the specific status determined for *this* adapter
                if status_str.startswith("Static: "):
                    active_profile_name_for_adapter = status_str.replace("Static: ", "")
                    if active_profile_name_for_adapter != "(Custom/Unsaved)":
                        active_profile_details = saved_configs_all.get("networks", {}).get(active_profile_name_for_adapter)
                        if active_profile_details and active_profile_details.get("router_ip"):
                            action_open_router = partial(
                                self._internal_open_router_handler,
                                active_profile_details.get("router_ip", ""),
                                active_profile_details.get("gateway", ""), # Gateway from saved profile
                                active_profile_details.get("router_port", ""),
                                active_profile_details.get("router_refresh_interval", 5),
                                active_profile_details.get("router_protocol", "http"),
                            )
                            current_adapter_submenu_items.insert(2, pystray.Menu.SEPARATOR) # Insert before DHCP/Save
                            current_adapter_submenu_items.insert(
                                2, # Insert before DHCP/Save
                                pystray.MenuItem(
                                    f"Open Router ({active_profile_name_for_adapter})",
                                    action_open_router,
                                ),
                            )

                adapter_submenu = pystray.Menu(*current_adapter_submenu_items)
                adapter_actions_menu_items.append(
                    pystray.MenuItem(adapter, adapter_submenu)
                )

        if adapter_actions_menu_items: # If there are any adapter-specific actions
            menu_items.append(pystray.Menu.SEPARATOR)
            menu_items.append(
                pystray.MenuItem(
                    "Adapter Actions", pystray.Menu(*adapter_actions_menu_items)
                )
            )

        menu_items.append(pystray.Menu.SEPARATOR)
        menu_items.append(pystray.MenuItem("Settings", self._request_open_settings))
        menu_items.append(pystray.MenuItem("Exit", self._request_exit_app))
        return pystray.Menu(*menu_items)

    def start_pystray_in_thread(self):
        """Creates and runs the system tray icon in a separate thread."""
        try:
            image = Image.open(ICON_PATH)
        except FileNotFoundError:
            image = Image.new("RGB", (64, 64), color="blue")
        menu = self.get_pystray_menu()
        self.icon = pystray.Icon(
            "Network Switcher", image, "Network Switcher", menu=menu
        )
        self.icon.run()

    def _request_open_settings(self, icon=None, item=None):
        self.show_settings_signal.emit()

    def _request_apply_config(self, config_name):
        thread = threading.Thread(
            target=self._internal_apply_config_task,
            args=(config_name,),
            daemon=True,
        )
        thread.start()

    def _request_set_adapter_to_dhcp(self, adapter_name):
        thread = threading.Thread(
            target=self._execute_set_dhcp_task,
            args=(adapter_name,),
            daemon=True,
        )
        thread.start()

    def _request_save_current_settings(self, adapter_name):
        self.prepare_settings_for_save_current_signal.emit(adapter_name)

    def _request_exit_app(self, icon=None, item=None):
        if self.icon:
            self.icon.stop()
        app_instance = QApplication.instance()
        if app_instance:
            app_instance.quit()

    def _internal_apply_config_handler(self, config_name, icon, item):
        self._request_apply_config(config_name)

    def _internal_open_router_handler(
        self, router_ip, gateway_ip, router_port, refresh_interval, protocol, icon, item
    ):
        self.open_router_signal.emit(
            router_ip, gateway_ip, router_port, refresh_interval, protocol
        )

    def _internal_dhcp(self, adapter_name, icon, item):
        self._request_set_adapter_to_dhcp(adapter_name)

    def _internal_apply_wifi_handler(
        self, config_name, ssid, password, auth_type, icon, item
    ):
        thread = threading.Thread(
            target=self._execute_wifi_task,
            args=(config_name, ssid, password, auth_type),
            daemon=True,
        )
        thread.start()

    def _internal_connect_nearby_network(self, network_ssid, auth_type, icon, item):
        """Open settings GUI to input password for a nearby network."""
        self.show_settings_signal.emit()
        QApplication.processEvents()
        if self.settings_window and self.settings_window.isVisible():
            self.settings_window.wifi_ssid.setText(network_ssid)
            self.settings_window.auth_type_combo.setCurrentText(auth_type)
            self.settings_window.wifi_password.setFocus()
            QMessageBox.information(self.settings_window, "Nearby Network Selected",
                                    f"'{network_ssid}' selected. Please enter password if required and click 'Apply Selected/Entered Wi-Fi'.")
        elif self.icon:
            self.icon.notify("Settings window not available for nearby network connection.", "Error")


    def _internal_apply_config_task(self, config_name):
        configs = self.db.load_configs()
        network_configs = configs.get("networks", {})

        if config_name not in network_configs:
            if self.icon:
                self.icon.notify(
                    f"Configuration '{config_name}' not found.", "Error", "Network Switcher"
                )
            return

        config_to_apply = network_configs[config_name]
        success, message = apply_network_config(config_to_apply["adapter_name"], config_to_apply)

        title = "Success" if success else "Error"
        full_title = f"Network Switcher - {title}"

        if self.icon:
            self.icon.notify(message, full_title)

        if success:
            if config_to_apply.get("open_router"):
                self.open_router_signal.emit(
                    config_to_apply.get("router_ip", ""),
                    config_to_apply.get("gateway", ""),
                    config_to_apply.get("router_port", ""),
                    config_to_apply.get("router_refresh_interval", 5),
                    config_to_apply.get("router_protocol", "http"),
                )
            self.request_tray_menu_refresh_signal.emit()


    def _execute_set_dhcp_task(self, adapter_name):
        success, message = set_adapter_to_dhcp(adapter_name)
        title = "Success" if success else "Error"
        full_title = f"Network Switcher - {title}"

        if self.icon:
            self.icon.notify(message, full_title)

        if success:
            self.request_tray_menu_refresh_signal.emit()


    def _execute_wifi_task(self, config_name, ssid, password, auth_type):
        all_system_adapters, list_err = list_adapters()
        if list_err: # Handle error from list_adapters
            if self.icon:
                self.icon.notify(f"Wi-Fi apply error: Could not list adapters. {list_err}", "Network Switcher - Wi-Fi Error")
            return

        wifi_adapters_present = [name for name in all_system_adapters if is_wifi_adapter(name)]

        if not wifi_adapters_present:
            if self.icon:
                self.icon.notify("No Wi-Fi adapter found on the system to apply the profile.", "Network Switcher - Wi-Fi Error")
            return

        adapter_to_use_for_wifi = wifi_adapters_present[0]

        success, message = apply_wifi_profile(ssid, password, adapter_to_use_for_wifi, auth_type)
        title = "Success" if success else "Error"
        full_title = f"Network Switcher - {title}"

        if self.icon:
            self.icon.notify(message, full_title)

        if success:
            self.request_tray_menu_refresh_signal.emit()


    def _slot_run_settings_gui(self):
        if not self.settings_window or not self.settings_window.isVisible():
            self.settings_window = SettingsGUI(self)
            self.settings_window.show()
        else:
            self.settings_window.activateWindow()
            self.settings_window.showNormal()


    def _slot_prepare_settings_for_save_current(self, adapter_name):
        current_config_data, msg = get_current_adapter_config(adapter_name)

        if not current_config_data:
            error_details = msg if msg else "No details provided."
            if self.icon:
                self.icon.notify(f"Could not retrieve current settings for {adapter_name}: {error_details}", "Error")
            return

        if not self.settings_window or not self.settings_window.isVisible():
            self.settings_window = SettingsGUI(self)
            self.settings_window.show()
        else:
            self.settings_window.activateWindow()
            self.settings_window.showNormal()

        current_ip = current_config_data.get('ip_address')
        current_ip_str = current_ip if current_ip else "NoIP"

        suggested_name = (
            f"{adapter_name} - {current_ip_str} - {datetime.now().strftime('%Y%m%d-%H%M%S')}"
        )

        QApplication.processEvents()
        self.settings_window.populate_for_new_save(current_config_data, suggested_name)

    def _slot_open_router_page(
        self, router_ip, gateway_ip, router_port, refresh_interval, protocol
    ):
        browser = open_router_page(
            router_ip, gateway_ip, router_port, refresh_interval, protocol
        )
        if browser:
            self.router_windows.append(browser)
            self.router_windows = [w for w in self.router_windows if w.isVisible()]

    def update_tray_menu(self):
        if self.icon:
            self.icon.menu = self.get_pystray_menu()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    tray_controller = TrayApp()
    pystray_thread = threading.Thread(
        target=tray_controller.start_pystray_in_thread,
        daemon=True,
    )
    pystray_thread.start()
    sys.exit(app.exec())
