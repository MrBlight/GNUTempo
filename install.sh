#!/bin/bash
# GNUTempo Installation Script
# Detects OS and installs as a system-wide command
# Licensed under GPLv3

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_NAME="gnutempo"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == "linux-gnu"* ]] || [[ "$OSTYPE" == "linux-musl"* ]]; then
        echo "linux"
    elif [[ "$OSTYPE" == "freebsd"* ]] || [[ "$OSTYPE" == "openbsd"* ]] || [[ "$OSTYPE" == "netbsd"* ]]; then
        echo "bsd"
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
        echo "windows"
    else
        echo "unknown"
    fi
}

check_dependencies() {
    local missing=()
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        missing+=("python3")
    fi
    
    # Check pip
    if ! command -v pip3 &> /dev/null && ! command -v pip &> /dev/null; then
        missing+=("pip3")
    fi
    
    # Check pygame (try to import)
    if ! python3 -c "import pygame" 2>/dev/null; then
        log_info "pygame not found, will install via pip"
    fi
    
    if [ ${#missing[@]} -ne 0 ]; then
        log_error "Missing dependencies: ${missing[*]}"
        log_info "Please install them first:"
        case $(detect_os) in
            macos)
                echo "  brew install python3"
                ;;
            linux)
                echo "  Debian/Ubuntu: sudo apt install python3 python3-pip"
                echo "  Fedora: sudo dnf install python3 python3-pip"
                echo "  Arch: sudo pacman -S python python-pip"
                ;;
            bsd)
                echo "  FreeBSD: pkg install python3 py39-pip"
                echo "  OpenBSD: pkg_add python3"
                ;;
        esac
        exit 1
    fi
}

install_pygame() {
    log_info "Installing pygame..."
    if command -v pip3 &> /dev/null; then
        pip3 install --user pygame 2>/dev/null || pip3 install pygame
    else
        pip install --user pygame 2>/dev/null || pip install pygame
    fi
    log_success "pygame installed"
}

get_install_path() {
    local os=$(detect_os)
    case $os in
        macos|linux|bsd)
            # Try user-local first, then system-wide
            if [ "$EUID" -eq 0 ]; then
                echo "/usr/local/bin"
            else
                # Check if ~/.local/bin is in PATH
                if [[ ":$PATH:" == *":$HOME/.local/bin:"* ]]; then
                    echo "$HOME/.local/bin"
                else
                    log_warn "$HOME/.local/bin not in PATH"
                    log_info "Installing to $HOME/.local/bin anyway"
                    log_info "Add this to your shell config (~/.bashrc, ~/.zshrc):"
                    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
                    echo "$HOME/.local/bin"
                fi
            fi
            ;;
        windows)
            echo "$HOME/AppData/Roaming/Python/Scripts"
            ;;
    esac
}

