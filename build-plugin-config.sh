#!/bin/bash

cd minecraft-docker
VERSION=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "latest")

docker rm spigot-build-config -f
docker rm spigot-map-config -f

sudo rm -rf ./build/worlds/
sudo mkdir -p ./build/worlds/plotworld
sudo chmod 777 ./build/plugins
sudo chmod 777 ./map/plugins

sudo rm -rf ./build/plugins/*/

docker run -d \
  --name spigot-build-config \
  -v ./build/plugins:/mc/plugins \
  minecraft-base:$VERSION

rm -rf ./map/plugins/*/
docker run -d \
  --name spigot-map-config \
  -v ./map/plugins:/mc/plugins \
  minecraft-base:$VERSION

sleep 40

commands=(
  "mv create plotworld normal -g PlotSquared"
  "mv modify plotworld set gamemode creative"
  "mv modify plotworld set difficulty peaceful plotworld"
  "lp group default permission set essentials.gamemode.creative true"
  "lp group default permission set minecraft.command.help true"
  "lp group default permission set minecraft.command.list true"
  "lp group default permission set minecraft.command.msg true"
  "lp group default permission set minecraft.command.me true"
  "lp group default permission set minecraft.command.spawnpoint true"
  "lp group default permission set minecraft.command.tell true"
  "lp group default permission set minecraft.command.trigger true"
  "lp group default permission set plots.* true"
  "lp group default permission set plots.admin.* false"
)

for cmd in "${commands[@]}"; do
  echo "Running: $cmd"
  docker exec -it "spigot-build-config" mcrcon -H "127.0.0.1" -P 25575 -p "DEFAULT_ADMIN_PASSWORD" "$cmd"
done

while ! docker exec spigot-build-config test -d /mc/plotworld; do
  echo "Waiting for plotworld to be created..."
  sleep 2
done

docker cp spigot-build-config:/mc/plotworld/ ./build/worlds/
docker cp spigot-build-config:/mc/bukkit.yml ./build/

cat <<'EOF' >> ./build/bukkit.yml
worlds:
  plotworld:
    generator: PlotSquared
EOF

bluemap_build_config="./build/plugins/BlueMap/core.conf"
if [ -f "$bluemap_build_config" ]; then
  sed -i 's/^accept-download: false/accept-download: true/' $bluemap_build_config
fi

bluemap_build_world_config="./build/plugins/BlueMap/maps/world.conf"
if [ -f "$bluemap_build_world_config" ]; then
  sed -i 's/^world: "world"/world: "plotworld"/' $bluemap_build_world_config
fi

bluemap_map_config="./map/plugins/BlueMap/core.conf"
if [ -f "$bluemap_map_config" ]; then
  sed -i 's/^accept-download: false/accept-download: true/' $bluemap_map_config
fi

essentials_config="./build/plugins/Essentials/config.yml"
if [ -f "$essentials_config" ]; then
  yq -i '
    .["player-commands"] |= (. // []) + ["gamemode","customtext"] | .["player-commands"] |= unique
  ' "$essentials_config"
fi

join_commands_config="./build/plugins/JoinCommands/config.yml"
if [ -f "$join_commands_config" ]; then
    yq -i '
    .world-join-commands.plotworld.world-list = ["plotworld"] |
    .world-join-commands.plotworld.command-list = ["p auto"] |
    .world-join-commands.plotworld.delay = 0 |
    .world-join-commands.plotworld["first-join-only"] = true |
    .world-join-commands.plotworld.permission = ""
    ' "$join_commands_config"
fi

multiverse_config="./build/plugins/Multiverse-Core/config.yml"
if [ -f "$multiverse_config" ]; then
  yq eval '.world-join-commands."first-spawn-override" = true' -i "$multiverse_config"
  yq eval '.spawn."first-spawn-location" = "plotworld"' -i "$multiverse_config"
fi


sudo chown -R ls:ls ./build/worlds/
sudo chown -R ls:ls ./build/plugins/
sudo chown -R ls:ls ./map/plugins/
sudo chmod 755 ./build/plugins
sudo chmod 755 ./map/plugins

docker rm spigot-build-config -f
docker rm spigot-map-config -f