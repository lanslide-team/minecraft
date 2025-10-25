#!/usr/bin/env python3
from __future__ import annotations

import argparse
import configparser
import glob
import os
import re
import shutil
import subprocess
import sys
import zipfile
import yaml

from urllib.request import urlretrieve, build_opener, install_opener
from datetime import datetime

class Plugin:
    LOG_DIR_NAME: str = "logs"
    TEMP_DIR_NAME: str = "temp"
    PLUGIN_DIR: str = "plugins"
    CONFIG_FILE: str = "plugins.ini"

    def __init__(self) -> None:
        parser = argparse.ArgumentParser(description="Discover or update plugins (silent; logs to file).")
        parser.add_argument("--only", metavar="PLUGIN", help="Only act on a single plugin")
        parser.add_argument("--base-dir", default="minecraft-docker", help="Base directory")
        parser.add_argument(
            "-v", "--verbose",
            action="count",
            default=0,
            help="Increase verbosity (use -vv for more detailed output)"
        )

        # Updating plugins, keep track of these
        self.args = parser.parse_args()
        self.base_dir: str = os.path.abspath(self.args.base_dir)
        self.current_target = None
        self.current_plugin = None
        self.log_dir = os.path.join(self.base_dir, self.LOG_DIR_NAME)
        self.temp_dir = os.path.join(self.base_dir, self.TEMP_DIR_NAME)
        self.target_dir = None
        self.verbosity = self.args.verbose + 1

        self.log(f"Base directory: {self.base_dir}")
        Plugin._ensure_dir(self.base_dir)
        Plugin._ensure_dir(self.log_dir)
        Plugin._ensure_dir(self.temp_dir)

        for target in ['build', 'map']:
            Plugin._ensure_dir(os.path.join(self.base_dir, target, Plugin.PLUGIN_DIR))

        # Force user-agent on downloads
        opener = build_opener()
        opener.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")]
        install_opener(opener)

        # Read Config
        self.config_path = os.path.join(self.args.base_dir, self.CONFIG_FILE)
        self.config = configparser.ConfigParser()
        self.config.read(self.config_path)
        self.config_updated = False

        targets_plugins = {
            section.split(":", 1)[1].lower(): dict(self.config[section])
            for section in self.config.sections()
            if section.startswith("plugin:")
        }

        self.selected_plugins = targets_plugins
        if self.args.only:
            if self.args.only not in targets_plugins:
                self.log(f"No such plugin in registry: {self.args.only}", level=1)
                sys.exit(1)
            self.selected_plugins = {self.args.only: targets_plugins[self.args.only]}

    def log(self, message: str, save_log: bool = False, level: int = 1) -> None:
        """
        level: 1 = normal, 2 = verbose, 3 = very verbose
        """
        if self.verbosity < level:
            return  # Skip logging for lower levels

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        path = ''
        if self.current_plugin:
            path = f"{self.current_target}/{self.PLUGIN_DIR}/{self.current_plugin}: " if self.current_target is not None else f"{self.current_plugin}: "

        log_message = f"[{timestamp}] {path}{message}"

        print(f"{log_message}")
        if save_log and self.current_plugin:
            log_path = os.path.join(self.log_dir, f"{self.current_plugin}.log")
            with open(log_path, "a") as f:
                f.write(f"{log_message}\n")

    @staticmethod
    def _ensure_dir(path):
        if not os.path.exists(path):
            os.makedirs(path)

    def save_config(self):
        with open(self.config_path, "w") as config_file:
            self.config.write(config_file)
        self.log(f"Written back to config", level=2)

    def process(self):
        self.log( 'Updating plugins:', level=1)

        general_prefer_beta = self.config.getboolean("general", "prefer_beta", fallback=False)
        general_prefer_newer = self.config.getboolean("general", "prefer_newer", fallback=False)

        for plugin_name, plugin in self.selected_plugins.items():
            prefer_beta = self.config.getboolean(f"plugin:{plugin_name}", "prefer_beta", fallback=general_prefer_beta)
            prefer_newer = self.config.getboolean(f"plugin:{plugin_name}", "prefer_newer", fallback=general_prefer_newer)
            if self.config.getboolean(f"plugin:{plugin_name}", "enabled", fallback=False):
                self.update_plugin(plugin_name, plugin, prefer_beta, prefer_newer)

        shutil.rmtree(self.temp_dir)
        self.log(f"Removing temp dir {self.temp_dir}", level=2)
        if self.config_updated:
            self.save_config()

    @staticmethod
    def get_jar(plugin_dir: str, cleanup_globs: list[str]):
        for pattern in cleanup_globs:
            for path in glob.glob(os.path.join(plugin_dir, pattern)):
                return os.path.basename(path)
        return None

    def read_plugin(self, cleanup_globs: list[str], use_temp: bool = False):
        plugin_dir = self.temp_dir if use_temp else self.target_dir

        if jar_path := Plugin.get_jar(plugin_dir, cleanup_globs):
            with zipfile.ZipFile(os.path.join(plugin_dir, jar_path), 'r') as z:
                if 'plugin.yml' in z.namelist():
                    with z.open('plugin.yml') as f:
                        return yaml.safe_load(f)

        return None

    def get_latest_url(self, plugin_name, prefer_beta: bool = False):
        try:
            beta = '--beta' if prefer_beta else '--stable'
            output = subprocess.check_output(
                ["python3", "plugin_url.py", plugin_name, beta], text=True
            ).strip()
            if output:
                return output
        except subprocess.CalledProcessError as e:
            self.log(str(e))
        return None

    def __process_bluemap(self, url: str):
        # Run CLI to generate default configs
        bluemap_output_dir = os.path.join(self.target_dir, "BlueMap")
        os.makedirs(bluemap_output_dir, exist_ok=True)

        # Derive CLI jar URL (replace '-spigot.jar' with '-cli.jar')
        cli_url = re.sub(r"-spigot\.jar$", "-cli.jar", url)
        cli_filename = os.path.basename(cli_url)
        cli_target_path = os.path.join(bluemap_output_dir, cli_filename)

        self.log(f"Detected Bluemap — downloading CLI jar: {cli_url}", level=3)
        urlretrieve(cli_url, cli_target_path)
        self.log(f"Downloaded Bluemap CLI successfully to {cli_target_path}", level=3)

        self.log(f"Running BlueMap CLI setup to generate configs in {bluemap_output_dir}...", level=3)
        try:
            subprocess.run(
                ["java", "-jar", cli_filename, "-c", '.'],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=bluemap_output_dir
            )
        except subprocess.CalledProcessError as e:
            pass

        self.log("BlueMap CLI setup completed successfully.", level=3)
        os.remove(cli_target_path)

        core_conf = os.path.join(bluemap_output_dir, "core.conf")
        if os.path.exists(core_conf):
            with open(core_conf, "r+", encoding="utf-8") as f:
                lines = f.readlines()
                f.seek(0)
                if any(l.strip().startswith("accept-download") for l in lines):
                    lines = [("accept-download=true\n" if l.strip().startswith("accept-download") else l) for l in
                             lines]
                else:
                    lines.append("accept-download=true\n")
                f.writelines(lines)
                f.truncate()
            self.log(f"Set accept-download=true in {core_conf}", level=3)

    def download_plugin(self, url: str, target_path: str):
        try:
            self.log(f"Downloading {url} to {target_path}...", level=2)
            urlretrieve(url, target_path)
            self.log(f"Downloaded successfully to {target_path}.", level=2)
        except Exception as e:
            self.log(f"Error downloading plugin from {url}: {e}", level=1)
            return False

        return True

    def update_plugin(self, plugin_name, plugin_cfg, prefer_beta, prefer_newer):
        targets = plugin_cfg.get("targets", "build").split(",")
        cleanup_globs = [
            g.strip() for g in plugin_cfg.get("cleanup_globs", "").split(",") if g.strip()
        ]

        for target in targets:
            self.current_target = target
            self.current_plugin = plugin_name
            self.target_dir = os.path.join(self.base_dir, target, self.PLUGIN_DIR)

            url = self.get_latest_url(plugin_name, prefer_beta) if prefer_newer else plugin_cfg['url']
            if not url:
                self.log(f"No URL found for {plugin_name}, skipping.", level=1)
                continue

            jar_name = os.path.basename(url)
            temp_path = os.path.join(self.temp_dir, jar_name)
            target_path = os.path.join(self.target_dir, jar_name)
            if not self.download_plugin(url, temp_path):
                continue

            local_plugin = self.read_plugin(cleanup_globs, False)
            temp_plugin = self.read_plugin(cleanup_globs, True)

            if temp_plugin:
                if local_plugin:
                    do_update = False
                    if temp_plugin['version'] == local_plugin['version']:
                        self.log(f"Versions match [{temp_plugin['version']}], no update required.", level=1)
                    else:
                        self.log(f"Update available: {local_plugin['version']} → {temp_plugin['version']}", level=1)
                        do_update = input("Proceed with new version? [y/Y]: ").lower() == 'y'

                    # Clean up old versions
                    if do_update:
                        for pattern in cleanup_globs:
                            for path in glob.glob(os.path.join(self.target_dir, pattern)):
                                os.remove(path)
                else:
                    # No local version, force download
                    self.log(f"Downloading update: {temp_plugin['version']}", level=1)
                    do_update = True

                if do_update:
                    self.log(f"Moving {temp_path} to {target_path}...", level=2)
                    shutil.move(temp_path, target_path)
                    plugin_cfg["url"] = url
                    self.config_updated = True

                    if plugin_name.lower() == 'bluemap':
                        self.__process_bluemap(url)
            else:
                self.log("Failed to download plugin", level=1)

        self.current_target = None
        self.current_plugin = None
        self.target_dir = None


if __name__ == "__main__":
    plugin = Plugin()
    plugin.process()
