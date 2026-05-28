#!/bin/bash
# ============================================================
# OneShot WebUI — Cross-platform Installer
# Platform: Termux, Kali, Ubuntu, Debian, Arch, Fedora
# Creates global command 'opx-oneshot' usable from anywhere
# ============================================================

set -e

REPO_URL="https://github.com/OP-AMINUL-FF/opx-oneshot.git"
INSTALL_DIR="${OPX_DIR:-$HOME/opx-oneshot}"
CMD_NAME="opx-oneshot"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'
info() { echo -e "${CYAN}[*]${NC} $1"; }
succ() { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[-]${NC} $1"; }

# ============================================================
# Detect Platform
# ============================================================
detect_platform() {
    if [ -n "$PREFIX" ] && [ -d "$PREFIX" ]; then echo "termux"
    elif command -v apt &>/dev/null; then
        if grep -qi kali /etc/os-release 2>/dev/null; then echo "kali"
        else echo "debian"; fi
    elif command -v pacman &>/dev/null; then echo "arch"
    elif command -v dnf &>/dev/null; then echo "fedora"
    else echo "unknown"; fi
}

get_python() {
    if command -v python3 &>/dev/null; then echo "python3"
    elif command -v python &>/dev/null; then echo "python"
    else echo ""; fi
}

# ============================================================
# Install Dependencies
# ============================================================
install_deps() {
    local plat="$1"
    info "Installing dependencies for: $plat"

    case "$plat" in
        termux)
            pkg update -y
            pkg install -y root-repo 2>/dev/null || true
            pkg install -y python wpa-supplicant pixiewps iw openssl git binutils \
                           tsu iproute2 wireless-tools
            pip install flask wcwidth
            ;;
        kali|debian)
            sudo apt update -y
            sudo apt install -y python3 python3-pip python3-tk python3-wcwidth \
                               wpasupplicant pixiewps iw wireless-tools iproute2 git
            sudo pip3 install flask
            ;;
        arch)
            sudo pacman -Syu --noconfirm
            sudo pacman -S --noconfirm python python-pip python-tk \
                               wpa_supplicant pixiewps iw wireless_tools iproute2 git
            sudo pip install flask wcwidth
            ;;
        fedora)
            sudo dnf install -y python3 python3-pip python3-tkinter \
                               wpa_supplicant pixiewps iw wireless-tools iproute git
            sudo pip3 install flask wcwidth
            ;;
        *)
            err "Unknown platform. Install manually."
            info "Required: python3, pip, wpa_supplicant, pixiewps, iw, wireless-tools,"
            info "         iproute2, tkinter, wcwidth, flask"
            exit 1
            ;;
    esac
    succ "Dependencies installed"
}

# ============================================================
# Clone / Update Repo
# ============================================================
clone_repo() {
    if [ -d "$INSTALL_DIR" ]; then
        warn "Directory exists. Updating..."
        cd "$INSTALL_DIR" && git pull 2>/dev/null || true
    else
        info "Cloning into $INSTALL_DIR..."
        git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
    fi
    succ "Files ready at $INSTALL_DIR"
}

