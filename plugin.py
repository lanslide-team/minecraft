#!/usr/bin/env python3
import os
import sys
import argparse
import configparser
import subprocess
import glob
import re
import shutil
from plugin_config import process_all_plugins
from urllib.request import urlretrieve
from datetime import datetime

CONFIG_FILE = "plugins.ini"
LOG_DIR = "logs"


def _ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)


def _log(base_dir, plugin_name, message):
    _ensure_dir(os.path.join(base_dir, LOG_DIR))
    log_path = os.path.join(base_dir, LOG_DIR, f"{plugin_name}.log")
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    with open(log_path, "a") as f:
        f.write(f"{timestamp} {message}\n")
    print(f"[{plugin_name}] {message}")


def get_installed_version(plugin_name, target_dir, cleanup_globs):
    for pattern in cleanup_globs:
        for path in glob.glob(os.path.join(target_dir, pattern)):
            basename = os.path.basename(path).lower()
            match = re.match(
                r"([a-zA-Z0-9\-]+)-([0-9\-\.]+)(?:-\w+)?(\.jar|\.zip)$", basename
            )
            if match:
                return match.group(2)
    return None


def get_config_version(plugin_cfg, plugin_name):
    url = plugin_cfg.get("url")
    if url:
        version_match = re.search(r"(\d+(\.\d+)+[-\w]*)", url)
        if version_match:
            return version_match.group(0)
    return plugin_name


def get_latest_url(plugin_name, log):
    t = None
    try:
        output = subprocess.check_output(
            ["python3", "plugin_url.py", plugin_name], text=True
        ).strip()
        if output:
            return output
    except subprocess.CalledProcessError as e:
        log(e)
        return None
    return None

def download_plugin(url, target_path, log):
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        log(f"Downloading {url} to {target_path}...")
        urlretrieve(url, target_path)
        log(f"Downloaded successfully to {target_path}.")

        plugin_name = os.path.basename(target_path).split('-')[0].lower()

        # --- Bluemap special handling ---
        if plugin_name == "bluemap":
            # Derive CLI jar URL (replace '-spigot.jar' with '-cli.jar')
            cli_url = re.sub(r"-spigot\.jar$", "-cli.jar", url)
            cli_filename = os.path.basename(cli_url)
            cli_target_path = os.path.join(os.path.dirname(target_path), cli_filename)

            log(f"Detected Bluemap — downloading CLI jar: {cli_url}")
            urlretrieve(cli_url, cli_target_path)
            log(f"Downloaded Bluemap CLI successfully to {cli_target_path}")

            # Run CLI to generate default configs
            bluemap_output_dir = os.path.join(os.path.dirname(target_path), "BlueMap")
            os.makedirs(bluemap_output_dir, exist_ok=True)

            log(f"Running BlueMap CLI setup to generate configs in {bluemap_output_dir}...")
            try:
                result = subprocess.run(
                    ["java", "-jar", cli_target_path, "-c", bluemap_output_dir],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            except subprocess.CalledProcessError as e:
                pass
#                log(f"BlueMap CLI setup failed:\n{e.stdout}")

            log("BlueMap CLI setup completed successfully.")
            data_dir = 'data'
            if os.path.exists(data_dir):
                shutil.rmtree(data_dir)

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
                log(f"Set accept-download=true in {core_conf}")

        # --- End Bluemap special handling ---

    except Exception as e:
        log(f"Error downloading plugin from {url}: {e}")
        return False

    return True

def normalize_version(version):
    """Remove any suffix like '-spigot' to make version comparison easier."""
    return version.split("-")[0]

def discover_plugin(base_dir, plugin_name, plugin_cfg):
    targets = plugin_cfg.get("targets", "build").split(",")
    cleanup_globs = [
        g.strip() for g in plugin_cfg.get("cleanup_globs", "").split(",") if g.strip()
    ]
    config_version = get_config_version(plugin_cfg, plugin_name)
    log_function = lambda msg: _log(base_dir, plugin_name, f"{t.strip()}/plugins: {msg}")
    latest_url = get_latest_url(plugin_name, log_function)
    latest_version = None
    if latest_url:
        latest_version = get_config_version({"url": latest_url}, plugin_name)

    for t in targets:
        target_dir = os.path.join(base_dir, t.strip() + "/plugins")
        _ensure_dir(target_dir)
        installed_version = get_installed_version(plugin_name, target_dir, cleanup_globs)

        if not installed_version:
            installed_version = config_version
            if config_version == latest_version:
                log_function(f"not installed ({installed_version})")
            else:
                log_function(f"not installed ({config_version} → {latest_version})")
        else:
            normalized_installed = normalize_version(installed_version)
            normalized_latest = normalize_version(latest_version) if latest_version else None
            normalized_config = normalize_version(config_version)

            if normalized_installed != normalized_latest:
                log_function(f"update available ({normalized_installed} → {normalized_latest})")
            elif normalized_installed != normalized_config:
                log_function(
                    f"config version mismatch ({normalized_installed} → {normalized_config} [c])"
                )
            else:
                log_function(f"already up-to-date ({normalized_installed})")


def version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v))


