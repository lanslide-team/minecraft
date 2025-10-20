#!/usr/bin/env python3
import zipfile
import os
import shutil
import yaml
import re

def get_official_plugin_name(jar_path):
    try:
        with zipfile.ZipFile(jar_path, 'r') as z:
            if 'plugin.yml' in z.namelist():
                with z.open('plugin.yml') as f:
                    data = yaml.safe_load(f)
                    return data.get('name')
    except Exception:
        pass
    return os.path.basename(jar_path).split('-')[0]

def clear_subdirectories(plugin_dir, log=None):
    for item in os.listdir(plugin_dir):
        item_path = os.path.join(plugin_dir, item)
        if os.path.isdir(item_path):
            shutil.rmtree(item_path)
            if log:
                log(f"Cleared subdirectory {item_path}")

def extract_configs(jar_path, target_root, log=None):
    plugin_name = get_official_plugin_name(jar_path)
    if plugin_name.lower() == "bluemap":
        return

    plugin_dir = os.path.join(os.path.dirname(jar_path), plugin_name)
    os.makedirs(plugin_dir, exist_ok=True)

    # Clear subdirectories first
    clear_subdirectories(plugin_dir, log)

    if log:
        log(f"Jar path: {jar_path}")

    with zipfile.ZipFile(jar_path, 'r') as z:
        for f in z.namelist():
            if f.endswith(('.yml', '.conf', '.json', '.txt')):
                dest_dir = plugin_dir
                dest_file = os.path.join(dest_dir, os.path.basename(f))
                os.makedirs(dest_dir, exist_ok=True)

                with z.open(f) as src, open(dest_file, 'wb') as dst:
                    dst.write(src.read())

def process_all_plugins(target_root=".", log=None):
    """Automatically find JARs in subfolders and extract configs."""
    for root, dirs, files in os.walk(target_root):
        for item in files:
            if item.endswith(".jar"):
                jar_path = os.path.join(root, item)
                extract_configs(jar_path, target_root, log)

if __name__ == "__main__":
    def log(msg): print(msg)
    process_all_plugins(log=log)