create_wrapper_script() {
    local install_path="$1"
    local wrapper_path="$install_path/$INSTALL_NAME"
    
    log_info "Creating wrapper script at $wrapper_path"
    
    cat > "$wrapper_path" << 'WRAPPER_EOF'
#!/usr/bin/env python3
"""
GNUTempo - Terminal Metronome Wrapper
Launches the metronome with optional flags
"""

import sys
import os
import subprocess
import argparse

def main():
    parser = argparse.ArgumentParser(
        prog='gnutempo',
        description='GNUTempo - Terminal Minimalist Metronome',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  gnutempo                          Start interactive mode
  gnutempo start                    Start interactive mode
  gnutempo --bpm 120 --time 4/4     Quick start with settings
  gnutempo --preset rock            Use preset rhythm
  gnutempo --debug                  Enable debug mode
  gnutempo --list-presets           Show available presets
  gnutempo --tap                    Tap tempo mode
  gnutempo --version                Show version
  gnutempo --help                   Show this help

For full interactive commands, just run 'gnutempo' and type 'help'
"""
    )
    
    parser.add_argument('action', nargs='?', default='start',
                       choices=['start', 'tap', 'quick'],
                       help='Action to perform (default: start)')
    parser.add_argument('--bpm', '-b', type=float, default=None,
                       help='Starting BPM (default: 120)')
    parser.add_argument('--time', '-t', type=str, default=None,
                       help='Time signature (default: 4/4)')
    parser.add_argument('--preset', '-p', type=str, default=None,
                       help='Use preset rhythm (rock, jazz, bossa, waltz, funk)')
    parser.add_argument('--debug', '-d', action='store_true',
                       help='Enable debug/diagnostic mode')
    parser.add_argument('--list-presets', action='store_true',
                       help='List available presets')
    parser.add_argument('--version', '-v', action='store_true',
                       help='Show version')
    parser.add_argument('--no-sound-check', action='store_true',
                       help='Skip audio file verification')
    
    args = parser.parse_args()
    
    # Handle --version
    if args.version:
        print("GNUTempo v1.1.0")
        print("Terminal Minimalist Metronome")
        print("Licensed under GPLv3")
        return 0
    
    # Handle --list-presets
    if args.list_presets:
        print("Available presets:")
        print("  rock      - Basic rock pattern (4/4)")
        print("  jazz      - Swing pattern (4/4)")
        print("  bossa     - Bossa nova pattern (4/4)")
        print("  waltz     - Waltz pattern (3/4)")
        print("  funk      - Funk pattern (4/4)")
        print("  samba     - Samba pattern (2/4)")
        return 0
    
    # Find the main script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Try multiple locations
    possible_paths = [
        os.path.join(script_dir, 'OpenTempo.py'),
        os.path.join(script_dir, 'gnutempo.py'),
        '/usr/local/share/gnutempo/OpenTempo.py',
        '/usr/share/gnutempo/OpenTempo.py',
        os.path.expanduser('~/.local/share/gnutempo/OpenTempo.py'),
    ]
    
    main_script = None
    for path in possible_paths:
        if os.path.exists(path):
            main_script = path
            break
    
    if not main_script:
        print("Error: Could not find OpenTempo.py", file=sys.stderr)
        print("Looked in:", file=sys.stderr)
        for path in possible_paths:
            print(f"  {path}", file=sys.stderr)
        return 1
    
    # Build command-line args for the main script
    cmd_args = [sys.executable, main_script]
    
    if args.debug:
        cmd_args.append('--debug')
    
    if args.no_sound_check:
        cmd_args.append('--no-sound-check')
    
    # For quick start with bpm/time
    if args.action == 'quick' or (args.bpm or args.time or args.preset):
        cmd_args.append('--quick-start')
        if args.bpm:
            cmd_args.extend(['--bpm', str(args.bpm)])
        if args.time:
            cmd_args.extend(['--time', args.time])
        if args.preset:
            cmd_args.extend(['--preset', args.preset])
    
    # Execute the main script
    try:
        os.execv(sys.executable, cmd_args)
    except Exception as e:
        print(f"Error launching GNUTempo: {e}", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
WRAPPER_EOF
    
    chmod +x "$wrapper_path"
    log_success "Wrapper script created"
}

install_system_files() {
    local os=$(detect_os)
    
    case $os in
        linux|bsd)
            if [ "$EUID" -eq 0 ]; then
                log_info "Installing desktop integration files..."
                
                # Create share directory
                mkdir -p /usr/local/share/gnutempo
                
                # Copy main files
                cp "$SCRIPT_DIR/OpenTempo.py" /usr/local/share/gnutempo/
                cp "$SCRIPT_DIR/"*.ogg /usr/local/share/gnutempo/ 2>/dev/null || true
                cp "$SCRIPT_DIR/"*.json /usr/local/share/gnutempo/ 2>/dev/null || true
                
                # Install man page if it exists
                if [ -f "$SCRIPT_DIR/gnutempo.1" ]; then
                    mkdir -p /usr/local/share/man/man1
                    cp "$SCRIPT_DIR/gnutempo.1" /usr/local/share/man/man1/
                    gzip -f /usr/local/share/man/man1/gnutempo.1 2>/dev/null || true
                    log_info "Man page installed"
                fi
                
                log_success "System files installed"
            fi
            ;;
        macos)
            if [ "$EUID" -eq 0 ]; then
                log_info "Installing to /usr/local/share/gnutempo..."
                mkdir -p /usr/local/share/gnutempo
                cp "$SCRIPT_DIR/OpenTempo.py" /usr/local/share/gnutempo/
                cp "$SCRIPT_DIR/"*.ogg /usr/local/share/gnutempo/ 2>/dev/null || true
                cp "$SCRIPT_DIR/"*.json /usr/local/share/gnutempo/ 2>/dev/null || true
                log_success "System files installed"
            fi
            ;;
    esac
}

print_post_install() {
    local os=$(detect_os)
    local install_path="$1"
    
    echo ""
    log_success "GNUTempo installation complete!"
    echo ""
    echo "You can now run GNUTempo by typing:"
    echo "  $INSTALL_NAME"
    echo ""
    
    case $os in
        macos|linux|bsd)
            if [[ "$install_path" == "$HOME"* ]]; then
                echo "Note: The install path ($install_path) should be in your PATH."
                echo "If '$INSTALL_NAME' command is not found, add this to your ~/.bashrc or ~/.zshrc:"
                echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
                echo ""
                echo "Then run: source ~/.bashrc  (or source ~/.zshrc)"
            elif [ "$EUID" -ne 0 ]; then
                echo "For system-wide installation, re-run with sudo:"
                echo "  sudo ./install.sh"
            fi
            ;;
        windows)
            echo "On Windows, you may need to add the Scripts folder to PATH:"
            echo "  $install_path"
            ;;
    esac
    
    echo ""
    echo "Quick start examples:"
    echo "  $INSTALL_NAME                 # Interactive mode"
    echo "  $INSTALL_NAME --bpm 120       # Start at 120 BPM"
    echo "  $INSTALL_NAME --preset rock   # Use rock preset"
    echo "  $INSTALL_NAME --debug         # Debug mode"
    echo "  $INSTALL_NAME --help          # All options"
    echo ""
}

# Main installation flow
main() {
    echo "╔════════════════════════════════════════╗"
    echo "║     GNUTempo Installation Script       ║"
    echo "╚════════════════════════════════════════╝"
    echo ""
    
    local os=$(detect_os)
    log_info "Detected OS: $os"
    
    if [ "$os" == "unknown" ]; then
        log_error "Could not detect your operating system"
        exit 1
    fi
    
    check_dependencies
    install_pygame
    
    local install_path=$(get_install_path)
    mkdir -p "$install_path"
    
    create_wrapper_script "$install_path"
    install_system_files
    
    print_post_install "$install_path"
}

main "$@"
