#!/bin/bash

cd minecraft-docker
VERSION=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "latest")

sudo chmod -R 777 ./build/plotworld 2>/dev/null || true
sudo chmod 777 ./build/plugins
sudo chmod 777 ./map/plugins

rm -rf ./build/plotworld/
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

docker exec -it spigot-build-config \
  mcrcon -H 127.0.0.1 -P 25575 -p DEFAULT_ADMIN_PASSWORD "mv create plotworld normal -g PlotSquared"

while ! docker exec spigot-build-config test -d /mc/plotworld; do
  echo "Waiting for plotworld to be created..."
  sleep 5
done

docker cp spigot-build-config:/mc/plotworld ./build/plotworld

sleep 10

sudo chown -R ls:ls ./build/plotworld/
sudo chown -R ls:ls ./build/plugins/
sudo chown -R ls:ls ./map/plugins/
sudo chmod 755 ./build/plotworld
sudo chmod 755 ./build/plugins
sudo chmod 755 ./map/plugins

docker rm spigot-build-config -f
docker rm spigot-map-config -f