# ============================================================
# Create Global Command
# ============================================================
create_global_cmd() {
    local plat="$1"
    local cmd_path

    if [ "$plat" = "termux" ]; then
        cmd_path="$PREFIX/bin/$CMD_NAME"
    else
        cmd_path="/usr/local/bin/$CMD_NAME"
    fi

    info "Creating global command: $cmd_path"

    local tmpfile
    tmpfile="$(mktemp)"

    cat > "$tmpfile" << 'SCRIPT'
#!/bin/bash
# OneShot WebUI — Global command (installed by install.sh)
INSTALL_DIR="__INSTALL_DIR__"
CMD_NAME="opx-oneshot"

detect_install_dir() {
    [ -d "$INSTALL_DIR" ] && return 0
    for d in "$HOME/opx-oneshot" "/data/data/com.termux/files/home/opx-oneshot" \
             "/opt/opx-oneshot" "/root/opx-oneshot"; do
        if [ -d "$d" ]; then INSTALL_DIR="$d"; return 0; fi
    done
    return 1
}

# ---- REMOVE ----
remove_all() {
    echo "[*] Removing OneShot WebUI..."
    local dirs=("$INSTALL_DIR")
    [ -d "$HOME/opx-oneshot" ] && dirs+=("$HOME/opx-oneshot")
    [ -d "/data/data/com.termux/files/home/opx-oneshot" ] && dirs+=("/data/data/com.termux/files/home/opx-oneshot")
    [ -d "/root/opx-oneshot" ] && dirs+=("/root/opx-oneshot")

    # Remove global command
    for c in "/usr/local/bin/$CMD_NAME" "/data/data/com.termux/files/usr/bin/$CMD_NAME" \
             "$PREFIX/bin/$CMD_NAME" 2>/dev/null; do
        [ -f "$c" ] && rm -f "$c" 2>/dev/null || sudo rm -f "$c" 2>/dev/null || true
    done

    # Remove all found dirs
    for dir in "${dirs[@]}"; do
        [ ! -d "$dir" ] && continue
        echo "[*] Removing $dir..."
        # Method 1: normal
        rm -rf "$dir" 2>/dev/null && echo "[+] Removed: $dir" && continue
        # Method 2: sudo
        sudo rm -rf "$dir" 2>/dev/null && echo "[+] Removed (sudo): $dir" && continue
        # Method 3: chmod + rm
        chmod -R 777 "$dir" 2>/dev/null; rm -rf "$dir" 2>/dev/null && echo "[+] Removed (chmod): $dir" && continue
        # Method 4: sudo chmod + rm
        sudo chmod -R 777 "$dir" 2>/dev/null; sudo rm -rf "$dir" 2>/dev/null && echo "[+] Removed (sudo+chmod): $dir" && continue
        # Method 5: chattr
        sudo chattr -R -i "$dir" 2>/dev/null; sudo rm -rf "$dir" 2>/dev/null && echo "[+] Removed (chattr): $dir" && continue
        # Method 6: Termux from root
        if command -v termux-setup-storage &>/dev/null; then
            cd /data/data/com.termux/files/home 2>/dev/null
            rm -rf "$dir" 2>/dev/null && echo "[+] Removed (Termux home): $dir" && continue
        fi
        # Method 7: busybox
        if command -v busybox &>/dev/null; then
            busybox rm -rf "$dir" 2>/dev/null && echo "[+] Removed (busybox): $dir" && continue
        fi
        warn "Could not remove: $dir"
    done
    echo "[+] Cleanup complete"
    exit 0
}

# ---- UPDATE ----
do_update() {
    detect_install_dir || { echo "[-] Install dir not found"; exit 1; }
    echo "[*] Updating OneShot in $INSTALL_DIR..."
    cd "$INSTALL_DIR" || exit 1
    git pull
    echo "[+] Update complete"
    exit 0
}

# ---- START ----
start_webui() {
    detect_install_dir || { echo "[-] Install dir not found"; exit 1; }

    local py
    for p in python3 python; do
        command -v "$p" &>/dev/null && { py="$p"; break; }
    done
    [ -z "$py" ] && { echo "[-] Python not found"; exit 1; }

    # Handle port argument
    local port="5000"
    local rest_args=()
    for arg in "$@"; do
        if [[ "$arg" =~ ^[0-9]+$ ]]; then port="$arg"
        else rest_args+=("$arg"); fi
    done

    if [ "$(id -u)" -ne 0 ]; then
        if command -v tsu &>/dev/null; then
            echo "[*] Starting with tsu..."
            exec tsu -c "cd '$INSTALL_DIR' && $py oneshot_web.py $port"
        elif command -v sudo &>/dev/null; then
            echo "[*] Starting with sudo..."
            exec sudo "$py" "$INSTALL_DIR/oneshot_web.py" "$port"
        else
            echo "[-] Root required. Run with sudo or tsu."
            exit 1
        fi
    else
        cd "$INSTALL_DIR" 2>/dev/null || { echo "[-] Install dir not found"; exit 1; }
        exec "$py" oneshot_web.py "$port"
    fi
}

# ============================================================
case "${1:-}" in
    -u|--update|update) do_update ;;
    -r|--remove|remove|uninstall) remove_all ;;
    -h|--help|help)
        echo "OneShot WebUI — WPS attack tool"
        echo "Usage: $CMD_NAME [OPTION]"
        echo "  (no option)   Start WebUI (http://127.0.0.1:5000)"
        echo "  <port>        Start on custom port"
        echo "  -u, --update  Update to latest version"
        echo "  -r, --remove  Remove OneShot completely"
        echo "  -h, --help    Show this help"
        ;;
    *) start_webui "$@" ;;
esac
SCRIPT

    # Replace placeholder
    sed -i "s|__INSTALL_DIR__|$INSTALL_DIR|g" "$tmpfile"

    if [ "$plat" = "termux" ]; then
        cp "$tmpfile" "$cmd_path"
    else
        sudo cp "$tmpfile" "$cmd_path"
    fi
    sudo chmod +x "$cmd_path"
    rm -f "$tmpfile"

    succ "Global command created: $cmd_path"
    succ "  Run 'opx-oneshot'        → start WebUI"
    succ "  Run 'opx-oneshot -u'     → update to latest"
    succ "  Run 'opx-oneshot -r'     → remove completely"
    succ "  Run 'opx-oneshot 8080'   → start on port 8080"
}

# ============================================================
# Show Info
# ============================================================
show_info() {
    local plat="$1"
    local cmd_path
    [ "$plat" = "termux" ] && cmd_path="$PREFIX/bin/$CMD_NAME" || cmd_path="/usr/local/bin/$CMD_NAME"
    local py; py="$(get_python)"

    echo ""
    succ "=== Installation Complete ==="
    echo ""
    echo "  Platform:     $plat"
    echo "  Install dir:  $INSTALL_DIR"
    echo "  Command:      $cmd_path"
    echo "  Python:       $py"
    echo ""
    echo "  ┌─────────────────────────────────────────┐"
    echo "  │  opx-oneshot        → Start WebUI       │"
    echo "  │  opx-oneshot 8080   → Start on port 8080│"
    echo "  │  opx-oneshot -u     → Update to latest  │"
    echo "  │  opx-oneshot -r     → Remove all files  │"
    echo "  └─────────────────────────────────────────┘"
    echo ""
    echo "  Open browser: http://127.0.0.1:5000"
    echo ""
}

# ============================================================
# Main
# ============================================================
main() {
    local plat; plat="$(detect_platform)"

    echo ""
    echo "╔═══════════════════════════════════════════╗"
    echo "║     OneShot WebUI — Cross-platform Installer "
    echo "╚═══════════════════════════════════════════╝"
    echo ""

    # Handle --remove for install.sh itself
    if [ "${1:-}" = "--remove" ] || [ "${1:-}" = "-r" ]; then
        if detect_install_dir 2>/dev/null; then
            # Call the global command's remove logic
            if command -v "$CMD_NAME" &>/dev/null; then
                exec "$CMD_NAME" -r
            fi
        fi
        err "OneShot not installed or command not found"
        exit 1
    fi

    info "Detected platform: $plat"
    info "Install directory: $INSTALL_DIR"
    echo ""

    install_deps "$plat"
    clone_repo
    create_global_cmd "$plat"
    show_info "$plat"
}

main "$@"
