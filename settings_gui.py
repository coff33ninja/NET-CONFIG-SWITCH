import sys
from PyQt6.QtWidgets import (
    QMainWindow, QVBoxLayout, QWidget, QLineEdit, QComboBox, QPushButton,
    QCheckBox, QLabel, QMessageBox, QDialog, QTableWidget, QTableWidgetItem,
    QDialogButtonBox, QHBoxLayout, QInputDialog
)
from network_manager import (list_adapters, validate_ip, get_wifi_profiles, get_wifi_password,
                             has_wifi_support, get_available_networks, apply_wifi_profile, is_wifi_adapter)
from db_manager import DBManager

class SettingsGUI(QMainWindow):
    """GUI for managing network configurations using PyQt6."""
    def __init__(self, main_app_controller):
        super().__init__()
        self.main_app_controller = main_app_controller
        self.db = DBManager()
        self.wifi_supported = has_wifi_support()
        self.wifi_section_widgets = []
        self.setWindowTitle("Network Configuration Settings")
        self.setGeometry(100, 100, 400, 600 if not self.wifi_supported else 900)
        self.init_ui()

    def init_ui(self):
        """Set up the GUI."""
        layout = QVBoxLayout()
        container = QWidget()
        container.setLayout(layout)

        # Adapter selection
        layout.addWidget(QLabel("Network Adapter:"))
        self.adapter_combo = QComboBox()
        adapter_names = list_adapters()
        if adapter_names:
            self.adapter_combo.addItems(adapter_names)
            self.adapter_combo.currentTextChanged.connect(self.update_wifi_controls_state)
        else:
            self.adapter_combo.addItem("No adapters found")
            self.adapter_combo.setEnabled(False)
        layout.addWidget(self.adapter_combo)

        # Configuration name
        layout.addWidget(QLabel("Configuration Name:"))
        self.config_name = QLineEdit()
        layout.addWidget(self.config_name)

        # IP address
        layout.addWidget(QLabel("IP Address:"))
        self.ip_address = QLineEdit()
        layout.addWidget(self.ip_address)

        # Subnet mask
        layout.addWidget(QLabel("Subnet Mask:"))
        self.subnet_mask = QLineEdit()
        layout.addWidget(self.subnet_mask)

        # Default gateway
        layout.addWidget(QLabel("Default Gateway:"))
        self.gateway = QLineEdit()
        layout.addWidget(self.gateway)

        # Primary DNS
        layout.addWidget(QLabel("Primary DNS:"))
        self.dns_primary = QLineEdit()
        layout.addWidget(self.dns_primary)

        # Secondary DNS
        layout.addWidget(QLabel("Secondary DNS (optional):"))
        self.dns_secondary = QLineEdit()
        layout.addWidget(self.dns_secondary)

        # Router IP
        layout.addWidget(QLabel("Router Login IP (optional):"))
        self.router_ip = QLineEdit()
        layout.addWidget(self.router_ip)

        # Router Port
        layout.addWidget(QLabel("Router Login Port (optional):"))
        self.router_port = QLineEdit()
        self.router_port.setPlaceholderText("e.g., 8080")
        layout.addWidget(self.router_port)

        # Router Protocol
        layout.addWidget(QLabel("Router Protocol:"))
        self.router_protocol_combo = QComboBox()
        self.router_protocol_combo.addItems(["http", "https"])
        layout.addWidget(self.router_protocol_combo)

        # Open router checkbox
        self.open_router = QCheckBox("Open router login page on apply")
        layout.addWidget(self.open_router)

        # Wi-Fi section (conditional)
        if self.wifi_supported:
            self.add_wifi_section(layout)
            # Initial call to set the correct state of Wi-Fi controls
            self.update_wifi_controls_state()

        # Buttons
        save_button = QPushButton("Save Configuration")
        save_button.clicked.connect(self.save_config)
        layout.addWidget(save_button)

        delete_button = QPushButton("Delete Configuration")
        delete_button.clicked.connect(self.delete_config)
        layout.addWidget(delete_button)

        view_button = QPushButton("View Configurations")
        view_button.clicked.connect(self.view_configs)
        layout.addWidget(view_button)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button)

        # Config selection for editing
        layout.addWidget(QLabel("Select Config to Edit:"))
        self.config_select = QComboBox()
        self.config_select.currentTextChanged.connect(self.load_config_to_fields)
        layout.addWidget(self.config_select)

        self.update_config_list()
        self.setCentralWidget(container)

    def add_wifi_section(self, layout):
        """Add Wi-Fi section to the GUI."""
        wifi_label = QLabel("Wi-Fi Profiles:")
        layout.addWidget(wifi_label)
        self.wifi_section_widgets.append(wifi_label)

        wifi_layout = QHBoxLayout()
        self.wifi_profile_combo = QComboBox()
        self.wifi_profile_combo.addItem("None")
        self.update_wifi_profile_list()
        wifi_layout.addWidget(self.wifi_profile_combo)
        import_wifi_btn = QPushButton("Import System Wi-Fi")
        import_wifi_btn.clicked.connect(self.import_system_wifi)
        wifi_layout.addWidget(import_wifi_btn)
        layout.addLayout(wifi_layout)
        self.wifi_section_widgets.append(self.wifi_profile_combo)
        self.wifi_section_widgets.append(import_wifi_btn)

        # Nearby networks
        nearby_layout = QHBoxLayout()
        self.nearby_networks_combo = QComboBox()
        self.nearby_networks_combo.addItem("None")
        nearby_layout.addWidget(self.nearby_networks_combo)
        scan_btn = QPushButton("Scan Nearby Networks")
        scan_btn.clicked.connect(self.scan_nearby_networks)
        nearby_layout.addWidget(scan_btn)
        layout.addLayout(nearby_layout)
        self.wifi_section_widgets.extend([self.nearby_networks_combo, scan_btn])

        ssid_label = QLabel("Wi-Fi SSID:")
        layout.addWidget(ssid_label)
        self.wifi_ssid = QLineEdit()
        layout.addWidget(self.wifi_ssid)
        self.wifi_section_widgets.extend([ssid_label, self.wifi_ssid])

        pwd_label = QLabel("Wi-Fi Password:")
        layout.addWidget(pwd_label)
        self.wifi_password = QLineEdit()
        self.wifi_password.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.wifi_password)
        self.wifi_section_widgets.extend([pwd_label, self.wifi_password])

        auth_label = QLabel("Authentication Type:")
        layout.addWidget(auth_label)
        self.auth_type_combo = QComboBox()
        self.auth_type_combo.addItems(["open", "WEP", "WPAPSK", "WPA2PSK", "WPA3SAE"])
        self.auth_type_combo.setCurrentText("WPA2PSK")
        layout.addWidget(self.auth_type_combo)
        self.wifi_section_widgets.extend([auth_label, self.auth_type_combo])

        wifi_btn_layout = QHBoxLayout()
        save_wifi_btn = QPushButton("Save Wi-Fi Profile")
        save_wifi_btn.clicked.connect(self.save_wifi)
        wifi_btn_layout.addWidget(save_wifi_btn)
        delete_wifi_btn = QPushButton("Delete Wi-Fi Profile")
        delete_wifi_btn.clicked.connect(self.delete_wifi)
        wifi_btn_layout.addWidget(delete_wifi_btn)
        self.apply_wifi_btn = QPushButton("Apply Wi-Fi Profile") # Store as instance variable
        self.apply_wifi_btn.clicked.connect(self.apply_wifi)
        wifi_btn_layout.addWidget(self.apply_wifi_btn)
        layout.addLayout(wifi_btn_layout)
        self.wifi_section_widgets.extend([save_wifi_btn, delete_wifi_btn, self.apply_wifi_btn])

    def scan_nearby_networks(self):
        """Scan for nearby Wi-Fi networks and populate dropdown."""
        networks = get_available_networks()
        self.nearby_networks_combo.clear()
        self.nearby_networks_combo.addItem("None")
        for ssid, auth_type, signal in networks:
            self.nearby_networks_combo.addItem(f"{ssid} ({auth_type}, {signal})")
        if not networks:
            QMessageBox.information(self, "Info", "No nearby Wi-Fi networks found.")

    def update_wifi_profile_list(self):
        """Update Wi-Fi profile dropdown."""
        if not self.wifi_supported:
            return
        self.wifi_profile_combo.clear()
        self.wifi_profile_combo.addItem("None")
        profiles = self.db.get_wifi_profiles()
        for profile in profiles:
            config_name, ssid, _, auth_type = profile
            self.wifi_profile_combo.addItem(f"{config_name}: {ssid} ({auth_type})")

    def import_system_wifi(self):
        """Import Wi-Fi profiles from the system."""
        profiles = get_wifi_profiles()
        if not profiles:
            QMessageBox.information(self, "Info", "No Wi-Fi profiles found on the system.")
            return
        profile_items = [f"{ssid} ({auth_type})" for ssid, auth_type in profiles]
        selected_item, ok = QInputDialog.getItem(
            self, "Select Wi-Fi Profile", "Choose a Wi-Fi profile:", profile_items, 0, False
        )
        if ok and selected_item:
            ssid = selected_item.split(" (")[0]
            auth_type = selected_item.split("(")[1].rstrip(")")
            password = get_wifi_password(ssid)
            if password:
                self.wifi_ssid.setText(ssid)
                self.wifi_password.setText(password)
                self.auth_type_combo.setCurrentText(auth_type)
            else:
                QMessageBox.warning(self, "Warning", f"Could not retrieve password for {ssid}.")
                self.wifi_ssid.setText(ssid)
                self.wifi_password.clear()
                self.auth_type_combo.setCurrentText(auth_type)

    def save_wifi(self):
        """Save Wi-Fi profile to database."""
        config_name = self.config_name.text()
        ssid = self.wifi_ssid.text()
        password = self.wifi_password.text()
        auth_type = self.auth_type_combo.currentText()

        # Check if a nearby network is selected
        selected_network = self.nearby_networks_combo.currentText()
        if selected_network != "None":
            selected_ssid = selected_network.split(" (")[0]
            selected_auth = selected_network.split("(")[1].split(",")[0]
            self.wifi_ssid.setText(selected_ssid)
            self.auth_type_combo.setCurrentText(selected_auth)
            ssid = selected_ssid
            auth_type = selected_auth

        if not config_name:
            QMessageBox.critical(self, "Error", "Configuration name is required.")
            return
        if not ssid or (auth_type != "open" and not password):
            QMessageBox.critical(self, "Error", "Wi-Fi SSID and password (if not open) are required.")
            return
        self.db.save_wifi_profile(config_name, ssid, password, auth_type)
        self.update_wifi_profile_list()
        self.main_app_controller.update_tray_menu()
        QMessageBox.information(self, "Success", f"Wi-Fi profile for '{ssid}' saved.")

    def delete_wifi(self):
        """Delete selected Wi-Fi profile."""
        selected = self.wifi_profile_combo.currentText()
        if selected == "None":
            QMessageBox.critical(self, "Error", "Select a Wi-Fi profile to delete.")
            return
        config_name, ssid = selected.split(": ", 1)[0], selected.split(": ", 1)[1].split(" (")[0]
        self.db.delete_wifi_profile(config_name, ssid)
        self.update_wifi_profile_list()
        self.main_app_controller.update_tray_menu()
        QMessageBox.information(self, "Success", f"Wi-Fi profile '{ssid}' deleted.")

    def apply_wifi(self):
        """Apply selected Wi-Fi profile or nearby network."""
        selected = self.wifi_profile_combo.currentText()
        selected_network = self.nearby_networks_combo.currentText()

        if selected_network != "None":
            ssid = selected_network.split(" (")[0]
            auth_type = selected_network.split("(")[1].split(",")[0]
            password = self.wifi_password.text()
            adapter_name = self.adapter_combo.currentText()
            if auth_type != "open" and not password:
                QMessageBox.critical(self, "Error", "Password is required for this network.")
                return
            if apply_wifi_profile(ssid, password, adapter_name, auth_type):
                QMessageBox.information(self, "Success", f"Connected to Wi-Fi '{ssid}'.")
            else:
                QMessageBox.critical(self, "Error", f"Failed to connect to Wi-Fi '{ssid}'.")
            return

        if selected == "None":
            QMessageBox.critical(self, "Error", "Select a Wi-Fi profile to apply.")
            return
        config_name, rest = selected.split(": ", 1)
        ssid, auth_type = rest.split(" (")[0], rest.split("(")[1].rstrip(")")
        profiles = self.db.get_wifi_profiles(config_name)
        for profile in profiles:
            if profile[1] == ssid and profile[3] == auth_type:
                password = profile[2]
                adapter_name = self.adapter_combo.currentText()
                if apply_wifi_profile(ssid, password, adapter_name, auth_type):
                    QMessageBox.information(self, "Success", f"Connected to Wi-Fi '{ssid}'.")
                else:
                    QMessageBox.critical(self, "Error", f"Failed to connect to Wi-Fi '{ssid}'.")
                return
        QMessageBox.critical(self, "Error", "Wi-Fi profile not found.")

    def view_configs(self):
        """Display all configurations."""
        configs = self.db.load_configs()
        if not configs or not configs["networks"]:
            QMessageBox.information(self, "Info", "No configurations available.")
            return
        dialog = ViewConfigsDialog(configs, self)
        dialog.exec()

    def update_adapters(self):
        """Update adapter dropdown."""
        adapters = list_adapters()
        self.adapter_combo.clear()
        self.adapter_combo.addItems(adapters)
        if adapters:
            self.adapter_combo.setCurrentIndex(0)

    def update_config_list(self):
        """Update config dropdown."""
        configs = self.db.load_configs()
        self.config_select.clear()
        self.config_select.addItems(list(configs["networks"].keys()))

    def load_config_to_fields(self, config_name):
        """Load selected config into fields."""
        if not config_name:
            return
        configs = self.db.load_configs()
        if config_name in configs["networks"]:
            config = configs["networks"][config_name]
            self.config_name.setText(config_name)
            self.ip_address.setText(config["ip_address"])
            self.subnet_mask.setText(config["subnet_mask"])
            self.gateway.setText(config["gateway"])
            self.dns_primary.setText(config["dns_primary"])
            self.dns_secondary.setText(config["dns_secondary"])
            self.router_ip.setText(config["router_ip"] or "")
            self.router_port.setText(config["router_port"] or "")
            self.router_protocol_combo.setCurrentText(config.get("router_protocol", "http"))
            self.adapter_combo.setCurrentText(config["adapter_name"])
            self.open_router.setChecked(config["open_router"])
            if self.wifi_supported:
                self.wifi_ssid.clear()
                self.wifi_password.clear()
                self.auth_type_combo.setCurrentText("WPA2PSK")

    def save_config(self):
        """Save configuration to database."""
        config_name = self.config_name.text()
        if not config_name:
            QMessageBox.critical(self, "Error", "Configuration name is required.")
            return

        required_static_fields = {
            "IP Address": self.ip_address.text(),
            "Subnet Mask": self.subnet_mask.text(),
            "Gateway": self.gateway.text(),
            "Primary DNS": self.dns_primary.text(),
        }

        for name, value in required_static_fields.items():
            if not value:
                QMessageBox.critical(self, "Error", f"{name} is required for a static configuration.")
                return
            if not validate_ip(value):
                QMessageBox.critical(self, "Error", f"Invalid {name}: {value}")
                return

        if self.dns_secondary.text() and not validate_ip(self.dns_secondary.text()):
            QMessageBox.critical(self, "Error", f"Invalid Secondary DNS: {self.dns_secondary.text()}")
            return
        if self.router_ip.text() and not validate_ip(self.router_ip.text()):
            QMessageBox.critical(self, "Error", f"Invalid Router IP: {self.router_ip.text()}")
            return
        if self.router_port.text() and not self.router_port.text().isdigit():
            QMessageBox.critical(self, "Error", f"Invalid Router Port: {self.router_port.text()}")
            return

        config = {
            "adapter_name": self.adapter_combo.currentText(),
            "ip_address": self.ip_address.text(),
            "subnet_mask": self.subnet_mask.text(),
            "gateway": self.gateway.text(),
            "dns_primary": self.dns_primary.text(),
            "dns_secondary": self.dns_secondary.text(),
            "router_ip": self.router_ip.text(),
            "router_port": self.router_port.text(),
            "open_router": self.open_router.isChecked(),
            "router_protocol": self.router_protocol_combo.currentText(),
        }
        self.db.save_config(config_name, config)
        self.update_config_list()
        if self.wifi_supported:
            self.update_wifi_profile_list()
        self.main_app_controller.update_tray_menu()
        QMessageBox.information(self, "Success", f"Configuration '{config_name}' saved.")
        self.clear_fields()

    def delete_config(self):
        """Delete selected configuration."""
        config_name = self.config_select.currentText()
        if not config_name:
            QMessageBox.critical(self, "Error", "Select a configuration to delete.")
            return
        self.db.delete_config(config_name)
        self.update_config_list()
        if self.wifi_supported:
            self.update_wifi_profile_list()
        self.main_app_controller.update_tray_menu()
        QMessageBox.information(self, "Success", f"Configuration '{config_name}' deleted.")
        self.clear_fields()

    def clear_fields(self):
        """Clear input fields."""
        self.config_name.clear()
        self.ip_address.clear()
        self.subnet_mask.clear()
        self.gateway.clear()
        self.dns_primary.clear()
        self.dns_secondary.clear()
        self.router_ip.clear()
        self.router_port.clear()
        self.router_protocol_combo.setCurrentText("http")
        self.open_router.setChecked(False)
        if self.wifi_supported:
            self.wifi_ssid.clear()
            self.wifi_password.clear()
            self.auth_type_combo.setCurrentText("WPA2PSK")
            self.wifi_profile_combo.setCurrentText("None")
            self.nearby_networks_combo.setCurrentText("None")

    def update_wifi_controls_state(self, adapter_name=None):
        """
        Enable or disable Wi-Fi input fields and the apply button based on
        whether the selected adapter is a Wi-Fi adapter.
        """
        if not self.wifi_supported:
            # If Wi-Fi isn't supported at all, this method shouldn't be called
            # or all Wi-Fi widgets would already be absent/disabled.
            return

        if adapter_name is None:
            adapter_name = self.adapter_combo.currentText()

        is_selected_adapter_wifi = False
        if adapter_name and adapter_name != "No adapters found":
            is_selected_adapter_wifi = is_wifi_adapter(adapter_name)

        # These controls depend on the selected adapter being Wi-Fi
        self.wifi_ssid.setEnabled(is_selected_adapter_wifi)
        self.wifi_password.setEnabled(is_selected_adapter_wifi)
        self.auth_type_combo.setEnabled(is_selected_adapter_wifi)

        if hasattr(self, 'apply_wifi_btn'): # Ensure button exists
            self.apply_wifi_btn.setEnabled(is_selected_adapter_wifi)

        # Other Wi-Fi controls (scan, import, profile list, save/delete profile)
        # are generally enabled if self.wifi_supported is True.
        # Their specific logic (e.g., delete only if item selected) is handled elsewhere.

    def populate_for_new_save(self, config_data, suggested_name):
        """Populate fields with given config_data, for saving as a new profile."""
        self.clear_fields()
        self.config_name.setText(suggested_name)
        if config_data.get("adapter_name"):
            self.adapter_combo.setCurrentText(config_data["adapter_name"])
        self.ip_address.setText(config_data.get("ip_address", ""))
        self.subnet_mask.setText(config_data.get("subnet_mask", ""))
        self.gateway.setText(config_data.get("gateway", ""))
        self.dns_primary.setText(config_data.get("dns_primary", ""))
        self.dns_secondary.setText(config_data.get("dns", ""))
        self.router_ip.setText(config_data.get("router_ip", ""))
        self.router_port.setText(config_data.get("router_port", ""))
        self.router_protocol_combo.setCurrentText(config_data.get("router_protocol", "http"))
        self.open_router.setChecked(config_data.get("open_router", False))

