import os
import sqlite3
from cryptography.fernet import Fernet, InvalidToken
import base64
import json # 1. Import json module

DB_FILE = "network_configs.db"
DB_DIR = os.path.dirname(os.path.abspath(DB_FILE))
if not os.path.exists(DB_DIR) and DB_DIR != "":
    os.makedirs(DB_DIR, exist_ok=True)
KEY_FILE = os.path.join(DB_DIR, "network_config_encryption.key")


class EncryptionKeyError(Exception):
    """Custom exception for errors related to encryption key handling."""
    pass

class DBManager:
    """Manages SQLite database for network configurations, bookmarks, history, and Wi-Fi profiles."""

    def __init__(self):
        self.db_file = DB_FILE
        self._fernet = self._get_fernet()
        self.init_db()

    def _get_encryption_key(self) -> bytes:
        """
        Retrieves the encryption key from KEY_FILE or generates and stores a new one.
        Returns the key as bytes.
        Raises EncryptionKeyError if key cannot be read or generated/written.
        """
        try:
            if os.path.exists(KEY_FILE):
                with open(KEY_FILE, "rb") as f:
                    key = f.read()
                if not key:
                    raise EncryptionKeyError(f"Encryption key file '{KEY_FILE}' is empty.")
                return key
            else:
                key = Fernet.generate_key()
                with open(KEY_FILE, "wb") as f:
                    f.write(key)
                return key
        except IOError as e:
            raise EncryptionKeyError(f"IOError handling encryption key file '{KEY_FILE}': {e}")
        except Exception as e:
            raise EncryptionKeyError(f"Unexpected error with encryption key file '{KEY_FILE}': {e}")

    def _get_fernet(self) -> Fernet:
        """
        Initializes and returns a Fernet object for encryption/decryption.
        Raises EncryptionKeyError if the key cannot be obtained.
        """
        key = self._get_encryption_key()
        return Fernet(key)


    def init_db(self):
        """Initialize SQLite database and create tables."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS configs (
                name TEXT PRIMARY KEY,
                adapter_name TEXT,
                ip_address TEXT,
                subnet_mask TEXT,
                gateway TEXT,
                dns_primary TEXT,
                dns_secondary TEXT,
                router_ip TEXT,
                router_port TEXT,
                open_router BOOLEAN,
                router_protocol TEXT DEFAULT 'http'
            )
        """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                url TEXT,
                router_ip TEXT
            )
        """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                router_ip TEXT
            )
        """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS wifi_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_name TEXT,
                ssid TEXT,
                password TEXT,
                auth_type TEXT,
                FOREIGN KEY (config_name) REFERENCES configs(name) ON DELETE CASCADE
            )
        """
        )
        conn.commit()
        conn.close()

    def load_configs(self):
        """Load all network configurations."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM configs")
        rows = cursor.fetchall()
        configs = {"networks": {}}
        for row in rows:
            configs["networks"][row[0]] = {
                "adapter_name": row[1],
                "ip_address": row[2],
                "subnet_mask": row[3],
                "gateway": row[4],
                "dns_primary": row[5],
                "dns_secondary": row[6],
                "router_ip": row[7],
                "router_port": row[8],
                "open_router": bool(row[9]),
                "router_protocol": row[10] if len(row) > 10 and row[10] else 'http',
            }
        conn.close()
        return configs

    def save_config(self, config_name, config_data): # Renamed config to config_data for clarity
        """Save or update a configuration. Returns (bool, str) for success/failure."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT OR REPLACE INTO configs
                (name, adapter_name, ip_address, subnet_mask, gateway, dns_primary, dns_secondary, router_ip, router_port, open_router, router_protocol)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    config_name,
                    config_data["adapter_name"],
                    config_data["ip_address"],
                    config_data["subnet_mask"],
                    config_data["gateway"],
                    config_data["dns_primary"],
                    config_data["dns_secondary"],
                    config_data["router_ip"],
                    config_data["router_port"],
                    int(config_data["open_router"]),
                    config_data.get("router_protocol", "http"),
                ),
            )
            conn.commit()
            return True, f"Network configuration '{config_name}' saved successfully."
        except sqlite3.Error as e:
            print(f"Database error saving network configuration '{config_name}': {e}")
            return False, f"Database error saving network configuration '{config_name}': {e}"
        finally:
            conn.close()


    def delete_config(self, config_name):
        """Delete a configuration and associated Wi-Fi profiles."""
        conn = sqlite3.connect(self.db_file)
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM configs WHERE name = ?", (config_name,))
        conn.commit()
        conn.close()

    def add_bookmark(self, name, url, router_ip):
        """Add a bookmark."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO bookmarks (name, url, router_ip) VALUES (?, ?, ?)",
            (name, url, router_ip),
        )
        conn.commit()
        conn.close()

    def get_bookmarks(self, router_ip):
        """Get bookmarks for a router IP."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, url FROM bookmarks WHERE router_ip = ?", (router_ip,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [(row[0], row[1]) for row in rows]

    def add_history(self, url, router_ip):
        """Add a URL to history."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO history (url, router_ip) VALUES (?, ?)", (url, router_ip)
        )
        conn.commit()
        conn.close()

    def get_history(self, router_ip):
        """Get history for a router IP."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT url, timestamp FROM history WHERE router_ip = ? ORDER BY timestamp DESC",
            (router_ip,),
        )
        rows = cursor.fetchall()
        conn.close()
        return [(row[0], row[1]) for row in rows]

    def save_wifi_profile(self, config_name, ssid, password, auth_type):
        """Save a Wi-Fi profile associated with a config, encrypting the password."""
        if not self._fernet:
            return False, "Encryption service not initialized. Wi-Fi profile not saved."

        try:
            encrypted_password_bytes = self._fernet.encrypt(password.encode('utf-8'))
            encrypted_password_b64_str = base64.urlsafe_b64encode(encrypted_password_bytes).decode('utf-8')
        except Exception as e:
            print(f"Error encrypting password for SSID '{ssid}': {e}")
            return False, f"Failed to encrypt password for SSID '{ssid}': {e}"

        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT OR REPLACE INTO wifi_profiles (config_name, ssid, password, auth_type)
                VALUES (?, ?, ?, ?)
            """, # Using INSERT OR REPLACE for simplicity during import
                (config_name, ssid, encrypted_password_b64_str, auth_type),
            )
            conn.commit()
            return True, f"Wi-Fi profile for SSID '{ssid}' (config: '{config_name}') saved."
        except sqlite3.Error as e:
            print(f"Database error saving Wi-Fi profile for SSID '{ssid}': {e}")
            return False, f"Database error for SSID '{ssid}': {e}"
        finally:
            conn.close()

    # 2. Modify get_wifi_profiles
    def get_wifi_profiles(self, config_name=None, decrypt_passwords=True):
        """
        Get Wi-Fi profiles, optionally filtered by config name.
        Passwords can be returned decrypted or as raw encrypted strings.
        Returns a tuple: (list_of_profiles, error_message_or_none)
        """
        if not self._fernet and decrypt_passwords: # Only critical if decryption is requested
            return [], "Encryption service not available. Could not retrieve/decrypt Wi-Fi profiles."

        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        query = "SELECT config_name, ssid, password, auth_type FROM wifi_profiles"
        params = ()
        if config_name:
            query += " WHERE config_name = ?"
            params = (config_name,)

        try:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Database error retrieving Wi-Fi profiles: {e}")
            return [], f"Database error: {e}"
        finally:
            conn.close()

        processed_profiles = []
        for profile_config_name, ssid, stored_password_str, auth_type in rows:
            if decrypt_passwords:
                try:
                    if stored_password_str:
                        encrypted_password_bytes = base64.urlsafe_b64decode(stored_password_str.encode('utf-8'))
                        decrypted_password_bytes = self._fernet.decrypt(encrypted_password_bytes)
                        plaintext_password = decrypted_password_bytes.decode('utf-8')
                    else:
                        plaintext_password = ""
                except InvalidToken:
                    print(f"Error: Failed to decrypt password for SSID {ssid} (config: {profile_config_name}). Key may be incorrect or data corrupt.")
                    plaintext_password = "DECRYPTION_FAILED"
                except Exception as e:
                    print(f"An unexpected error occurred during password decryption for SSID {ssid} (config: {profile_config_name}): {e}")
                    plaintext_password = "DECRYPTION_ERROR"
                processed_profiles.append((profile_config_name, ssid, plaintext_password, auth_type))
            else: # Do not decrypt, return raw stored password (encrypted, base64 encoded string)
                processed_profiles.append((profile_config_name, ssid, stored_password_str, auth_type))

        return processed_profiles, None


    def delete_wifi_profile(self, config_name, ssid):
        """Delete a specific Wi-Fi profile."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM wifi_profiles WHERE config_name = ? AND ssid = ?",
                (config_name, ssid),
            )
            conn.commit()
            return True, "Wi-Fi profile deleted successfully."
        except sqlite3.Error as e:
            print(f"Database error deleting Wi-Fi profile: {e}")
            return False, f"Database error: {e}"
        finally:
            conn.close()

    # 3. Implement export_all_data
    def export_all_data(self) -> tuple[str | None, str | None]:
        """Exports all network and Wi-Fi configurations to a JSON string."""
        try:
            configs_data = self.load_configs() # This is already a dict like {"networks": {...}}
            # Get Wi-Fi profiles with passwords encrypted (as stored)
            wifi_profiles_data_list, wifi_error = self.get_wifi_profiles(decrypt_passwords=False)

            if wifi_error:
                return None, f"Error fetching Wi-Fi profiles for export: {wifi_error}"

            export_data = {
                "network_configurations": configs_data.get("networks", {}),
                # wifi_profiles_data_list is already a list of tuples
                "wifi_profiles": wifi_profiles_data_list
            }
            json_string = json.dumps(export_data, indent=4)
            return json_string, None
        except Exception as e:
            print(f"Error during data export: {e}")
            return None, f"Failed to export data: {e}"

    # 4. Implement import_all_data
    def import_all_data(self, json_string: str) -> tuple[bool, str]:
        """Imports network and Wi-Fi configurations from a JSON string."""
        imported_net_configs_count = 0
        updated_net_configs_count = 0
        failed_net_configs_count = 0
        net_config_errors = []

        imported_wifi_profiles_count = 0
        updated_wifi_profiles_count = 0 # Assuming save_wifi_profile uses INSERT OR REPLACE
        failed_wifi_profiles_count = 0
        problematic_wifi_decryption = [] # List of (config_name, ssid) for decryption issues
        wifi_profile_errors = []

        try:
            data = json.loads(json_string)
        except json.JSONDecodeError as e:
            return False, f"Import failed: Invalid JSON format. {e}"

        if not isinstance(data, dict) or \
           "network_configurations" not in data or \
           "wifi_profiles" not in data:
            return False, "Import failed: JSON structure is invalid. Missing required keys."

        # Import Network Configurations
        network_configs_to_import = data.get("network_configurations", {})
        if not isinstance(network_configs_to_import, dict):
             return False, "Import failed: 'network_configurations' must be a dictionary."

        for name, config_data in network_configs_to_import.items():
            # Basic validation of config_data structure could be added here if needed
            # For now, assuming save_config handles missing keys gracefully or we trust the export format
            success, msg = self.save_config(name, config_data) # save_config uses INSERT OR REPLACE
            if success:
                # It's hard to distinguish between new import vs update with INSERT OR REPLACE
                # For simplicity, let's count all successful saves as "processed"
                imported_net_configs_count +=1
            else:
                failed_net_configs_count += 1
                net_config_errors.append(f"'{name}': {msg}")

        # Import Wi-Fi Profiles
        wifi_profiles_to_import = data.get("wifi_profiles", [])
        if not isinstance(wifi_profiles_to_import, list):
            return False, "Import failed: 'wifi_profiles' must be a list."

        if not self._fernet:
            return False, "Import failed: Encryption service not available for Wi-Fi password handling."

        for profile_data in wifi_profiles_to_import:
            if not (isinstance(profile_data, (list, tuple)) and len(profile_data) == 4):
                failed_wifi_profiles_count += 1
                wifi_profile_errors.append(f"Invalid Wi-Fi profile data format: {profile_data}")
                continue

            config_name, ssid, encrypted_password_b64, auth_type = profile_data

            plaintext_password = ""
            decryption_ok = False
            if encrypted_password_b64: # Only try to decrypt if there's a password string
                try:
                    encrypted_bytes = base64.urlsafe_b64decode(encrypted_password_b64.encode('utf-8'))
                    decrypted_bytes = self._fernet.decrypt(encrypted_bytes)
                    plaintext_password = decrypted_bytes.decode('utf-8')
                    decryption_ok = True
                except (InvalidToken, base64.binascii.Error, Exception) as e: # Catch specific and general decryption errors
                    problematic_wifi_decryption.append(f"'{ssid}' (Config: '{config_name}', Error: {type(e).__name__})")
                    print(f"Decryption failed for Wi-Fi profile SSID '{ssid}' under config '{config_name}': {e}")
            elif auth_type == "open": # If open auth and no password, that's fine
                decryption_ok = True # Effectively, no password needed
            else: # Non-open auth but no password provided in export (should not happen if exported correctly)
                problematic_wifi_decryption.append(f"'{ssid}' (Config: '{config_name}', Error: Missing password for non-open auth)")


            if decryption_ok:
                success, msg = self.save_wifi_profile(config_name, ssid, plaintext_password, auth_type)
                if success:
                    imported_wifi_profiles_count += 1
                else:
                    failed_wifi_profiles_count += 1
                    wifi_profile_errors.append(f"'{ssid}' (Config: '{config_name}'): {msg}")
            # If not decryption_ok, it's already added to problematic_wifi_decryption

        # Compile Summary Message
        summary_parts = [f"Import process finished."]
        summary_parts.append(f"Network Configurations: Processed {imported_net_configs_count}, Failed {failed_net_configs_count}.")
        if net_config_errors:
            summary_parts.append("Network Config Errors:\n- " + "\n- ".join(net_config_errors))

        summary_parts.append(f"Wi-Fi Profiles: Processed {imported_wifi_profiles_count}, Failed to Save {failed_wifi_profiles_count}, Failed to Decrypt {len(problematic_wifi_decryption)}.")
        if wifi_profile_errors:
            summary_parts.append("Wi-Fi Save Errors:\n- " + "\n- ".join(wifi_profile_errors))
        if problematic_wifi_decryption:
            summary_parts.append("Wi-Fi Profiles with Decryption Issues (original encrypted password not imported):\n- " + "\n- ".join(problematic_wifi_decryption))
            summary_parts.append("These profiles may need their passwords re-entered manually if they were encrypted with a different key.")

        overall_success = (failed_net_configs_count == 0 and failed_wifi_profiles_count == 0)
        return overall_success, "\n".join(summary_parts)
