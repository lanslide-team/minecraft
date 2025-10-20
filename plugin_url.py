#!/usr/bin/env python3
import sys, json, re, requests

# --------------------------
# Utility Functions
# --------------------------
def version_tuple(v):
    """Convert a version string into a tuple of integers for comparison."""
    return tuple(int(x) for x in re.findall(r'\d+', v))

def extract_version(s):
    """Extract version string from filenames like plugin-1.2.3.jar or plugin-1.2.3-beta-1.jar"""
    m = re.search(r'(\d+(?:\.\d+)+(?:-beta-\d+)?)', s)
    return m.group(1) if m else "0"

# --------------------------
# Modrinth
# --------------------------
def modrinth_latest(slug, beta=False):
    """Fetch the latest Modrinth version, preferring Spigot/Bukkit/Paper jars."""
    try:
        r = requests.get(f"https://api.modrinth.com/v2/project/{slug}/version", timeout=10).json()
        best_url, best_ver = None, "0"
        for v in r:
            ver = v.get("version_number") or v.get("name") or "0"
            if not beta and "beta" in ver.lower():
                continue
            for f in v.get("files", []):
                fn = f["url"].lower()
                if not fn.endswith(".jar"):
                    continue
                # Only pick Spigot/Bukkit/Paper jars
                if any(x in fn for x in ["velocity", "bungee", "fabric", "cli"]):
                    continue
                if version_tuple(ver) > version_tuple(best_ver):
                    best_ver = ver
                    best_url = f["url"]
        return best_url
    except Exception as e:
        print(f"Modrinth error: {e}", file=sys.stderr)
        return None

# --------------------------
# GitHub
# --------------------------
def github_latest(repo_url, beta=False):
    """
    Fetch the latest GitHub release, preferring Spigot > Paper > other jars.
    Excludes CLI, sources, javadoc, Fabric, Velocity, Bungee.
    """
    try:
        m = re.search(r"github\.com/([^/]+/[^/]+)", repo_url)
        if not m:
            return None
        repo = m.group(1)
        releases = requests.get(f"https://api.github.com/repos/{repo}/releases", timeout=10).json()

        best_url = None
        best_priority = 0  # 3=Spigot/Bukkit, 2=Paper, 1=Other

        for rel in releases:
            if not beta and rel.get("prerelease", False):
                continue

            for a in rel.get("assets", []):
                fn = a["name"].lower()
                if not fn.endswith(".jar") or any(x in fn for x in ["cli", "-sources", "-javadoc", "fabric", "velocity", "bungee"]):
                    continue

                # Assign priority
                if "spigot" in fn or "bukkit" in fn:
                    priority = 3
                elif "paper" in fn:
                    priority = 2
                else:
                    priority = 1

                if priority > best_priority:
                    best_priority = priority
                    best_url = a["browser_download_url"]

        return best_url
    except Exception as e:
        print(f"GitHub error: {e}", file=sys.stderr)
        return None

# --------------------------
# Hangar
# --------------------------
def hangar_latest(url, beta=False):
    """
    Fetch the latest Hangar version.
    Only supports PAPER platform. Beta versions can be included with --beta.
    """
    try:
        m = re.search(r"hangar\.papermc\.io/([^/]+)/([^/]+)", url)
        if not m:
            return None
        author, project = m.group(1), m.group(2)
        r = requests.get(f"https://hangar.papermc.io/api/v1/projects/{author}/{project}/versions", timeout=10).json()["result"]

        # Sort descending by version number
        versions = sorted(r, key=lambda v: version_tuple(v["name"]), reverse=True)
        for v in versions:
            if not beta and v.get("channel", {}).get("name", "").lower() == "beta":
                continue
            ver_name = v["name"]
            platform = "PAPER"
            file_name = f"{project}-{ver_name}.jar"
            return f"https://hangarcdn.papermc.io/plugins/{author}/{project}/versions/{ver_name}/{platform}/{file_name}"
        return None
    except Exception as e:
        print(f"Hangar error: {e}", file=sys.stderr)
        return None

# --------------------------
# Main lookup
# --------------------------
def get_latest(plugin_name, beta=False):
    """
    Load repos.json and query sources in order:
    Modrinth -> GitHub -> Hangar
    """
    try:
        with open("minecraft-docker/repos.json") as f:
            plugins = json.load(f)
    except Exception as e:
        print(f"Error loading repos.json: {e}", file=sys.stderr)
        return None

    urls = plugins.get(plugin_name.lower())
    if not urls:
        return None

    for url in urls:
        result = None
        if "modrinth.com" in url:
            result = modrinth_latest(url.rstrip("/").split("/")[-1], beta=beta)
        elif "github.com" in url:
            result = github_latest(url, beta=beta)
        elif "hangar.papermc.io" in url:
            result = hangar_latest(url, beta=beta)
        if result:
            return result
    return None

# --------------------------
# CLI Interface
# --------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: plugin-url.py <plugin_name> [--beta | --stable]", file=sys.stderr)
        sys.exit(1)

    plugin_name = sys.argv[1]
    beta_flag = False
    if len(sys.argv) > 2 and sys.argv[2].lower() == "--beta":
        beta_flag = True

    jar = get_latest(plugin_name, beta=beta_flag)
    if jar:
        # Output only the jar URL (for other scripts to use)
        print(jar)
    else:
        sys.exit(1)

