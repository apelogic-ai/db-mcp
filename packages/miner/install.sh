#!/bin/bash
# Miner install script — downloads the latest binary for your platform.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/apelogic-ai/db-mcp/main/packages/miner/install.sh | bash
#
# Environment variables:
#   MINER_VERSION  — specific version (default: latest)
#   MINER_DIR      — install directory (default: ~/.local/bin)

set -euo pipefail

REPO="apelogic-ai/db-mcp"
INSTALL_DIR="${MINER_DIR:-$HOME/.local/bin}"
BINARY_NAME="miner"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
DIM='\033[2m'
RESET='\033[0m'

info() { echo -e "${GREEN}$1${RESET}"; }
dim() { echo -e "${DIM}$1${RESET}"; }
error() { echo -e "${RED}Error: $1${RESET}" >&2; exit 1; }

# Detect platform
detect_platform() {
  local os arch target

  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  arch="$(uname -m)"

  case "$os" in
    darwin) os="darwin" ;;
    linux)  os="linux" ;;
    *)      error "Unsupported OS: $os" ;;
  esac

  case "$arch" in
    arm64|aarch64) arch="arm64" ;;
    x86_64|amd64)  arch="x64" ;;
    *)             error "Unsupported architecture: $arch" ;;
  esac

  echo "${os}-${arch}"
}

# Get latest version from GitHub
get_latest_version() {
  local version
  version=$(curl -fsSL "https://api.github.com/repos/${REPO}/releases" \
    | grep -o '"tag_name": "miner-v[^"]*"' \
    | head -1 \
    | grep -o 'v[0-9.]*' \
    | head -1)

  if [ -z "$version" ]; then
    error "Could not determine latest version. Set MINER_VERSION manually."
  fi
  echo "$version"
}

main() {
  echo ""
  info "Miner — AI agent trace collection"
  echo ""

  # Detect platform
  local target
  target=$(detect_platform)
  dim "Platform: $target"

  # Determine version
  local version
  if [ -n "${MINER_VERSION:-}" ]; then
    version="$MINER_VERSION"
    dim "Version: $version (from MINER_VERSION)"
  else
    dim "Checking latest version..."
    version=$(get_latest_version)
    dim "Version: $version"
  fi

  # Download URL
  local url="https://github.com/${REPO}/releases/download/miner-${version}/miner-${target}"
  local checksum_url="${url}.sha256"

  dim "Downloading miner-${target}..."

  # Create install directory
  mkdir -p "$INSTALL_DIR"

  # Download binary
  local tmp_file
  tmp_file=$(mktemp)
  if ! curl -fsSL "$url" -o "$tmp_file"; then
    rm -f "$tmp_file"
    error "Download failed. Check https://github.com/${REPO}/releases for available versions."
  fi

  # Verify checksum
  local tmp_checksum
  tmp_checksum=$(mktemp)
  if curl -fsSL "$checksum_url" -o "$tmp_checksum" 2>/dev/null; then
    local expected actual
    expected=$(awk '{print $1}' "$tmp_checksum")
    if command -v sha256sum &>/dev/null; then
      actual=$(sha256sum "$tmp_file" | awk '{print $1}')
    else
      actual=$(shasum -a 256 "$tmp_file" | awk '{print $1}')
    fi
    if [ "$expected" != "$actual" ]; then
      rm -f "$tmp_file" "$tmp_checksum"
      error "Checksum mismatch! Expected $expected, got $actual"
    fi
    dim "Checksum verified ✓"
  fi
  rm -f "$tmp_checksum"

  # Install
  local dest="${INSTALL_DIR}/${BINARY_NAME}"
  mv "$tmp_file" "$dest"
  chmod +x "$dest"

  info "✓ Installed to ${dest}"

  # Check PATH
  if ! echo "$PATH" | tr ':' '\n' | grep -q "^${INSTALL_DIR}$"; then
    echo ""
    echo "Add to your shell profile:"
    echo ""
    echo "  export PATH=\"${INSTALL_DIR}:\$PATH\""
    echo ""
  fi

  echo ""
  info "Next: run 'miner init' to configure"
  echo ""
}

main