class ViewConfigsDialog(QDialog):
    def __init__(self, configs_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Saved Network Configurations")
        layout = QVBoxLayout(self)
        self.table_widget = QTableWidget()
        self.table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table_widget)
        self.populate_table(configs_data)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)
        self.resize(800, 450)

    def populate_table(self, configs_data):
        if not configs_data or not configs_data.get("networks"):
            self.table_widget.setRowCount(1)
            self.table_widget.setColumnCount(1)
            self.table_widget.setHorizontalHeaderLabels(["Info"])
            self.table_widget.setItem(0, 0, QTableWidgetItem("No configurations available."))
            return

        networks = configs_data["networks"]
        headers = [
            "Profile Name", "Adapter Name", "IP Address", "Subnet Mask", "Gateway",
            "DNS Primary", "DNS Secondary", "Router IP", "Router Port", "Router Protocol", "Open Router"
        ]
        if hasattr(self.parent(), 'wifi_supported') and self.parent().wifi_supported:
            headers.append("Wi-Fi Profiles")
        self.table_widget.setColumnCount(len(headers))
        self.table_widget.setHorizontalHeaderLabels(headers)
        self.table_widget.setRowCount(len(networks))

        for row_idx, (name, config) in enumerate(networks.items()):
            self.table_widget.setItem(row_idx, 0, QTableWidgetItem(name))
            self.table_widget.setItem(row_idx, 1, QTableWidgetItem(config.get("adapter_name", "")))
            self.table_widget.setItem(row_idx, 2, QTableWidgetItem(config.get("ip_address", "")))
            self.table_widget.setItem(row_idx, 3, QTableWidgetItem(config.get("subnet_mask", "")))
            self.table_widget.setItem(row_idx, 4, QTableWidgetItem(config.get("gateway", "")))
            self.table_widget.setItem(row_idx, 5, QTableWidgetItem(config.get("dns_primary", "")))
            self.table_widget.setItem(row_idx, 6, QTableWidgetItem(config.get("dns", "")))
            self.table_widget.setItem(row_idx, 7, QTableWidgetItem(config.get("router_ip", "")))
            self.table_widget.setItem(row_idx, 8, QTableWidgetItem(config.get("router_port", "")))
            self.table_widget.setItem(row_idx, 9, QTableWidgetItem(config.get("router_protocol", "http")))
            self.table_widget.setItem(row_idx, 10, QTableWidgetItem(str(config.get("open_router", False))))
            if hasattr(self.parent(), 'wifi_supported') and self.parent().wifi_supported:
                wifi_profiles = self.parent().db.get_wifi_profiles(name)
                # When config_name is provided to get_wifi_profiles, it returns (ssid, password, auth_type)
                # So, p[0] is ssid, p[2] is auth_type
                profile_str = "; ".join([f"{p[0]} ({p[2]})" for p in wifi_profiles])
                self.table_widget.setItem(row_idx, 11, QTableWidgetItem(profile_str))
        self.table_widget.resizeColumnsToContents()
