from PyQt6.QtWidgets import (
    QMainWindow, QVBoxLayout, QWidget, QLineEdit, QComboBox, QPushButton,
    QCheckBox, QLabel, QMessageBox, QDialog, QTableWidget, QTableWidgetItem,
    QDialogButtonBox, QHBoxLayout, QInputDialog, QStatusBar, QScrollArea,
    QFileDialog
)
# Ensure aliased imports are used if function names clash
from network_manager import (
    list_adapters, validate_ip,
    get_wifi_profiles as nm_get_wifi_profiles,
    get_wifi_password as nm_get_wifi_password,
    has_wifi_support, get_available_networks, apply_wifi_profile, is_wifi_adapter
)
from db_manager import DBManager
class SettingsGUI(QMainWindow):
    """GUI for managing network configurations using PyQt6."""
    # Declare attributes for QLineEdit fields and other UI elements for type hinting
    config_name: QLineEdit
    ip_address: QLineEdit
    subnet_mask: QLineEdit
    gateway: QLineEdit
    dns_primary: QLineEdit
    dns_secondary: QLineEdit
    router_ip: QLineEdit
    router_port: QLineEdit
    router_refresh_interval: QLineEdit

    adapter_combo: QComboBox
    router_protocol_combo: QComboBox
    open_router: QCheckBox
    config_select: QComboBox

    # For Wi-Fi section if they are class members accessed elsewhere
    wifi_scroll_area: QScrollArea
    wifi_profile_combo: QComboBox
    nearby_networks_combo: QComboBox
    wifi_ssid: QLineEdit
    wifi_password: QLineEdit
    auth_type_combo: QComboBox
    apply_wifi_btn: QPushButton

    def __init__(self, main_app_controller):
        super().__init__()
        self.main_app_controller = main_app_controller
        try:
            self.db = DBManager()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to initialize database manager: {e}\nSettings GUI cannot function properly.")
            print(f"CRITICAL: DBManager failed to initialize: {e}")
            class DummyDB: # Fallback DummyDB
                def load_configs(self): return {"networks": {}}
                def get_wifi_profiles(self, config_name=None, decrypt_passwords=True): return ([], "DB not initialized")
                def save_config(self, c, d): return (False, "DB not initialized")
                def delete_config(self, c): return (False, "DB not initialized")
                def save_wifi_profile(self, cn, s, p, a): return (False, "DB not initialized")
                def delete_wifi_profile(self, cn, s): return (False, "DB not initialized")
                def export_all_data(self): return (None, "DB not initialized")
                def import_all_data(self, js): return (False, "DB not initialized")
            self.db = DummyDB() if not hasattr(self, 'db') else self.db


        self.wifi_supported = has_wifi_support()

        self.setWindowTitle("Network Configuration Settings")
        initial_height = 680 if self.wifi_supported else 610 # Adjusted height for new field + buttons
        self.resize(750, initial_height)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self._loading_config = False

        self.init_ui()
        self.status_bar.showMessage("Settings window ready.", 3000)


    def init_ui(self):
        """Set up the GUI."""
        main_container = QWidget()
        main_layout = QVBoxLayout(main_container)

        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        layout_adapter = QHBoxLayout()
        layout_adapter.setSpacing(10)
        adapter_label = QLabel("Network Adapter:")
        self.adapter_combo = QComboBox()
        adapters_result, adapters_msg = list_adapters()
        if adapters_msg:
             QMessageBox.warning(self, "Adapter Info", adapters_msg)
        if adapters_result:
            for short_name, detailed_name in adapters_result:
                self.adapter_combo.addItem(detailed_name, short_name) # Add detailed_name as text, short_name as userData
            if self.adapter_combo.count() > 0:
                self.adapter_combo.setCurrentIndex(0)
        else:
            self.adapter_combo.addItem("No adapters found")
            self.adapter_combo.setEnabled(False)
        layout_adapter.addWidget(adapter_label)
        layout_adapter.addWidget(self.adapter_combo, 1)
        main_layout.addLayout(layout_adapter)

        layout_config_name = QHBoxLayout()
        layout_config_name.setSpacing(10)
        config_name_label = QLabel("Configuration Name:")
        self.config_name = QLineEdit()
        layout_config_name.addWidget(config_name_label)
        layout_config_name.addWidget(self.config_name, 1)
        main_layout.addLayout(layout_config_name)

        fields_data = [
            ("IP Address:", "ip_address"),
            ("Subnet Mask:", "subnet_mask"),
            ("Default Gateway:", "gateway"),
            ("Primary DNS:", "dns_primary"),
            ("Secondary DNS (optional):", "dns_secondary"),
            ("Router Login IP (optional):", "router_ip"),
            ("Router Login Port (optional):", "router_port", "e.g., 8080"),
            ("Router Refresh Interval (s):", "router_refresh_interval", "e.g., 5"),
        ]

        for label_text, attr_name, *rest in fields_data:
            placeholder_text = rest[0] if rest else None
            field_layout = QHBoxLayout()
            field_layout.setSpacing(10)
            label = QLabel(label_text)
            line_edit = QLineEdit()
            if placeholder_text:
                line_edit.setPlaceholderText(placeholder_text)
            setattr(self, attr_name, line_edit)
            field_layout.addWidget(label)
            field_layout.addWidget(line_edit, 1)
            main_layout.addLayout(field_layout)

        router_protocol_layout = QHBoxLayout()
        router_protocol_layout.setSpacing(10)
        router_protocol_label = QLabel("Router Protocol:")
        self.router_protocol_combo = QComboBox()
        self.router_protocol_combo.addItems(["http", "https"])
        router_protocol_layout.addWidget(router_protocol_label)
        router_protocol_layout.addWidget(self.router_protocol_combo, 1)
        main_layout.addLayout(router_protocol_layout)

        self.open_router = QCheckBox("Open router login page on apply")
        main_layout.addWidget(self.open_router)

        if self.wifi_supported:
            self.wifi_scroll_area = QScrollArea()
            self.wifi_scroll_area.setWidgetResizable(True)

            wifi_widget_container = QWidget()
            wifi_main_layout = QVBoxLayout(wifi_widget_container)
            wifi_main_layout.setSpacing(10)
            wifi_main_layout.setContentsMargins(5, 5, 5, 5)

            self.add_wifi_section_content(wifi_main_layout)

            self.wifi_scroll_area.setWidget(wifi_widget_container)
            main_layout.addWidget(self.wifi_scroll_area)

        # Connect signal after adapter_combo is populated
        self.adapter_combo.currentIndexChanged.connect(self.update_wifi_controls_state) # Use currentIndexChanged or currentTextChanged

        # --- Main Action Buttons Section ---
        main_action_buttons_layout = QHBoxLayout()
        main_action_buttons_layout.setSpacing(10)
        save_button = QPushButton("Save Configuration")
        save_button.clicked.connect(self.save_config)
        delete_button = QPushButton("Delete Configuration")
        delete_button.clicked.connect(self.delete_config)
        view_button = QPushButton("View Configurations")
        view_button.clicked.connect(self.view_configs)

        main_action_buttons_layout.addStretch(1)
        main_action_buttons_layout.addWidget(save_button)
        main_action_buttons_layout.addWidget(delete_button)
        main_action_buttons_layout.addWidget(view_button)
        main_action_buttons_layout.addStretch(1)
        main_layout.addLayout(main_action_buttons_layout)

        # --- Import/Export Buttons Section (New) ---
        import_export_layout = QHBoxLayout()
        import_export_layout.setSpacing(10)
        export_button = QPushButton("Export Settings")
        export_button.clicked.connect(self._export_settings) # Connect
        import_button = QPushButton("Import Settings")
        import_button.clicked.connect(self._import_settings) # Connect

        import_export_layout.addStretch(1)
        import_export_layout.addWidget(export_button)
        import_export_layout.addWidget(import_button)
        import_export_layout.addStretch(1)
        main_layout.addLayout(import_export_layout)

        # --- Close Button Section ---
        close_button_layout = QHBoxLayout()
        # close_button_layout.setSpacing(10) # Not strictly necessary if only one button centered
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        close_button_layout.addStretch(1)
        close_button_layout.addWidget(close_button)
        close_button_layout.addStretch(1)
        main_layout.addLayout(close_button_layout)


        config_select_layout = QHBoxLayout()
        config_select_layout.setSpacing(10)
        config_select_label = QLabel("Select Config to Edit/Load:")
        self.config_select = QComboBox()
        self.config_select.currentTextChanged.connect(self.load_config_to_fields)
        config_select_layout.addWidget(config_select_label)
        config_select_layout.addWidget(self.config_select, 1)
        main_layout.addLayout(config_select_layout)

        main_layout.addStretch(1)

        self.update_config_list()
        self.setCentralWidget(main_container)
        # Initial call to set Wi-Fi controls state based on default adapter selection
        if self.wifi_supported:
            self.update_wifi_controls_state()

    def add_wifi_section_content(self, wifi_main_layout):
        wifi_label = QLabel("Wi-Fi Settings:")
        wifi_main_layout.addWidget(wifi_label)

        wifi_profile_layout = QHBoxLayout()
        wifi_profile_layout.setSpacing(10)
        wifi_profile_label = QLabel("Saved Wi-Fi Profiles:")
        self.wifi_profile_combo = QComboBox()
        self.wifi_profile_combo.addItem("None")
        self.update_wifi_profile_list()
        self.wifi_profile_combo.currentTextChanged.connect(self._on_wifi_profile_selected)
        import_wifi_btn = QPushButton("Import System Wi-Fi")
        import_wifi_btn.clicked.connect(self.import_system_wifi)
        wifi_profile_layout.addWidget(wifi_profile_label)
        wifi_profile_layout.addWidget(self.wifi_profile_combo, 1)
        wifi_profile_layout.addWidget(import_wifi_btn)
        wifi_main_layout.addLayout(wifi_profile_layout)

        nearby_layout = QHBoxLayout()
        nearby_layout.setSpacing(10)
        nearby_label = QLabel("Nearby Wi-Fi Networks:")
        self.nearby_networks_combo = QComboBox()
        self.nearby_networks_combo.addItem("None")
        scan_btn = QPushButton("Scan Nearby")
        scan_btn.clicked.connect(self.scan_nearby_networks)
        nearby_layout.addWidget(nearby_label)
        nearby_layout.addWidget(self.nearby_networks_combo, 1)
        nearby_layout.addWidget(scan_btn)
        wifi_main_layout.addLayout(nearby_layout)

        wifi_ssid_layout = QHBoxLayout()
        wifi_ssid_layout.setSpacing(10)
        ssid_label = QLabel("Wi-Fi SSID:")
        self.wifi_ssid = QLineEdit()
        wifi_ssid_layout.addWidget(ssid_label)
        wifi_ssid_layout.addWidget(self.wifi_ssid, 1)
        wifi_main_layout.addLayout(wifi_ssid_layout)

        wifi_password_layout = QHBoxLayout()
        wifi_password_layout.setSpacing(10)
        pwd_label = QLabel("Wi-Fi Password:")
        self.wifi_password = QLineEdit()
        self.wifi_password.setEchoMode(QLineEdit.EchoMode.Password)
        wifi_password_layout.addWidget(pwd_label)
        wifi_password_layout.addWidget(self.wifi_password, 1)
        wifi_main_layout.addLayout(wifi_password_layout)

        wifi_auth_layout = QHBoxLayout()
        wifi_auth_layout.setSpacing(10)
        auth_label = QLabel("Authentication Type:")
        self.auth_type_combo = QComboBox()
        self.auth_type_combo.addItems(["open", "WEP", "WPAPSK", "WPA2PSK", "WPA3SAE"])
        self.auth_type_combo.setCurrentText("WPA2PSK")
        wifi_auth_layout.addWidget(auth_label)
        wifi_auth_layout.addWidget(self.auth_type_combo, 1)
        wifi_main_layout.addLayout(wifi_auth_layout)

        wifi_btn_layout = QHBoxLayout()
        wifi_btn_layout.setSpacing(10)
        save_wifi_btn = QPushButton("Save Wi-Fi to Current Config")
        save_wifi_btn.clicked.connect(self.save_wifi)
        delete_wifi_btn = QPushButton("Delete Selected Saved Wi-Fi")
        delete_wifi_btn.clicked.connect(self.delete_wifi)
        self.apply_wifi_btn = QPushButton("Apply Selected/Entered Wi-Fi")
        self.apply_wifi_btn.clicked.connect(self.apply_wifi)
        wifi_btn_layout.addStretch(1)
        wifi_btn_layout.addWidget(save_wifi_btn)
        wifi_btn_layout.addWidget(delete_wifi_btn)
        wifi_btn_layout.addWidget(self.apply_wifi_btn)
        wifi_btn_layout.addStretch(1)
        wifi_main_layout.addLayout(wifi_btn_layout)

    def _on_wifi_profile_selected(self, selected_text):
        # Allow processing if loading config and selected_text is "None" (to clear fields)
        if self._loading_config and selected_text != "None":
            return

        if not selected_text or selected_text == "None":
            self.wifi_ssid.clear()
            self.wifi_password.clear()
            self.auth_type_combo.setCurrentText("WPA2PSK")
            return

        try:
            parts = selected_text.split(": ", 1)
            config_name_from_profile = parts[0]
            ssid_auth_part = parts[1]
            ssid = ssid_auth_part.split(" (")[0]
            auth_type = ssid_auth_part.split("(")[1].rstrip(")")

            if self.config_select.currentText() != config_name_from_profile:
                 self._loading_config = True
                 self.config_select.setCurrentText(config_name_from_profile)
                 self._loading_config = False

            self.wifi_ssid.setText(ssid)
            self.auth_type_combo.setCurrentText(auth_type)
            self.wifi_password.clear()

            self.status_bar.showMessage(f"Loaded Wi-Fi: {ssid} (for config: {config_name_from_profile}). Enter/verify password.", 7000)
        except Exception as e:
            print(f"Error parsing Wi-Fi profile selection '{selected_text}': {e}")
            self.status_bar.showMessage("Error processing Wi-Fi profile selection.", 5000)
            self.wifi_ssid.clear()
            self.wifi_password.clear()
            self.auth_type_combo.setCurrentText("WPA2PSK")

    def scan_nearby_networks(self):
        networks, message = get_available_networks()
        if message:
            self.status_bar.showMessage(f"Scan info: {message}", 5000)
            QMessageBox.warning(self, "Scan Info", message)

        self.nearby_networks_combo.clear()
        self.nearby_networks_combo.addItem("None")
        if networks:
            for ssid, auth_type, signal in networks:
                self.nearby_networks_combo.addItem(f"{ssid} ({auth_type}, {signal})")
            self.status_bar.showMessage(f"Found {len(networks)} nearby networks.", 3000)
        elif not message:
             QMessageBox.information(self, "Info", "No nearby Wi-Fi networks found.")
             self.status_bar.showMessage("No nearby Wi-Fi networks found.", 3000)

    def update_wifi_profile_list(self):
        if not self.wifi_supported or not hasattr(self, 'wifi_profile_combo'):
            return
        current_selection = self.wifi_profile_combo.currentText()
        self.wifi_profile_combo.clear()
        self.wifi_profile_combo.addItem("None")
        profiles, message = self.db.get_wifi_profiles()
        if message:
            self.status_bar.showMessage(f"Error loading Wi-Fi profiles: {message}", 5000)
            if "Encryption service not available" not in message:
                QMessageBox.warning(self, "Wi-Fi Profile Info", f"Could not load Wi-Fi profiles: {message}")
            return
        if profiles:
            for profile_data in profiles:
                config_name, ssid, _, auth_type = profile_data
                self.wifi_profile_combo.addItem(f"{config_name}: {ssid} ({auth_type})")
            if self.wifi_profile_combo.findText(current_selection) != -1:
                self.wifi_profile_combo.setCurrentText(current_selection)

    def import_system_wifi(self):
        profiles, message = nm_get_wifi_profiles()
        if message:
            self.status_bar.showMessage(f"System Wi-Fi import error: {message}", 5000)
            QMessageBox.warning(self, "Import Info", f"Could not retrieve system Wi-Fi profiles: {message}")
            return
        if not profiles:
            self.status_bar.showMessage("No system Wi-Fi profiles found to import.", 3000)
            QMessageBox.information(self, "Info", "No Wi-Fi profiles found on the system.")
            return

        profile_items = [f"{p_ssid} ({p_auth_type})" for p_ssid, p_auth_type in profiles]
        selected_item, ok = QInputDialog.getItem(
            self, "Select Wi-Fi Profile", "Choose a Wi-Fi profile:", profile_items, 0, False
        )
        if ok and selected_item:
            ssid = selected_item.split(" (")[0]
            auth_type_from_selected = selected_item.split("(")[1].rstrip(")")

            password, pwd_message = nm_get_wifi_password(ssid)
            if pwd_message and not password:
                 self.status_bar.showMessage(f"Password retrieval for {ssid}: {pwd_message}", 5000)
                 QMessageBox.warning(self, "Password Retrieval", pwd_message)

            self.wifi_ssid.setText(ssid)
            self.wifi_password.setText(password or "")
            self.auth_type_combo.setCurrentText(auth_type_from_selected)
            self.status_bar.showMessage(f"Imported system Wi-Fi profile for {ssid}.", 3000)

    def save_wifi(self):
        try:
            config_name = self.config_name.text()
            ssid = self.wifi_ssid.text()
            password = self.wifi_password.text()
            auth_type = self.auth_type_combo.currentText()

            selected_network = self.nearby_networks_combo.currentText()
            if selected_network != "None" and selected_network != "":
                selected_ssid = selected_network.split(" (")[0]
                selected_auth = selected_network.split("(")[1].split(",")[0]
                self.wifi_ssid.setText(selected_ssid)
                self.auth_type_combo.setCurrentText(selected_auth)
                ssid = selected_ssid
                auth_type = selected_auth

            if not config_name:
                self.status_bar.showMessage("Save Wi-Fi failed: Configuration name is required.", 5000)
                QMessageBox.critical(self, "Validation Error", "Configuration name is required to associate with this Wi-Fi profile.")
                return
            if not ssid:
                self.status_bar.showMessage("Save Wi-Fi failed: Wi-Fi SSID is required.", 5000)
                QMessageBox.critical(self, "Validation Error", "Wi-Fi SSID is required.")
                return
            if auth_type != "open" and not password:
                self.status_bar.showMessage("Save Wi-Fi failed: Password is required for non-open networks.", 5000)
                QMessageBox.critical(self, "Validation Error", "Password is required for non-open Wi-Fi networks.")
                return

            success, message = self.db.save_wifi_profile(config_name, ssid, password, auth_type)
            if success:
                self.update_wifi_profile_list()
                self.main_app_controller.update_tray_menu()
                self.status_bar.showMessage(f"Wi-Fi profile for '{ssid}' saved.", 3000)
                QMessageBox.information(self, "Success", message)
            else:
                self.status_bar.showMessage(f"Failed to save Wi-Fi profile: {message}", 5000)
                QMessageBox.critical(self, "DB Error", message)
        except Exception as e:
            self.status_bar.showMessage(f"Save Wi-Fi error: {e}", 5000)
            QMessageBox.critical(self, "Save Wi-Fi Error", f"An unexpected error occurred: {e}")

    def delete_wifi(self):
        selected_profile_text = self.wifi_profile_combo.currentText()
        if not selected_profile_text or selected_profile_text == "None":
            self.status_bar.showMessage("Delete Wi-Fi failed: No profile selected.", 5000)
            QMessageBox.critical(self, "Selection Error", "Please select a Wi-Fi profile to delete.")
            return

        try:
            parts = selected_profile_text.split(": ", 1)
            config_name = parts[0]
            ssid_auth_part = parts[1]
            ssid = ssid_auth_part.split(" (")[0]

            reply = QMessageBox.question(self, 'Delete Wi-Fi Profile',
                                         f"Are you sure you want to delete the Wi-Fi profile '{ssid}' for configuration '{config_name}'?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)

            if reply == QMessageBox.StandardButton.Yes:
                success, message = self.db.delete_wifi_profile(config_name, ssid)
                if success:
                    self.update_wifi_profile_list()
                    self.main_app_controller.update_tray_menu()
                    self.status_bar.showMessage(f"Wi-Fi profile '{ssid}' deleted.", 3000)
                    QMessageBox.information(self, "Success", message)
                else:
                    self.status_bar.showMessage(f"Failed to delete Wi-Fi profile: {message}", 5000)
                    QMessageBox.critical(self, "DB Error", message)
        except Exception as e:
            self.status_bar.showMessage(f"Delete Wi-Fi error: {e}", 5000)
            QMessageBox.critical(self, "Delete Wi-Fi Error", f"An unexpected error occurred: {e}")

    def apply_wifi(self):
        try:
            adapter_name = self.adapter_combo.currentData() # Use short_name from userData
            if not adapter_name or adapter_name == "No adapters found":
                self.status_bar.showMessage("Apply Wi-Fi failed: No adapter selected.", 5000)
                QMessageBox.critical(self, "Selection Error", "No network adapter selected or available.")
                return

            ssid_to_apply = ""
            auth_type_to_apply = ""
            password_to_apply = ""

            selected_nearby = self.nearby_networks_combo.currentText()
            selected_profile_text = self.wifi_profile_combo.currentText()

            if selected_nearby != "None" and selected_nearby != "":
                ssid_to_apply = selected_nearby.split(" (")[0]
                auth_type_to_apply = selected_nearby.split("(")[1].split(",")[0]
                password_to_apply = self.wifi_password.text()
                if auth_type_to_apply != "open" and not password_to_apply:
                    self.status_bar.showMessage(f"Apply Wi-Fi: Password needed for {ssid_to_apply}.", 5000)
                    QMessageBox.critical(self, "Input Error", f"Password is required to connect to '{ssid_to_apply}'. Please enter it in the Wi-Fi Password field.")
                    return
            elif selected_profile_text != "None" and selected_profile_text != "":
                parts = selected_profile_text.split(": ", 1)
                config_name_of_profile = parts[0]
                ssid_auth_part = parts[1]
                ssid_to_apply = ssid_auth_part.split(" (")[0]
                auth_type_to_apply = ssid_auth_part.split("(")[1].rstrip(")")

                profiles, msg = self.db.get_wifi_profiles(config_name_of_profile)
                if msg:
                    self.status_bar.showMessage(f"Apply Wi-Fi Error: {msg}", 5000)
                    QMessageBox.critical(self, "Profile Error", f"Could not load Wi-Fi profile details: {msg}")
                    return

                found_profile = False
                if profiles:
                    for p_config_name, p_ssid, p_password, p_auth_type in profiles:
                        if p_config_name == config_name_of_profile and p_ssid == ssid_to_apply and p_auth_type == auth_type_to_apply:
                            password_to_apply = p_password
                            found_profile = True
                            break

                if not found_profile:
                    self.status_bar.showMessage(f"Apply Wi-Fi: Profile details not found for {ssid_to_apply}.", 5000)
                    QMessageBox.critical(self, "Profile Error", f"Could not find password details for saved Wi-Fi profile '{ssid_to_apply}'. Try re-saving the Wi-Fi profile with a password.")
                    return
            else:
                self.status_bar.showMessage("Apply Wi-Fi failed: No profile or network selected.", 5000)
                QMessageBox.critical(self, "Selection Error", "Select a Wi-Fi profile or a nearby network to apply.")
                return

            success, message = apply_wifi_profile(ssid_to_apply, password_to_apply, adapter_name, auth_type_to_apply)
            if success:
                self.status_bar.showMessage(f"Successfully applied Wi-Fi: {ssid_to_apply}", 3000)
                QMessageBox.information(self, "Success", message or f"Successfully connected to Wi-Fi '{ssid_to_apply}'.")
            else:
                self.status_bar.showMessage(f"Failed to apply Wi-Fi: {ssid_to_apply}. Error: {message}", 7000)
                QMessageBox.critical(self, "Connection Error", message or f"Failed to connect to Wi-Fi '{ssid_to_apply}'.")
        except Exception as e:
            self.status_bar.showMessage(f"Apply Wi-Fi error: {e}", 5000)
            QMessageBox.critical(self, "Apply Wi-Fi Error", f"An unexpected error occurred: {e}")

    def view_configs(self):
        configs = self.db.load_configs()
        if not configs or not configs["networks"]:
            self.status_bar.showMessage("No configurations to view.", 3000)
            QMessageBox.information(self, "Info", "No configurations available.")
            return
        dialog = ViewConfigsDialog(configs, self)
        dialog.exec()
        self.status_bar.showMessage("Viewed configurations.", 3000)

    def update_adapters(self):
        self.adapter_combo.clear()
        adapters_result, message = list_adapters() # list_adapters returns list of tuples
        if message:
            self.status_bar.showMessage(f"Adapter update: {message}", 5000)
            QMessageBox.warning(self, "Adapter Info", message)

        if adapters_result:
            for short_name, detailed_name in adapters_result:
                self.adapter_combo.addItem(detailed_name, short_name) # Add detailed_name as text, short_name as userData

            if self.adapter_combo.count() > 0:
                 self.adapter_combo.setCurrentIndex(0)
        else:
            self.adapter_combo.addItem("No adapters found")
            self.adapter_combo.setEnabled(False)

    def update_config_list(self):
        current_selection = self.config_select.currentText()
        self.config_select.clear()
        configs = self.db.load_configs()
        if configs and configs.get("networks"):
            self.config_select.addItems(list(configs["networks"].keys()))
            if self.config_select.findText(current_selection) != -1:
                self.config_select.setCurrentText(current_selection)
            elif self.config_select.count() > 0:
                self.config_select.setCurrentIndex(0)

    def load_config_to_fields(self, config_name):
        if self._loading_config:
            return

        if not config_name or config_name == "None":
            self.clear_fields()
            self.status_bar.showMessage("No configuration selected or configuration cleared.", 3000)
            return

        configs = self.db.load_configs()
        if config_name in configs["networks"]:
            config = configs["networks"][config_name]
            self.config_name.setText(config_name)
            self.ip_address.setText(config.get("ip_address", ""))
            self.subnet_mask.setText(config.get("subnet_mask", ""))
            self.gateway.setText(config.get("gateway", ""))
            self.dns_primary.setText(config.get("dns_primary", ""))
            self.dns_secondary.setText(config.get("dns_secondary", ""))
            self.router_ip.setText(config.get("router_ip", ""))
            self.router_port.setText(config.get("router_port", ""))
            self.router_refresh_interval.setText(str(config.get("router_refresh_interval", 5)))
            self.router_protocol_combo.setCurrentText(config.get("router_protocol", "http"))

            # Set adapter_combo based on short_name stored in config
            adapter_short_name_from_config = config.get("adapter_name", "")
            if adapter_short_name_from_config:
                for i in range(self.adapter_combo.count()):
                    if self.adapter_combo.itemData(i) == adapter_short_name_from_config:
                        self.adapter_combo.setCurrentIndex(i)
                        break # Adapter found and set
                # No 'else' here to avoid resetting to index 0 if adapter_short_name_from_config is empty
                else: # Adapter short_name from config not found in combo
                    print(f"Warning: Adapter '{adapter_short_name_from_config}' from saved config not found in current adapter list.")
                    if self.adapter_combo.count() > 0:
                        self.adapter_combo.setCurrentIndex(0) # Fallback

            self.open_router.setChecked(config.get("open_router", False))

            self._loading_config = True
            if self.wifi_supported and hasattr(self, 'wifi_profile_combo'): # Ensure combo exists
                self.wifi_ssid.clear()
                self.wifi_password.clear()
                self.auth_type_combo.setCurrentText("WPA2PSK")

                profiles_for_config, msg = self.db.get_wifi_profiles(config_name)
                if msg:
                    self.status_bar.showMessage(f"Error loading Wi-Fi profiles for {config_name}: {msg}", 5000)
                    self.wifi_profile_combo.setCurrentText("None")
                elif profiles_for_config:
                    first_profile_data = profiles_for_config[0]
                    target_combo_text = f"{first_profile_data[0]}: {first_profile_data[1]} ({first_profile_data[3]})"

                    found_idx = self.wifi_profile_combo.findText(target_combo_text)
                    if found_idx != -1:
                         self.wifi_profile_combo.setCurrentIndex(found_idx)
                    else:
                         self.wifi_profile_combo.setCurrentText("None")
                else:
                     self.wifi_profile_combo.setCurrentText("None")

            self.status_bar.showMessage(f"Loaded details for configuration: {config_name}", 5000)
            self._loading_config = False
        else:
            self.status_bar.showMessage(f"Configuration '{config_name}' not found.", 5000)

    def save_config(self):
        try:
            config_name = self.config_name.text()
            if not config_name:
                self.status_bar.showMessage("Save failed: Configuration name cannot be empty.", 5000)
                QMessageBox.critical(self, "Validation Error", "Configuration name is required.")
                return

            if self.ip_address.text():
                required_static_fields = {
                    "IP Address": self.ip_address.text(),
                    "Subnet Mask": self.subnet_mask.text(),
                    "Gateway": self.gateway.text(),
                    "Primary DNS": self.dns_primary.text(),
                }
                for name, value in required_static_fields.items():
                    if not value:
                        self.status_bar.showMessage(f"Save failed: {name} is required.", 5000)
                        QMessageBox.critical(self, "Validation Error", f"{name} is required for a static configuration when IP Address is provided.")
                        return
                    if not validate_ip(value):
                        self.status_bar.showMessage(f"Save failed: Invalid {name} ({value}).", 5000)
                        QMessageBox.critical(self, "Validation Error", f"Invalid {name}: {value}")
                        return

            dns_secondary_val = self.dns_secondary.text()
            if dns_secondary_val and not validate_ip(dns_secondary_val):
                self.status_bar.showMessage("Save failed: Invalid Secondary DNS.", 5000)
                QMessageBox.critical(self, "Validation Error", f"Invalid Secondary DNS: {dns_secondary_val}")
                return
            router_ip_val = self.router_ip.text()
            if router_ip_val and not validate_ip(router_ip_val):
                self.status_bar.showMessage("Save failed: Invalid Router IP.", 5000)
                QMessageBox.critical(self, "Validation Error", f"Invalid Router IP: {router_ip_val}")
                return
            router_port_val = self.router_port.text()
            if router_port_val and not router_port_val.isdigit():
                self.status_bar.showMessage("Save failed: Invalid Router Port.", 5000)
                QMessageBox.critical(self, "Validation Error", f"Invalid Router Port: {router_port_val}. Must be a number.")
                return
            
            router_refresh_interval_str = self.router_refresh_interval.text()
            router_refresh_interval_val = 5 # Default
            if router_refresh_interval_str:
                if not router_refresh_interval_str.isdigit() or int(router_refresh_interval_str) <= 0:
                    self.status_bar.showMessage("Save failed: Invalid Router Refresh Interval.", 5000)
                    QMessageBox.critical(self, "Validation Error", "Router Refresh Interval must be a positive number (seconds).")
                    return
                router_refresh_interval_val = int(router_refresh_interval_str)

            config_data = { # Renamed from config to config_data
                "ip_address": self.ip_address.text(),
                "subnet_mask": self.subnet_mask.text(),
                "gateway": self.gateway.text(),
                "dns_primary": self.dns_primary.text(),
                "dns_secondary": self.dns_secondary.text(),
                "router_ip": self.router_ip.text(),
                "router_port": self.router_port.text(),
                "open_router": self.open_router.isChecked(),
                "router_protocol": self.router_protocol_combo.currentText(),
                "router_refresh_interval": router_refresh_interval_val,
            }
            config_data["adapter_name"] = self.adapter_combo.currentData() # Store short_name

            success, message = self.db.save_config(config_name, config_data) # Use config_data
            if success:
                self.update_config_list()
                if self.wifi_supported:
                    self.update_wifi_profile_list()

                self.main_app_controller.update_tray_menu()
                self.status_bar.showMessage(message, 3000)
                QMessageBox.information(self, "Success", message)
                self.clear_fields()
            else:
                self.status_bar.showMessage(f"Save failed: {message}", 5000)
                QMessageBox.critical(self, "Save Error", message)

        except Exception as e:
            self.status_bar.showMessage(f"Save config error: {e}", 5000)
            QMessageBox.critical(self, "Save Error", f"An unexpected error occurred while saving the configuration: {e}")

    def delete_config(self):
        config_name = self.config_select.currentText()
        if not config_name:
            self.status_bar.showMessage("Delete failed: No configuration selected.", 5000)
            QMessageBox.critical(self, "Error", "Select a configuration to delete.")
            return

        reply = QMessageBox.question(self, 'Delete Confirmation',
                                     f"Are you sure you want to delete the configuration '{config_name}'?\nThis will also delete any associated Wi-Fi profiles.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.db.delete_config(config_name)
                self.update_config_list()
                if self.wifi_supported:
                    self.update_wifi_profile_list()
                self.main_app_controller.update_tray_menu()
                self.status_bar.showMessage(f"Configuration '{config_name}' deleted.", 3000)
                QMessageBox.information(self, "Success", f"Configuration '{config_name}' and associated Wi-Fi profiles deleted.")
                self.clear_fields()
            except Exception as e:
                 self.status_bar.showMessage(f"Delete config error: {e}", 5000)
                 QMessageBox.critical(self, "Delete Error", f"An error occurred while deleting '{config_name}': {e}")

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
        self.router_refresh_interval.setText("5") # Default value
        self.router_protocol_combo.setCurrentText("http")
        self.open_router.setChecked(False)
        if self.wifi_supported and hasattr(self, 'wifi_ssid'): # Check attributes exist
            self.wifi_ssid.clear()
            self.wifi_password.clear()
            self.auth_type_combo.setCurrentText("WPA2PSK")
            if hasattr(self, 'wifi_profile_combo'):
                self.wifi_profile_combo.setCurrentText("None")
            if hasattr(self, 'nearby_networks_combo'):
                self.nearby_networks_combo.setCurrentText("None")
        self.status_bar.showMessage("Input fields cleared.", 3000)

    def update_wifi_controls_state(self, _index_or_text_from_signal=None): # Parameter can be ignored
        if not self.wifi_supported:
            if hasattr(self, 'wifi_scroll_area'):
                self.wifi_scroll_area.setEnabled(False)
            return

        # Get the short_name from currentData
        current_adapter_short_name = self.adapter_combo.currentData()

        is_selected_adapter_wifi = False
        if current_adapter_short_name: # Ensure it's not None (e.g. for "No adapters found" item)
            is_selected_adapter_wifi = is_wifi_adapter(current_adapter_short_name)

        if hasattr(self, 'wifi_scroll_area'):
            self.wifi_scroll_area.setEnabled(is_selected_adapter_wifi)

    def populate_for_new_save(self, config_data, suggested_name):
        self.clear_fields()
        self.config_name.setText(suggested_name)

        # config_data["adapter_name"] from get_current_adapter_config is the short_name
        adapter_short_name_to_set = config_data.get("adapter_name")
        if adapter_short_name_to_set:
            for i in range(self.adapter_combo.count()):
                if self.adapter_combo.itemData(i) == adapter_short_name_to_set:
                    self.adapter_combo.setCurrentIndex(i)
                    break
            else:
                 print(f"Warning: Current adapter '{adapter_short_name_to_set}' not found in combo list during populate_for_new_save.")
                 if self.adapter_combo.count() > 0:
                     self.adapter_combo.setCurrentIndex(0) # Fallback

        self.ip_address.setText(config_data.get("ip_address", ""))
        self.subnet_mask.setText(config_data.get("subnet_mask", ""))
        self.gateway.setText(config_data.get("gateway", ""))
        self.dns_primary.setText(config_data.get("dns_primary", ""))
        self.dns_secondary.setText(config_data.get("dns", "") or config_data.get("dns_secondary", ""))
        self.router_ip.setText(config_data.get("router_ip", ""))
        self.router_port.setText(config_data.get("router_port", ""))
        self.router_refresh_interval.setText(str(config_data.get("router_refresh_interval", 5)))
        self.router_protocol_combo.setCurrentText(config_data.get("router_protocol", "http"))
        self.open_router.setChecked(config_data.get("open_router", False))
        self.status_bar.showMessage(f"Current network settings populated for saving as '{suggested_name}'.", 5000)

    # --- Export/Import Methods ---
    def _export_settings(self):
        try:
            json_data, error = self.db.export_all_data()
            if error:
                self.status_bar.showMessage(f"Export failed: {error}", 5000)
                QMessageBox.critical(self, "Export Error", f"Failed to export data: {error}")
                return

            if not json_data:
                self.status_bar.showMessage("Export failed: No data to export.", 5000)
                QMessageBox.information(self, "Export Info", "No data available to export.")
                return

            file_path, _ = QFileDialog.getSaveFileName(self, "Export Settings", "", "JSON Files (*.json)")
            if file_path:
                if not file_path.endswith(".json"):
                    file_path += ".json"
                try:
                    with open(file_path, 'w') as f:
                        f.write(json_data)
                    self.status_bar.showMessage(f"Settings exported to {file_path}", 5000)
                    QMessageBox.information(self, "Export Successful", f"All settings successfully exported to:\n{file_path}")
                except IOError as e:
                    self.status_bar.showMessage(f"Export IOError: {e}", 5000)
                    QMessageBox.critical(self, "Export File Error", f"Failed to write to file {file_path}: {e}")
        except Exception as e:
            self.status_bar.showMessage(f"Export error: {e}", 5000)
            QMessageBox.critical(self, "Export Error", f"An unexpected error occurred during export: {e}")

    def _import_settings(self):
        try:
            file_path, _ = QFileDialog.getOpenFileName(self, "Import Settings", "", "JSON Files (*.json)")
            if file_path:
                try:
                    with open(file_path, 'r') as f:
                        json_string = f.read()
                except IOError as e:
                    self.status_bar.showMessage(f"Import IOError: {e}", 5000)
                    QMessageBox.critical(self, "Import File Error", f"Failed to read file {file_path}: {e}")
                    return

                if not json_string:
                    self.status_bar.showMessage("Import failed: File is empty.", 5000)
                    QMessageBox.warning(self, "Import Warning", "The selected file is empty.")
                    return

                success, message = self.db.import_all_data(json_string)

                if success:
                    QMessageBox.information(self, "Import Successful", message)
                    self.status_bar.showMessage("Settings imported successfully. Refreshing UI.", 5000)
                else:
                    QMessageBox.warning(self, "Import Result", message)
                    self.status_bar.showMessage("Import completed with issues. See dialog for details.", 7000)

                self.update_config_list()
                if self.wifi_supported:
                    self.update_wifi_profile_list()
                self.main_app_controller.update_tray_menu()

        except Exception as e:
            self.status_bar.showMessage(f"Import error: {e}", 5000)
            QMessageBox.critical(self, "Import Error", f"An unexpected error occurred during import: {e}")


class ViewConfigsDialog(QDialog):
    # Forward reference for SettingsGUI type hint
    def __init__(self, configs_data, parent_settings_gui: 'SettingsGUI | None' = None):
        super().__init__(parent_settings_gui) # Pass it as QWidget parent
        self.parent_settings_gui = parent_settings_gui # Store it for typed access

        self.setWindowTitle("Saved Network Configurations")
        self.resize(800, 450)
        layout = QVBoxLayout(self)

        self.table_widget = QTableWidget()
        self.table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self.table_widget.horizontalHeader()
        if header is not None:
            header.setStretchLastSection(True)
        layout.addWidget(self.table_widget)

        self.populate_table(configs_data)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        header_view = self.table_widget.horizontalHeader()
        if header_view: # Check if header_view is not None
            header_view.setStretchLastSection(True)

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
            "DNS Primary", "DNS Secondary", "Router IP", "Router Port", "Router Protocol",
            "Open Router", "Router Refresh (s)"
        ]
        if self.parent_settings_gui and self.parent_settings_gui.wifi_supported:
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
            dns_secondary_val = config.get("dns_secondary", "") or config.get("dns", "")
            self.table_widget.setItem(row_idx, 6, QTableWidgetItem(dns_secondary_val))
            self.table_widget.setItem(row_idx, 7, QTableWidgetItem(config.get("router_ip", "")))
            self.table_widget.setItem(row_idx, 8, QTableWidgetItem(config.get("router_port", "")))
            self.table_widget.setItem(row_idx, 9, QTableWidgetItem(config.get("router_protocol", "http")))
            self.table_widget.setItem(row_idx, 10, QTableWidgetItem(str(config.get("open_router", False))))
            self.table_widget.setItem(row_idx, 11, QTableWidgetItem(str(config.get("router_refresh_interval", 5))))

            if self.parent_settings_gui and self.parent_settings_gui.wifi_supported and hasattr(self.parent_settings_gui, 'db'):
                wifi_col_idx = 12 # Column index for Wi-Fi profiles
                wifi_profiles_data, wifi_msg = self.parent_settings_gui.db.get_wifi_profiles(name)
                if wifi_msg:
                    print(f"Error getting Wi-Fi profiles for {name}: {wifi_msg}")

                profile_strs = []
                if wifi_profiles_data:
                    for _, p_ssid, _, p_auth_type in wifi_profiles_data: # config_name, ssid, password, auth_type
                        profile_strs.append(f"{p_ssid} ({p_auth_type})")
                self.table_widget.setItem(row_idx, wifi_col_idx, QTableWidgetItem("; ".join(profile_strs)))
        self.table_widget.resizeColumnsToContents()
