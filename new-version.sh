#!/usr/bin/env bash
set -euo pipefail

cd minecraft-docker
if [ $# -ne 2 ]; then
  echo "Usage: $0 <old_version> <new_version>"
  exit 1
fi

OLD="v$1"
NEW="v$2"

git fetch origin
git checkout "$OLD"
git checkout -b "$NEW"

sed -i "s/MC_VERSION=$1/MC_VERSION=$2/" base/Dockerfile
sed -i "s/MC_VERSION=$1/MC_VERSION=$2/" build/Dockerfile
sed -i "s/MC_VERSION=$1/MC_VERSION=$2/" map/Dockerfile

git commit -am "Bump to Minecraft $2 (based on $1)"
git push --set-upstream origin "$NEW"
