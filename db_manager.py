import os
import sqlite3

DB_FILE = "network_configs.db"


class DBManager:
    """Manages SQLite database for network configurations, bookmarks, history, and Wi-Fi profiles."""

    def __init__(self):
        self.db_file = DB_FILE
        self.init_db()

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
                FOREIGN KEY (config_name) REFERENCES configs(name)
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
                "router_protocol": row[10] if len(row) > 10 and row[10] else 'http', # Handle existing rows
            }
        conn.close()
        return configs

    def save_config(self, config_name, config):
        """Save or update a configuration."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO configs
            (name, adapter_name, ip_address, subnet_mask, gateway, dns_primary, dns_secondary, router_ip, router_port, open_router, router_protocol)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                config_name,
                config["adapter_name"],
                config["ip_address"],
                config["subnet_mask"],
                config["gateway"],
                config["dns_primary"],
                config["dns_secondary"],
                config["router_ip"],
                config["router_port"],
                int(config["open_router"]),
                config.get("router_protocol", "http"),
            ),
        )
        conn.commit()
        conn.close()

    def delete_config(self, config_name):
        """Delete a configuration and associated Wi-Fi profiles."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM wifi_profiles WHERE config_name = ?", (config_name,)
        )
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
        """Save a Wi-Fi profile associated with a config."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO wifi_profiles (config_name, ssid, password, auth_type)
            VALUES (?, ?, ?, ?)
        """,
            (config_name, ssid, password, auth_type),
        )
        conn.commit()
        conn.close()

    def get_wifi_profiles(self, config_name=None):
        """Get Wi-Fi profiles, optionally filtered by config name."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        if config_name:
            cursor.execute(
                "SELECT ssid, password, auth_type FROM wifi_profiles WHERE config_name = ?",
                (config_name,),
            )
        else:
            cursor.execute(
                "SELECT config_name, ssid, password, auth_type FROM wifi_profiles"
            )
        rows = cursor.fetchall()
        conn.close()
        return rows

    def delete_wifi_profile(self, config_name, ssid):
        """Delete a specific Wi-Fi profile."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM wifi_profiles WHERE config_name = ? AND ssid = ?",
            (config_name, ssid),
        )
        conn.commit()
        conn.close()
