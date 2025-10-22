#!/bin/bash

cd minecraft-docker
VERSION=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "latest")

sudo chmod 777 ./build/plugins
sudo chmod 777 ./map/plugins

rm -rf ./build/plugins/*/

docker run -d \
  --name spigot-build-config \
  -v ./build/plugins:/mc/plugins \
  minecraft-base:$VERSION

rm -rf ./map/plugins/*/
docker run -d \
  --name spigot-map-config \
  -v ./map/plugins:/mc/plugins \
  minecraft-base:$VERSION

sleep 30

sudo chown -R ls:ls ./build/plugins/
sudo chown -R ls:ls ./map/plugins/
sudo chmod 755 ./build/plugins
sudo chmod 755 ./map/plugins

docker rm spigot-build-config -f
docker rm spigot-map-config -f