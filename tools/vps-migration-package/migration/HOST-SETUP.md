# Host prerequisites before restoring development tools

Original host: Ubuntu24.04.5 LTS, x86_64; systemPython3.12.3, Git2.43.0, unzip6.0; Docker reports29.1.3. SystemPython is only the bootstrap interpreter. Project tests use separately rebuiltCPython3.12.10.

These commands are for a **new, otherwise empty Ubuntu24.04 x86_64 VPS**, with sudo available. Do not run package removal/upgrade commands on an existing game server. No host installation was performed while preparing this transfer.

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git unzip python3
```

If Docker is not already installed, configure its official Ubuntu repository and select a specific version as described in [Docker's Ubuntu installation guide](https://docs.docker.com/engine/install/ubuntu/). The commands below use that repository method and stop if29.1.3 is unavailable; do not silently substitute an unreviewed version.

```bash
set -euo pipefail
. /etc/os-release
test "$ID" = ubuntu
test "$VERSION_CODENAME" = noble
test "$(dpkg --print-architecture)" = amd64
if command -v docker >/dev/null; then
  echo 'Docker already exists. Retain it and verify its version; do not reinstall.'
else
  sudo install -m 0755 -d /etc/apt/keyrings
  test ! -e /etc/apt/keyrings/docker.asc
  test ! -e /etc/apt/sources.list.d/docker.sources
  sudo curl --fail --silent --show-error --location https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod 0644 /etc/apt/keyrings/docker.asc
  printf '%s\n' 'Types: deb' 'URIs: https://download.docker.com/linux/ubuntu' 'Suites: noble' 'Components: stable' 'Architectures: amd64' 'Signed-By: /etc/apt/keyrings/docker.asc' | sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null
  sudo apt-get update
  docker_version=$(apt-cache madison docker-ce | awk '$3 ~ /^5:29\.1\.3-/ {print $3; exit}')
  test -n "$docker_version" || { echo 'Docker29.1.3 unavailable; stop and review an alternative version.'; exit 1; }
  sudo apt-get install -y "docker-ce=$docker_version" "docker-ce-cli=$docker_version" containerd.io docker-buildx-plugin docker-compose-plugin
fi
sudo systemctl start docker
sudo docker version
```

Configure your development user's Docker access using the [official post-install instructions](https://docs.docker.com/engine/install/linux-postinstall/), or use an appropriately configured rootless daemon. Membership in the docker group provides root-equivalent control. The supplied rebuild commands expect `docker info` to succeed for your development user; they do not change group membership themselves.

Then follow `environment/README-ENVIRONMENT.md`. This reinstalls the container toolchains and projectPython3.12.10 using included pins/archives. Never run the container-built Python binary directly on Ubuntu: the image's GLIBC/OpenSSL may differ. Invoke it inside the specified container with the preserved mount paths.
