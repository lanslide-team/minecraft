#!/bin/bash

cd minecraft-docker
VERSION=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "latest")

docker build -t "minecraft-base:$VERSION"   ./base
docker build -t "minecraft-build:$VERSION"  ./build
docker build -t "minecraft-map:$VERSION"    ./map
