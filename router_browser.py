import sys
import os
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QLineEdit,
    QInputDialog, QMessageBox, QMenu, QLabel, QStatusBar
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile, QWebEnginePage
from PyQt6.QtCore import QUrl, QTimer, QDir
from PyQt6.QtGui import QPixmap
from PyQt6.QtGui import QAction
import socket
import keyring
from db_manager import DBManager
from network_manager import get_current_adapter_config, list_adapters # Import list_adapters
from datetime import datetime


class RouterBrowser(QMainWindow):
    """Custom browser for router login with navigation, credentials, and HTTPS support."""

    def __init__(self, router_ip, router_port=None, refresh_interval=5000, preferred_protocol="http"):
        super().__init__()
        if not router_ip: # Ensure router_ip is provided
            raise ValueError("Router IP must be provided for RouterBrowser.")

        self.target_ip = router_ip # Use router_ip directly
        self.router_port = router_port
        self.current_protocol_is_https = (preferred_protocol.lower() == "https")
        self.refresh_interval = refresh_interval
        self.monitor_active = True
        self.db = DBManager()
        self.current_credential_index = 0
        self.credentials = []

        try:
            self.machine_name = socket.gethostname()
        except Exception:
            self.machine_name = "unknown_machine"

        self._setup_web_profile()
        self.init_ui() # Sets up self.web_view among other things

        self.load_credentials()
        self.web_view.load(QUrl(self.build_url()))
        self.start_url_monitor()
        self.update_network_status()

    def _setup_web_profile(self):
        """Sets up the web engine profile and cookie storage."""
        self.cookie_dir = os.path.join(
            os.getcwd(), "cookies", self.target_ip.replace(".", "_")
        )
        QDir().mkpath(self.cookie_dir)
        self.profile = QWebEngineProfile(f"Router_{self.target_ip}", self)
        self.profile.setPersistentStoragePath(self.cookie_dir)
        settings = self.profile.settings()
        if settings:
            settings.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, True)

    def build_url(self, force_https=None):
        """Build the target URL with protocol and port."""
        use_https_for_build = self.current_protocol_is_https
        if force_https is not None:
            use_https_for_build = force_https

        protocol = "https" if use_https_for_build else "http"
        if self.router_port:
            return f"{protocol}://{self.target_ip}:{self.router_port}"
        return f"{protocol}://{self.target_ip}"

    def _create_navigation_bar(self):
        """Creates the navigation bar with URL, back, forward, reload, bookmarks, and history."""
        nav_layout = QHBoxLayout()

        back_button = QPushButton("Back")
        back_button.clicked.connect(self.web_view.back)
        nav_layout.addWidget(back_button)

        forward_button = QPushButton("Forward")
        forward_button.clicked.connect(self.web_view.forward)
        nav_layout.addWidget(forward_button)

        reload_button = QPushButton("Reload")
        reload_button.clicked.connect(self.web_view.reload)
        nav_layout.addWidget(reload_button)

        self.url_bar = QLineEdit()
        self.url_bar.setText(self.build_url())
        self.url_bar.returnPressed.connect(self.navigate_to_url)
        # Connect urlChanged from web_view to update url_bar text
        self.web_view.urlChanged.connect(lambda url: self.url_bar.setText(url.toString()))
        nav_layout.addWidget(self.url_bar)

        self._create_menus(nav_layout) # Add bookmark and history menus to nav_layout

        return nav_layout

    def _create_menus(self, parent_layout: QHBoxLayout):
        """Creates and adds bookmark and history menus to the given parent layout."""
        # Bookmarks menu
        bookmark_btn = QPushButton("Bookmarks")
        self.bookmark_menu = QMenu()
        self.update_bookmark_menu(self.bookmark_menu) # Populate initially
        bookmark_btn.setMenu(self.bookmark_menu)
        parent_layout.addWidget(bookmark_btn)

        add_bookmark_btn = QPushButton("Add Bookmark")
        add_bookmark_btn.clicked.connect(self.add_bookmark)
        parent_layout.addWidget(add_bookmark_btn)

        # History menu
        history_btn = QPushButton("History")
        self.history_menu = QMenu()
        self.update_history_menu(self.history_menu) # Populate initially
        history_btn.setMenu(self.history_menu)
        parent_layout.addWidget(history_btn)

    def _create_control_buttons_layout(self):
        """Creates the layout for control buttons."""
        controls_layout = QHBoxLayout()

        self.refresh_button = QPushButton("Refresh to Original IP")
        self.refresh_button.clicked.connect(self.refresh_to_original)
        controls_layout.addWidget(self.refresh_button)

        self.protocol_button = QPushButton() # Text set by update_protocol_button_state
        self.protocol_button.clicked.connect(self.toggle_protocol_and_reload)
        controls_layout.addWidget(self.protocol_button)
        self.update_protocol_button_state() # Set initial text

        self.monitor_button = QPushButton("Stop Redirect Monitor") # Initial text
        self.monitor_button.clicked.connect(self.toggle_monitor)
        controls_layout.addWidget(self.monitor_button)

        snapshot_btn = QPushButton("Save Page Snapshot")
        snapshot_btn.clicked.connect(self.save_snapshot)
        controls_layout.addWidget(snapshot_btn)

        switch_cred_btn = QPushButton("Switch Credential")
        switch_cred_btn.clicked.connect(self.switch_credential)
        controls_layout.addWidget(switch_cred_btn)

        return controls_layout

    def _create_status_bar(self):
        """Creates and configures the status bar."""
        self.status_bar = QStatusBar()
        self.network_status_label = QLabel("Network Status: Unknown")
        self.status_bar.addWidget(self.network_status_label)
        self.setStatusBar(self.status_bar)

    def init_ui(self):
        """Set up the browser UI by assembling components from helper methods."""
        self.setWindowTitle("Router Login")
        self.setGeometry(100, 100, 800, 600)

        # Create web view (must be created before navigation bar if nav bar connects to its signals)
        self.web_view = QWebEngineView()
        page = QWebEnginePage(self.profile, self.web_view)
        page.certificateError.connect(self.handle_certificate_error)
        self.web_view.setPage(page)
        self.web_view.loadFinished.connect(self.on_load_finished)
        self.web_view.urlChanged.connect(self.add_url_to_history) # For history menu

        # Create UI sections using helper methods
        navigation_bar_layout = self._create_navigation_bar()
        control_buttons_layout = self._create_control_buttons_layout()
        self._create_status_bar()

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.addLayout(navigation_bar_layout)
        main_layout.addLayout(control_buttons_layout)
        main_layout.addWidget(self.web_view) # Add web_view last

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

    def update_protocol_button_state(self):
        if self.current_protocol_is_https:
            self.protocol_button.setText("Switch to HTTP")
        else:
            self.protocol_button.setText("Switch to HTTPS")

    def toggle_protocol_and_reload(self):
        self.current_protocol_is_https = not self.current_protocol_is_https
        print(f"Manually switched protocol. Attempting {'HTTPS' if self.current_protocol_is_https else 'HTTP'}.")
        self.web_view.load(QUrl(self.build_url()))
        self.update_protocol_button_state()

    def on_load_finished(self, success):
        current_loaded_url = self.web_view.url()
        current_loaded_url_is_https = current_loaded_url.scheme().lower() == 'https'

        if success:
            self.current_protocol_is_https = current_loaded_url_is_https
            # Clear status bar on successful load, or show success message briefly
            self.status_bar.showMessage(f"Successfully loaded: {current_loaded_url.toString()}", 5000) # Brief success message
            print(f"Load successful for {current_loaded_url.toString()}. Applying credentials. Protocol is now {'HTTPS' if self.current_protocol_is_https else 'HTTP'}.")
            self.check_and_apply_credentials()
        else:
            # Display error in status bar
            self.status_bar.showMessage(f"Error: Failed to load URL: {current_loaded_url.toString()}", 10000)
            print(f"Load FAILED for URL: {current_loaded_url.toString()} (Browser's current_protocol_is_https: {self.current_protocol_is_https}, Actual scheme of failed URL: {'HTTPS' if current_loaded_url_is_https else 'HTTP'})")

        # Ensure URL bar is accurate even on failure or redirect
        self.url_bar.setText(current_loaded_url.toString())
        self.update_protocol_button_state()

    def handle_certificate_error(self, error_info):
        self.current_protocol_is_https = True
        self.update_protocol_button_state()
        reply = QMessageBox.warning(
            self,
            "Certificate Error",
            f"SSL certificate error for {error_info.url().toString()}:\n{error_info.errorDescription()}\n\nProceed anyway (unsafe)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            error_info.ignoreCertificateError()
            self.status_bar.showMessage(f"Proceeding with insecure connection to {error_info.url().toString()}", 7000)
        else:
            # User chose not to proceed. Update status bar.
            self.status_bar.showMessage(f"HTTPS connection to {error_info.url().toString()} cancelled due to certificate error.", 10000)
            QMessageBox.information(self, "HTTPS Connection Cancelled",
                                    "The insecure HTTPS connection was not established. "
                                    "The page load will likely fail. You can try HTTP.")
            # The on_load_finished(success=False) will follow, and its status message will overwrite the one above.
            # This is acceptable as it reflects the final state of the load attempt.

    def navigate_to_url(self):
        """Navigate to the URL in the URL bar."""
        url_text = self.url_bar.text()
        url = QUrl(url_text)
        if not url.scheme():
            url.setScheme("https" if self.current_protocol_is_https else "http")
            self.url_bar.setText(url.toString())
        self.web_view.load(url)

    def add_url_to_history(self, url):
        """Add current URL to history."""
        self.db.add_history(url.toString(), self.target_ip)
        if hasattr(self, 'history_menu'):
            self.update_history_menu(self.history_menu)

    def add_bookmark(self):
        """Add current URL as a bookmark."""
        name, ok = QInputDialog.getText(self, "Add Bookmark", "Bookmark name:")
        if ok and name:
            self.db.add_bookmark(name, self.web_view.url().toString(), self.target_ip)
            if hasattr(self, 'bookmark_menu'):
                self.update_bookmark_menu(self.bookmark_menu)

    def update_bookmark_menu(self, menu):
        """Update bookmarks menu."""
        menu.clear()
        bookmarks = self.db.get_bookmarks(self.target_ip)
        for name, url_str in bookmarks:
            action = QAction(name, self)
            action.triggered.connect(lambda checked=False, u=url_str: self.web_view.load(QUrl(u)))
            menu.addAction(action)

    def update_history_menu(self, menu):
        """Update history menu."""
        menu.clear()
        history = self.db.get_history(self.target_ip)
        for url_str, timestamp in history[:10]:
            action = QAction(f"{url_str} ({timestamp})", self)
            action.triggered.connect(lambda checked=False, u=url_str: self.web_view.load(QUrl(u)))
            menu.addAction(action)

    def load_credentials(self):
        """Load saved credentials from keyring."""
        service_name = f"RouterLogin_{self.machine_name}_{self.target_ip}"
        index = 0
        self.credentials = []
        while True:
            username = keyring.get_password(f"{service_name}_{index}", "username")
            if not username:
                break
            password = keyring.get_password(f"{service_name}_{index}", "password")
            if password is None:
                password = ""
            self.credentials.append((username, password))
            index += 1

    def check_and_apply_credentials(self):
        """Check for saved credentials and suggest login."""
        if self.credentials:
            username, password = self.credentials[self.current_credential_index]
            self.apply_credentials(username, password)
        else:
            self.prompt_save_credentials()

    def apply_credentials(self, username, password):
        """Apply credentials to login form."""
        js = f"""
        let userField = document.querySelector('input[type="text"], input[name*="user"], input[id*="user"]');
        let passField = document.querySelector('input[type="password"], input[name*="pass"], input[id*="pass"]');
        if (userField && passField) {{
            userField.value = "{username}";
            passField.value = "{password}";
        }}
        """
        page = self.web_view.page()
        if page is not None:
            page.runJavaScript(js)
        else:
            print("Warning: Web page is not available to run JavaScript for credentials.")

    def prompt_save_credentials(self):
        """Prompt to save login credentials."""
        js = """
        (function() {{
            let userField = document.querySelector('input[type="text"]:not([readonly]), input[name*="user"]:not([readonly]), input[id*="user"]:not([readonly])');
            let passField = document.querySelector('input[type="password"]:not([readonly]), input[name*="pass"]:not([readonly]), input[id*="pass"]:not([readonly])');
            if (userField && userField.offsetWidth > 0 && userField.offsetHeight > 0 &&
                passField && passField.offsetWidth > 0 && passField.offsetHeight > 0) {{
                 return [userField.value, passField.value];
            }}
            return ['', ''];
        }})();
        """
        # Check if page exists before calling runJavaScript
        page = self.web_view.page()
        if page:
            page.runJavaScript(js, lambda result: self.save_credentials(result))
        else:
            print(f"Warning: Web page not available for {self.target_ip} to run JavaScript for credentials.")

    def save_credentials(self, result):
        """Save credentials to keyring."""
        username, password = (
            result if isinstance(result, list) and len(result) == 2 else ("", "")
        )
        if username and password:
            reply = QMessageBox.question(
                self,
                "Save Credentials",
                f"Save login for {self.target_ip}?\nUsername: {username}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                service_name = f"RouterLogin_{self.machine_name}_{self.target_ip}"
                index = len(self.credentials)
                keyring.set_password(f"{service_name}_{index}", "username", username)
                keyring.set_password(f"{service_name}_{index}", "password", password)
                self.credentials.append((username, password))
                print(f"Saved credentials for {self.target_ip}")
                self.status_bar.showMessage(f"Credentials for {username} saved.", 5000)
    def refresh_to_original(self):
        """Refresh the browser to the original IP."""
        url_to_load = self.build_url()
        # Ensure URL bar is updated before loading, in case build_url changed protocol
        if self.url_bar:
            self.url_bar.setText(url_to_load)
        self.web_view.load(QUrl(url_to_load))
        print(f"Refreshed to {url_to_load}")
        self.status_bar.showMessage(f"Reloading {url_to_load}", 3000)

    def toggle_monitor(self):
        """Toggle the redirect monitor."""
        self.monitor_active = not self.monitor_active
        self.monitor_button.setText(
            "Start Redirect Monitor"
            if not self.monitor_active
            else "Stop Redirect Monitor"
        )
        if self.monitor_active and hasattr(self, 'timer'):
            self.timer.start(self.refresh_interval)
        elif hasattr(self, 'timer'):
            self.timer.stop()
        print(f"Redirect monitor {'started' if self.monitor_active else 'stopped'}")

    def start_url_monitor(self):
        """Monitor for redirects and refresh if needed."""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_url)
        if self.monitor_active:
            self.timer.start(self.refresh_interval)

    def check_url(self):
        """Check if the current URL has redirected from the target IP."""
        if not self.monitor_active:
            return
        current_url_host = self.web_view.url().host()
        if current_url_host and current_url_host != self.target_ip:
            original_url_to_refresh_to = self.build_url()
            print(
                f"Detected navigation away from {self.target_ip} to {current_url_host}. Refreshing to {original_url_to_refresh_to}"
            )
            self.status_bar.showMessage(f"Redirect detected. Refreshing to {self.target_ip}", 5000)
            self.refresh_to_original()


    def save_snapshot(self):
        """Save a screenshot of the current page."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not os.path.exists(self.cookie_dir):
            os.makedirs(self.cookie_dir, exist_ok=True)

        snapshot_path = os.path.join(self.cookie_dir, f"snapshot_{self.target_ip.replace('.', '_')}_{timestamp}.png")
        pixmap = QPixmap(self.web_view.size())
        self.web_view.render(pixmap)
        if pixmap.save(snapshot_path):
            QMessageBox.information(self, "Success", f"Snapshot saved to {snapshot_path}")
            self.status_bar.showMessage(f"Snapshot saved: {snapshot_path}", 5000)
        else:
            QMessageBox.critical(self, "Error", f"Failed to save snapshot to {snapshot_path}")
            self.status_bar.showMessage("Failed to save snapshot.", 5000)


    def switch_credential(self):
        """Cycle through saved credentials."""
        if not self.credentials:
            QMessageBox.information(self, "No Credentials", "No saved credentials to switch. Attempting to detect and save new ones.")
            self.prompt_save_credentials()
            return
        self.current_credential_index = (self.current_credential_index + 1) % len(self.credentials)
        username, password = self.credentials[self.current_credential_index]
        self.apply_credentials(username, password)
        self.status_bar.showMessage(f"Switched to credential for: {username}", 5000)

    def update_network_status(self):
        """Update the network status in the status bar."""
        active_adapters_tuples, msg = list_adapters() # list_adapters returns list of tuples
        if msg:
            self.network_status_label.setText(f"Network Status: Error listing adapters - {msg}")
            return

        status_text = "Network Status: Unknown or No Active Configured Connection"
        if active_adapters_tuples:
            for adapter_short_name, adapter_detailed_name in active_adapters_tuples:
                # Use adapter_short_name for get_current_adapter_config
                config, config_msg = get_current_adapter_config(adapter_short_name)
                if config_msg and not config:
                    print(f"Could not get config for {adapter_short_name} ({adapter_detailed_name}): {config_msg}")
                    continue
                if config and config.get('ip_address') and config.get('gateway'):
                    # Display adapter_detailed_name for user-friendliness
                    status_text = f"Adapter: {adapter_detailed_name} | IP: {config.get('ip_address', 'N/A')} | Gateway: {config.get('gateway', 'N/A')}"
                    break
        self.network_status_label.setText(status_text)


    def show(self):
        """Show the browser window."""
        super().show()
        self.activateWindow()
        self.raise_()


def open_router_page(router_ip, router_port=None, refresh_interval=5, protocol="http"):
    """Open the router login page in a custom browser."""
    if not QApplication.instance():
        QApplication(sys.argv)

    if not router_ip: # Check only for router_ip
        QMessageBox.critical(None, "Error", "No router IP provided.")
        print("Error: No router IP provided.")
        return None
    try:
        browser = RouterBrowser(router_ip, router_port, refresh_interval * 1000, preferred_protocol=protocol)
        browser.show()
        return browser
    except ValueError as e:
        QMessageBox.critical(None, "Initialization Error", str(e))
        return None
    except Exception as e:
        QMessageBox.critical(None, "Router Browser Error", f"Could not open router browser: {e}")
        return None
