import sys
import os
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QPushButton,
    QLineEdit, QInputDialog, QMessageBox, QMenu, QComboBox, QLabel, QStatusBar
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile, QWebEnginePage
from PyQt6.QtCore import QUrl, QTimer, QDir
from PyQt6.QtGui import QPixmap
from urllib.parse import urlparse
from PyQt6.QtGui import QAction # Keep QAction
import socket # Import the socket module
import keyring
from db_manager import DBManager
from network_manager import get_current_adapter_config
from datetime import datetime


class RouterBrowser(QMainWindow):

    """Custom browser for router login with navigation, credentials, and HTTPS support."""

    def __init__(self, router_ip, gateway, router_port=None, refresh_interval=5000, preferred_protocol="http"):
        super().__init__()
        self.target_ip = router_ip or gateway
        if not self.target_ip:
            raise ValueError("Router IP or gateway must be provided.")
        self.router_port = router_port
        self.current_protocol_is_https = (preferred_protocol.lower() == "https")
        self.refresh_interval = refresh_interval
        self.monitor_active = True
        self.db = DBManager()
        self.current_credential_index = 0
        try:
            self.machine_name = socket.gethostname()
        except Exception:
            self.machine_name = "unknown_machine" # Fallback
        self.credentials = []

        # Set up cookie storage
        self.cookie_dir = os.path.join(
            os.getcwd(), "cookies", self.target_ip.replace(".", "_")
        )
        QDir().mkpath(self.cookie_dir)

        self.profile = QWebEngineProfile(f"Router_{self.target_ip}", self)
        self.profile.setPersistentStoragePath(self.cookie_dir)
        self.profile.settings().setAttribute(
            QWebEngineSettings.WebAttribute.ShowScrollBars, True
        )

        self.init_ui()
        self.load_credentials()
        self.web_view.load(QUrl(self.build_url())) # Initial load (respecting preferred_protocol)
        self.start_url_monitor()
        self.update_network_status()

    def build_url(self, force_https=None):
        """Build the target URL with protocol and port."""
        use_https_for_build = self.current_protocol_is_https
        if force_https is not None:
            use_https_for_build = force_https

        protocol = "https" if use_https_for_build else "http"
        if self.router_port:
            return f"{protocol}://{self.target_ip}:{self.router_port}"
        return f"{protocol}://{self.target_ip}"

    def init_ui(self):
        """Set up the browser UI."""
        self.setWindowTitle("Router Login")
        self.setGeometry(100, 100, 800, 600)

        # Create web view
        self.web_view = QWebEngineView()
        page = QWebEnginePage(self.profile, self.web_view)
        page.certificateError.connect(self.handle_certificate_error) # Connect signal
        self.web_view.setPage(page)
        self.web_view.loadFinished.connect(self.on_load_finished)
        self.web_view.urlChanged.connect(self.add_url_to_history) # For history
        # URL bar is updated by a separate connection below

        # Navigation bar
        nav_layout = QHBoxLayout()
        back_button = QPushButton("Back")
        back_button.clicked.connect(self.web_view.back)
        forward_button = QPushButton("Forward")
        forward_button.clicked.connect(self.web_view.forward)
        reload_button = QPushButton("Reload")
        reload_button.clicked.connect(self.web_view.reload)
        self.url_bar = QLineEdit()
        self.url_bar.setText(self.build_url()) # Use build_url() to get the initial URL
        self.url_bar.returnPressed.connect(self.navigate_to_url)
        self.web_view.urlChanged.connect(
            lambda url: self.url_bar.setText(url.toString())
        )
        nav_layout.addWidget(back_button)
        nav_layout.addWidget(forward_button)
        nav_layout.addWidget(reload_button)
        nav_layout.addWidget(self.url_bar)

        # Bookmarks menu
        bookmark_btn = QPushButton("Bookmarks")
        self.bookmark_menu = QMenu()
        self.update_bookmark_menu(self.bookmark_menu)
        bookmark_btn.setMenu(self.bookmark_menu)
        nav_layout.addWidget(bookmark_btn)
        add_bookmark_btn = QPushButton("Add Bookmark")
        add_bookmark_btn.clicked.connect(self.add_bookmark)
        nav_layout.addWidget(add_bookmark_btn)

        # History menu
        history_btn = QPushButton("History")
        self.history_menu = QMenu()
        self.update_history_menu(self.history_menu)
        history_btn.setMenu(self.history_menu)
        nav_layout.addWidget(history_btn)

        # Control buttons
        self.refresh_button = QPushButton("Refresh to Original IP")
        self.refresh_button.clicked.connect(self.refresh_to_original)
        self.protocol_button = QPushButton("Switch to HTTPS") # Initial text
        self.protocol_button.clicked.connect(self.toggle_protocol_and_reload)
        self.monitor_button = QPushButton("Stop Redirect Monitor")
        self.monitor_button.clicked.connect(self.toggle_monitor)
        snapshot_btn = QPushButton("Save Page Snapshot")
        snapshot_btn.clicked.connect(self.save_snapshot)
        switch_cred_btn = QPushButton("Switch Credential")
        switch_cred_btn.clicked.connect(self.switch_credential)
        self.update_protocol_button_state()

        # Control buttons layout
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.refresh_button)
        controls_layout.addWidget(self.protocol_button)
        controls_layout.addWidget(self.monitor_button)
        controls_layout.addWidget(snapshot_btn)
        controls_layout.addWidget(switch_cred_btn)

        # Layout
        layout = QVBoxLayout()
        layout.addLayout(nav_layout)
        layout.addLayout(controls_layout) # Add the new horizontal layout for control buttons
        layout.addWidget(self.web_view)

        # Status bar
        self.status_bar = QStatusBar()
        self.network_status_label = QLabel("Network Status: Unknown")
        self.status_bar.addWidget(self.network_status_label)
        self.setStatusBar(self.status_bar)

        container = QWidget()
        container.setLayout(layout)
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

        if success: # Page loaded successfully
            # Sync internal browser state (current_protocol_is_https)
            # with the protocol of the URL that actually loaded.
            # This handles cases where an HTTP URL redirected to HTTPS.
            self.current_protocol_is_https = current_loaded_url_is_https

            print(f"Load successful for {current_loaded_url.toString()}. Applying credentials. Protocol is now {'HTTPS' if self.current_protocol_is_https else 'HTTP'}.")
            self.check_and_apply_credentials()

        else:  # Load failed
            print(f"Load FAILED for URL: {current_loaded_url.toString()} (Browser's current_protocol_is_https: {self.current_protocol_is_https}, Actual scheme of failed URL: {'HTTPS' if current_loaded_url_is_https else 'HTTP'})")

            # Warnings removed as per request. Console logs above provide failure information.
            # You could add a status bar message here if desired:
            # self.status_bar.showMessage(f"Failed to load: {current_loaded_url.toString()}", 10000)
        self.url_bar.setText(current_loaded_url.toString())  # Ensure URL bar is accurate
        self.update_protocol_button_state() # Reflects any change in self.current_protocol_is_https

    def handle_certificate_error(self, error_info): # error_info is QWebEngineCertificateError
        """Handle HTTPS certificate errors."""
        # This error means an HTTPS connection was attempted.
        self.current_protocol_is_https = True # Reflect that HTTPS was the goal
        self.update_protocol_button_state() # Ensure button says "Switch to HTTP"
        reply = QMessageBox.warning(
            self,
            "Certificate Error",
            f"SSL certificate error for {error_info.url().toString()}:\n{error_info.errorDescription()}\n\nProceed anyway (unsafe)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No # Default to No
        )
        if reply == QMessageBox.StandardButton.Yes:
            error_info.ignoreCertificateError() # Tell QtWebEngine to ignore this error and proceed
        else:
            # User chose not to proceed. The page load will likely fail.
            # on_load_finished will be called with success=False.
            QMessageBox.information(self, "HTTPS Connection Cancelled",
                                    "The insecure HTTPS connection was not established. "
                                    "The page load will likely fail. You can try HTTP.")
        # This slot is void, we don't return True/False.

    def navigate_to_url(self):
        """Navigate to the URL in the URL bar."""
        url = QUrl(self.url_bar.text())
        if not url.scheme():
            url.setScheme("https" if self.current_protocol_is_https else "http")
        self.web_view.load(url)

    def add_url_to_history(self, url):
        """Add current URL to history."""
        self.db.add_history(url.toString(), self.target_ip)
        self.update_history_menu(self.history_menu)

    def add_bookmark(self):
        """Add current URL as a bookmark."""
        name, ok = QInputDialog.getText(self, "Add Bookmark", "Bookmark name:")
        if ok and name:
            self.db.add_bookmark(name, self.web_view.url().toString(), self.target_ip)
            self.update_bookmark_menu(self.bookmark_menu)

    def update_bookmark_menu(self, menu):
        """Update bookmarks menu."""
        menu.clear()
        bookmarks = self.db.get_bookmarks(self.target_ip)
        for name, url in bookmarks:
            action = QAction(name, self)
            action.triggered.connect(lambda: self.web_view.load(QUrl(url)))
            menu.addAction(action)

    def update_history_menu(self, menu):
        """Update history menu."""
        menu.clear()
        history = self.db.get_history(self.target_ip)
        for url, timestamp in history[:10]:
            action = QAction(f"{url} ({timestamp})", self)
            action.triggered.connect(lambda: self.web_view.load(QUrl(url)))
            menu.addAction(action)

    def load_credentials(self):
        """Load saved credentials from keyring."""
        service_name = f"RouterLogin_{self.machine_name}_{self.target_ip}"
        index = 0
        while True:
            username = keyring.get_password(f"{service_name}_{index}", "username")
            if not username:
                break
            password = keyring.get_password(f"{service_name}_{index}", "password")
            self.credentials.append((username, password))
            index += 1

    def check_and_apply_credentials(self):
        """Check for saved credentials and suggest login."""
        if self.credentials:
            if self.credentials: # Check if list is not empty
                username, password = self.credentials[self.current_credential_index]
                self.apply_credentials(username, password)
        else:
            self.prompt_save_credentials()

    def apply_credentials(self, username, password):
        """Apply credentials to login form."""
        js = f"""
        let userField = document.querySelector('input[type="text"], input[name*="user"]');
        let passField = document.querySelector('input[type="password"]');
        if (userField && passField) {{
            userField.value = "{username}";
            passField.value = "{password}";
        }}
        """
        self.web_view.page().runJavaScript(js)

    def prompt_save_credentials(self):
        """Prompt to save login credentials."""
        js = """
        let userField = document.querySelector('input[type="text"], input[name*="user"]');
        let passField = document.querySelector('input[type="password"]');
        [userField ? userField.value : '', passField ? passField.value : ''];
        """
        self.web_view.page().runJavaScript(
            js, lambda result: self.save_credentials(result)
        )

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

    def refresh_to_original(self):
        """Refresh the browser to the original IP."""
        url_to_load = self.build_url() # Uses current_protocol_is_https
        self.web_view.load(QUrl(url_to_load))
        print(f"Refreshed to {url_to_load}")

    def toggle_monitor(self):
        """Toggle the redirect monitor."""
        self.monitor_active = not self.monitor_active
        self.monitor_button.setText(
            "Start Redirect Monitor"
            if not self.monitor_active
            else "Stop Redirect Monitor"
        )
        if self.monitor_active:
            self.timer.start(self.refresh_interval)
        else:
            self.timer.stop()
        print(f"Redirect monitor {'started' if self.monitor_active else 'stopped'}")

    def start_url_monitor(self):
        """Monitor for redirects and refresh if needed."""
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_url)
        if self.monitor_active:
            self.timer.start(self.refresh_interval)

    def check_url(self):
        """Check if the current URL has redirected to a local domain."""
        if not self.monitor_active:
            return
        current_url = self.web_view.url().toString()
        parsed = urlparse(current_url)
        redirect_domains = [".com", ".net", ".local", ".lan", ".io"]
        if self.target_ip not in parsed.netloc and any(
            domain in parsed.netloc for domain in redirect_domains
        ):
            original_url_to_refresh_to = self.build_url()
            print(
                f"Detected redirect to {current_url}. Refreshing to {original_url_to_refresh_to}"
            )
            self.refresh_to_original()

    def save_snapshot(self):
        """Save a screenshot of the current page."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_path = os.path.join(self.cookie_dir, f"snapshot_{timestamp}.png")
        pixmap = QPixmap(self.web_view.size())
        self.web_view.render(pixmap)
        pixmap.save(snapshot_path)
        QMessageBox.information(self, "Success", f"Snapshot saved to {snapshot_path}")

    def switch_credential(self):
        """Cycle through saved credentials."""
        if not self.credentials:
            self.prompt_save_credentials()
            return
        self.current_credential_index = (self.current_credential_index + 1) % len(self.credentials)
        username, password = self.credentials[self.current_credential_index]
        self.apply_credentials(username, password)
        self.status_bar.showMessage(f"Switched to credential: {username}", 5000)

    def update_network_status(self):
        """Update the network status in the status bar."""
        # Import list_adapters here or ensure it's available in the class scope if imported at module level
        from network_manager import list_adapters # Assuming it's not already a class member or global
        active_adapters = list_adapters()
        status_text = "Network Status: Unknown or No Active Connection"

        for adapter_name in active_adapters:
            config = get_current_adapter_config(adapter_name)
            # Check if the adapter has a valid IP and gateway
            if config and config.get('ip_address') and config.get('gateway'):
                status_text = f"Adapter: {adapter_name} | IP: {config.get('ip_address', 'N/A')} | Gateway: {config.get('gateway', 'N/A')}"
                break # Display info for the first active, configured adapter
        self.network_status_label.setText(status_text)

    def show(self):
        """Show the browser window."""
        super().show()


def open_router_page(router_ip, gateway, router_port=None, refresh_interval=5, protocol="http"):
    """Open the router login page in a custom browser."""
    if not router_ip and not gateway:
        print("Error: No router IP or gateway provided.")
        return None
    try:
        browser = RouterBrowser(router_ip, gateway, router_port, refresh_interval * 1000, preferred_protocol=protocol)
        browser.show()
        return browser
    except ValueError as e:
        QMessageBox.critical(None, "Initialization Error", str(e))
        return None