def update_plugin(base_dir, plugin_name, plugin_cfg, prefer_newer=True):
    targets = plugin_cfg.get("targets", "build").split(",")
    cleanup_globs = [
        g.strip() for g in plugin_cfg.get("cleanup_globs", "").split(",") if g.strip()
    ]
    log_function = lambda msg: _log(base_dir, plugin_name, f"{t.strip()}/plugins: {msg}")
    latest_url = get_latest_url(plugin_name, log_function)
    latest_version = None
    if latest_url:
        latest_version = get_config_version({"url": latest_url}, plugin_name)

    for t in targets:
        target_dir = os.path.join(base_dir, t.strip() + "/plugins")
        _ensure_dir(target_dir)
        installed_version = get_installed_version(plugin_name, target_dir, cleanup_globs)

        normalized_installed = normalize_version(installed_version) if installed_version else None
        normalized_latest = normalize_version(latest_version) if latest_version else None

        need_update = (
            normalized_installed is None
            or version_tuple(normalized_installed) < version_tuple(normalized_latest)
        )

        if need_update and latest_url:
            for pattern in cleanup_globs:
                for path in glob.glob(os.path.join(target_dir, pattern)):
                    os.remove(path)

            jar_name = os.path.basename(latest_url)
            target_path = os.path.join(target_dir, jar_name)

            if not download_plugin(latest_url, target_path, log_function):
                continue

            if installed_version is None:
                log_function(f"installing {latest_version}")
            else:
                log_function(f"updated {installed_version} → {latest_version}")

            plugin_cfg["url"] = latest_url

            config = configparser.ConfigParser()
            config_path = os.path.join(base_dir, CONFIG_FILE)
            config.read(config_path)
            section_name = f"plugin:{plugin_name}"
            if not config.has_section(section_name):
                config.add_section(section_name)
            for key, value in plugin_cfg.items():
                config.set(section_name, key, str(value))
            with open(config_path, "w") as config_file:
                config.write(config_file)

            log_function(f"version updated in config to {normalized_latest}")
        else:
            log_function(f"already up-to-date ({normalized_installed})")

def sync_plugin(base_dir, plugin_name, plugin_cfg):
    """
    Install the plugin version specified in the config, ignoring latest URLs.
    """
    targets = plugin_cfg.get("targets", "build").split(",")
    cleanup_globs = [g.strip() for g in plugin_cfg.get("cleanup_globs", "").split(",") if g.strip()]
    config_version = get_config_version(plugin_cfg, plugin_name)
    url = plugin_cfg.get("url")
    if not url:
        _log(base_dir, plugin_name, "No URL in config, skipping.")
        return

    for t in targets:
        target_dir = os.path.join(base_dir, t.strip() + "/plugins")
        _ensure_dir(target_dir)
        installed_version = get_installed_version(plugin_name, target_dir, cleanup_globs)

        normalized_installed = normalize_version(installed_version) if installed_version else None
        normalized_config = normalize_version(config_version)

        if normalized_installed != normalized_config:
            # Remove old versions
            for pattern in cleanup_globs:
                for path in glob.glob(os.path.join(target_dir, pattern)):
                    os.remove(path)

            jar_name = os.path.basename(url)
            target_path = os.path.join(target_dir, jar_name)
            if download_plugin(url, target_path, lambda msg: _log(base_dir, plugin_name, f"{t.strip()}/plugins: {msg}")):
                if installed_version is None:
                    _log(base_dir, plugin_name, f"{t.strip()}/plugins: installing {config_version}")
                else:
                    _log(base_dir, plugin_name, f"{t.strip()}/plugins: updated {installed_version} → {config_version}")
            else:
                _log(base_dir, plugin_name, f"{t.strip()}/plugins: failed to download {config_version}")
        else:
            _log(base_dir, plugin_name, f"{t.strip()}/plugins: already in sync ({config_version})")

def main():
    parser = argparse.ArgumentParser(description="Discover or update plugins (silent; logs to file).")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(sp):
        sp.add_argument("--only", metavar="PLUGIN", help="Only act on a single plugin")
        sp.add_argument("--base-dir", default="minecraft-docker", help="Base directory")

    sp_discover = sub.add_parser("discover")
    add_common(sp_discover)

    sp_update = sub.add_parser("update")
    add_common(sp_update)
    sp_update.add_argument("--prefer-newer", action="store_true")

    sp_sync = sub.add_parser("sync")
    add_common(sp_sync)

    args = parser.parse_args()

    config = configparser.ConfigParser()
    config_path = os.path.join(args.base_dir, CONFIG_FILE)
    config.read(config_path)

    targets_plugins = {
        section.split(":", 1)[1].lower(): dict(config[section])
        for section in config.sections()
        if section.startswith("plugin:")
    }

    base_dir = os.path.abspath(args.base_dir)
    _ensure_dir(base_dir)

    selected_plugins = targets_plugins
    if args.only:
        key = args.only.lower()
        if key not in targets_plugins:
            _log(base_dir, "general", f"No such plugin in registry: {key}")
            return 1
        selected_plugins = {key: targets_plugins[key]}

    _log(base_dir, "general", f"Base directory: {base_dir}")

    if args.command == "discover":
        _log(base_dir, "general", "Discovery results (no changes):")
        for k, p in selected_plugins.items():
            discover_plugin(base_dir, k, p)
        return 0

    if args.command == "update":
        _log(base_dir, "general", "Updating plugins:")
        for k, p in selected_plugins.items():
            update_plugin(base_dir, k, p, prefer_newer=args.prefer_newer)
        process_all_plugins()
        return 0

    if args.command == "sync":
        _log(base_dir, "general", "Syncing plugins to config versions:")
        for k, p in selected_plugins.items():
            sync_plugin(base_dir, k, p)
        process_all_plugins()
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
