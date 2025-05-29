import pystray
from PIL import Image
import sys
from PyQt6.QtWidgets import QApplication
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
    is_wifi_adapter, # Import is_wifi_adapter
    get_available_networks,
)
from router_browser import open_router_page
from settings_gui import SettingsGUI

ICON_PATH = "network.ico"


class TrayApp(QObject):
    """System tray application for network configuration."""

    show_settings_signal = pyqtSignal()
    prepare_settings_for_save_current_signal = pyqtSignal(str)
    request_tray_menu_refresh_signal = pyqtSignal()
    open_router_signal = pyqtSignal(str, str, str, int, str) # Added protocol

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
        """Update the tray menu with current configurations."""
        configs = self.db.load_configs()
        menu_items = [
            pystray.MenuItem(name, partial(self._internal_apply_config_handler, name))
            for name in configs["networks"]
        ]

        # Wi-Fi profiles (conditional)
        if self.wifi_supported:
            wifi_profiles = self.db.get_wifi_profiles()
            if wifi_profiles:
                wifi_menu_items = []
                for profile in wifi_profiles:
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
                menu_items.append(pystray.Menu.SEPARATOR)
                menu_items.append(
                    pystray.MenuItem("Wi-Fi Profiles", pystray.Menu(*wifi_menu_items))
                )

            # Nearby networks
            networks = get_available_networks()
            if networks:
                nearby_menu_items = []
                for ssid, auth_type, signal in networks:
                    nearby_menu_items.append(
                        pystray.MenuItem(
                            f"{ssid} ({auth_type}, {signal})",
                            partial(self._internal_connect_nearby_network, ssid, auth_type),
                        )
                    )
                menu_items.append(
                    pystray.MenuItem("Nearby Networks", pystray.Menu(*nearby_menu_items)))

        # Adapter-specific actions
        adapter_menu = []
        active_adapters = list_adapters()
        for adapter in active_adapters:
            action_set_dhcp = partial(self._internal_dhcp, adapter)
            action_save_current = partial(self._internal_save_current_settings_handler, adapter)
            current_adapter_menu_items = [
                pystray.MenuItem(f"Set '{adapter}' to DHCP", action_set_dhcp),
                pystray.MenuItem(
                    f"Save Current Settings for '{adapter}'", action_save_current
                ),
            ]
            current_adapter_settings = get_current_adapter_config(adapter)
            saved_configs = self.db.load_configs().get("networks", {})
            for config_name, config in saved_configs.items():
                if (
                    config.get("adapter_name") == adapter
                    and config.get("ip_address") == current_adapter_settings.get("ip_address")
                    and config.get("gateway") == current_adapter_settings.get("gateway")
                    and config.get("router_ip")
                ):
                    action_open_router = partial(
                        self._internal_open_router_handler,
                        config.get("router_ip", ""),
                        config.get("gateway", ""),
                        config.get("router_port", ""),
                        config.get("router_refresh_interval", 5),
                        config.get("router_protocol", "http"),
                    )
                    current_adapter_menu_items.insert(0, pystray.Menu.SEPARATOR)
                    current_adapter_menu_items.insert(
                        0,
                        pystray.MenuItem(
                            f"Open Router (Active: {config_name})",
                            action_open_router,
                        ),
                    )
                    break
            adapter_submenu = pystray.Menu(*current_adapter_menu_items)
            adapter_menu.append(
                pystray.MenuItem(adapter, adapter_submenu)
            )

        if adapter_menu:
            menu_items.append(pystray.Menu.SEPARATOR)
            menu_items.append(
                pystray.MenuItem(
                    "Adapter Actions", pystray.Menu(*adapter_menu)
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
        QApplication.instance().quit()

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
        # Removed: self._request_save_current_settings(adapter_name)
        # Setting to DHCP is a distinct action from saving settings.

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
        if self.settings_window:
            self.settings_window.wifi_ssid.setText(network_ssid)
            self.settings_window.auth_type_combo.setCurrentText(auth_type)
            # The rest of the logic for connecting will be handled by the SettingsGUI
            # after the user inputs a password (if required) and clicks an apply button there.

    def _internal_apply_config_task(self, config_name):
        configs = self.db.load_configs()
        if not configs or not configs.get("networks") or config_name not in configs.get("networks"):
            if self.icon:
                self.icon.notify(
                    f"Configuration '{config_name}' not found.", "Error", "Network Switcher"
                )
            return
        config = configs["networks"][config_name] # Corrected access
        success = apply_network_config(config["adapter_name"], config)
        if success:
            if self.icon:
                self.icon.notify(
                    f"Applied configuration: {config_name}", "Network Switcher", "Success"
                )
            if config.get("open_router"):
                self.open_router_signal.emit(
                    config.get("router_ip", ""),
                    config.get("gateway", ""),
                    config.get("router_port", ""),
                    config.get("router_refresh_interval", 5), # Corrected refresh interval
                    config.get("router_protocol", "http"),
                )
            if self.wifi_supported:
                # Check for associated Wi-Fi profiles for this specific network config
                # This part might need more specific logic if a config can have multiple Wi-Fi profiles
                # For now, assuming we might apply the first one if present.
                # Or, this Wi-Fi application logic might be better handled if explicitly tied.
                # For simplicity, if a static config is applied, and it has an associated Wi-Fi profile,
                # it might be desirable to also attempt to connect to that Wi-Fi.
                # This depends on the intended application flow.
                # Example:
                # wifi_profiles_for_config = self.db.get_wifi_profiles(config_name=config_name)
                # if wifi_profiles_for_config:
                #     # Assuming you want to apply the first associated Wi-Fi profile
                #     profile_data = wifi_profiles_for_config[0] # ssid, password, auth_type
                #     apply_wifi_profile(
                #         profile_data[0], # ssid
                #         profile_data[1], # password
                #         config["adapter_name"],
                #         profile_data[2]  # auth_type
                #     )
                pass # Re-evaluate Wi-Fi application logic here if needed for static configs
            self.request_tray_menu_refresh_signal.emit()
        else:
            if self.icon:
                self.icon.notify(
                    f"Failed to apply configuration: {config_name}", "Error", "Network Switcher"
                )

    def _execute_set_dhcp_task(self, adapter_name):
        success = set_adapter_to_dhcp(adapter_name)
        if success:
            if self.icon:
                self.icon.notify(
                    f"Adapter '{adapter_name}' set to DHCP.", "Network Switcher", "Success"
                )
            self.request_tray_menu_refresh_signal.emit()
        else:
            if self.icon:
                self.icon.notify(
                    f"Failed to set '{adapter_name}' to DHCP.", "Network Switcher", "Error"
                )

    def _execute_wifi_task(self, config_name, ssid, password, auth_type):
        # For applying a Wi-Fi profile, we should use an actual Wi-Fi adapter.
        # The config_name here is the one associated with the Wi-Fi profile,
        # not necessarily indicative of the adapter to use for Wi-Fi.
        all_system_adapters = list_adapters()
        wifi_adapters_present = [name for name in all_system_adapters if is_wifi_adapter(name)]

        if not wifi_adapters_present:
            if self.icon:
                self.icon.notify("No Wi-Fi adapter found on the system to apply the profile.", "Network Switcher Error", "Error")
            return

        adapter_to_use_for_wifi = wifi_adapters_present[0] # Use the first available Wi-Fi adapter

        if apply_wifi_profile(ssid, password, adapter_to_use_for_wifi, auth_type):
            if self.icon:
                self.icon.notify(
                    f"Connected to Wi-Fi '{ssid}'.", "Network Switcher", "Success"
                )
        else:
            if self.icon:
                self.icon.notify(
                    f"Failed to connect to Wi-Fi '{ssid}'.", "Network Switcher", "Error")

    def _slot_run_settings_gui(self):
        if not self.settings_window or not self.settings_window.isVisible():
            self.settings_window = SettingsGUI(self)
            self.settings_window.show()
        else:
            self.settings_window.activateWindow()
            self.settings_window.show()

    def _slot_prepare_settings_for_save_current(self, adapter_name):
        current_config_data = get_current_adapter_config(adapter_name)
        if not current_config_data:
            if self.icon:
                self.icon.notify(
                    f"Could not retrieve current settings for {adapter_name}.", "Error")
            return
        if not self.settings_window or not self.settings_window.isVisible():
            self.settings_window = SettingsGUI(self)
            self.settings_window.show()
        else:
            self.settings_window.activateWindow()
        suggested_name = (
            f"{adapter_name}--current--{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        )
        self.settings_window.populate_for_new_save(current_config_data, suggested_name)

    def _slot_open_router_page(
        self, router_ip, gateway_ip, router_port, refresh_interval, protocol
    ):
        browser = open_router_page(
            router_ip, gateway_ip, router_port, refresh_interval, protocol
        )
        if browser:
            self.router_windows.append(browser)
            self.router_windows = [w for w in self.router_windows if w.isVisible()] # Corrected variable name and method

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
