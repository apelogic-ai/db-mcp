#!/bin/sh
# dbmcp installer
# Usage: curl -fsSL https://raw.githubusercontent.com/apelogic-ai/db-mcp/main/scripts/install.sh | sh
#
# Environment variables:
#   DBMCP_VERSION  - Version to install (default: latest)
#   DBMCP_INSTALL  - Installation directory (default: ~/.local/bin)

set -e

REPO="apelogic-ai/db-mcp"

info()    { printf '\033[34m%s\033[0m\n' "$1"; }
success() { printf '\033[32m%s\033[0m\n' "$1"; }
warn()    { printf '\033[33m%s\033[0m\n' "$1"; }
error()   { printf '\033[31m%s\033[0m\n' "$1" >&2; }

detect_platform() {
    os=""
    arch=""

    case "$(uname -s)" in
        Darwin) os="macos" ;;
        Linux) os="linux" ;;
        MINGW*|MSYS*|CYGWIN*) os="windows" ;;
        *) error "Unsupported operating system: $(uname -s)"; exit 1 ;;
    esac

    case "$(uname -m)" in
        x86_64|amd64) arch="x64" ;;
        arm64|aarch64) arch="arm64" ;;
        *) error "Unsupported architecture: $(uname -m)"; exit 1 ;;
    esac

    printf '%s-%s' "$os" "$arch"
}

FALLBACK_VERSION="0.3.0"

get_latest_version() {
    version=$(curl -sL "https://api.github.com/repos/${REPO}/releases/latest" 2>/dev/null | \
        grep '"tag_name":' | \
        head -1 | \
        sed -E 's/.*"v([^"]+)".*/\1/')

    if [ -n "$version" ]; then
        printf '%s' "$version"
    else
        printf '%s' "$FALLBACK_VERSION"
    fi
}

download_binary() {
    version="$1"
    platform="$2"
    dest="$3"

    ext=""
    case "$platform" in
        windows-*) ext=".exe" ;;
    esac

    filename="dbmcp-${platform}${ext}"
    url="https://github.com/${REPO}/releases/download/v${version}/${filename}"

    info "Downloading dbmcp v${version} for ${platform}..."
    printf '  URL: %s\n' "$url"

    case "$platform" in
        macos-*)
            cache_dir="$HOME/.dbmcp/cache"
            mkdir -p "$cache_dir"
            cache_path="${cache_dir}/dbmcp-${version}${ext}"

            if ! curl -fsSL "$url" -o "$cache_path"; then
                error "Failed to download from ${url}"
                exit 1
            fi
            chmod +x "$cache_path"
            rm -f "$dest"
            ln -s "$cache_path" "$dest"
            ;;
        *)
            if ! curl -fsSL "$url" -o "$dest"; then
                error "Failed to download from ${url}"
                exit 1
            fi
            chmod +x "$dest"
            ;;
    esac
}

main() {
    printf '\033[34m'
    printf '╔════════════════════════════════════════╗\n'
    printf '║         dbmcp Installer                ║\n'
    printf '║   Database MCP Server for Claude       ║\n'
    printf '╚════════════════════════════════════════╝\n'
    printf '\033[0m\n'

    platform=$(detect_platform)
    printf 'Platform: \033[32m%s\033[0m\n' "$platform"

    version="${DBMCP_VERSION:-}"
    if [ -z "$version" ]; then
        printf 'Fetching latest version...\n'
        version=$(get_latest_version)
    fi
    printf 'Version: \033[32m%s\033[0m\n' "$version"

    install_dir="${DBMCP_INSTALL:-$HOME/.local/bin}"
    binary_path="${install_dir}/dbmcp"

    mkdir -p "$install_dir"

    download_binary "$version" "$platform" "$binary_path"

    if [ -x "$binary_path" ]; then
        success "✓ dbmcp installed successfully!"
        printf '  Location: %s\n\n' "$binary_path"

        case ":$PATH:" in
            *":$install_dir:"*) ;;
            *)
                warn "Note: ${install_dir} is not in your PATH."
                printf 'Add this to your shell profile:\n\n'
                printf '  \033[34mexport PATH="$HOME/.local/bin:$PATH"\033[0m\n\n'
                ;;
        esac

        success "Next steps:"
        printf '  1. Run '\''dbmcp init'\'' to configure your database connection\n'
        printf '  2. Restart Claude Desktop and start querying!\n\n'

        info "Commands:"
        printf '  dbmcp init [NAME]       Configure new connection\n'
        printf '  dbmcp status            Show current configuration\n'
        printf '  dbmcp list              List all connections\n'
        printf '  dbmcp --help            Show all commands\n\n'
    else
        error "Installation failed."
        exit 1
    fi
}

main "$@"
