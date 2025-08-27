#!/bin/bash
# Build .deb package for AuroraFTP using native dpkg-deb
# This version doesn't require fpm and works with standard Debian tools

set -e

# Check if running from project root
if [[ ! -f "pyproject.toml" ]]; then
    echo "Error: Must run from project root directory"
    exit 1
fi

# Parse version from git or use default
if command -v git &> /dev/null && git rev-parse --git-dir > /dev/null 2>&1; then
    RAW_VERSION=$(git describe --tags --dirty --always 2>/dev/null || echo "0.1.0-dev")
    # Clean version for Debian packaging (remove 'v' prefix, convert dashes to dots, handle 'dirty')
    VERSION=$(echo "$RAW_VERSION" | sed 's/^v//' | sed 's/-/./g' | sed 's/\.dirty/.1/' | sed 's/\.g[0-9a-f]*//')
    # Ensure version is valid (contains only digits, dots, and letters)
    if ! echo "$VERSION" | grep -q '^[0-9][0-9a-zA-Z.]*$'; then
        VERSION="0.1.0.dev$(date +%Y%m%d)"
    fi
else
    VERSION="0.1.0"
fi

echo "Building AuroraFTP v${VERSION} .deb package..."

# Create build directory structure
BUILD_DIR="build/deb"
PACKAGE_DIR="${BUILD_DIR}/auroraftp_${VERSION}_all"
DEBIAN_DIR="${PACKAGE_DIR}/DEBIAN"
rm -rf "${BUILD_DIR}"
mkdir -p "${DEBIAN_DIR}"
mkdir -p "${PACKAGE_DIR}/usr/lib"
mkdir -p "${PACKAGE_DIR}/usr/bin"
mkdir -p "${PACKAGE_DIR}/usr/share/applications"
mkdir -p "${PACKAGE_DIR}/usr/share/pixmaps"
mkdir -p "${PACKAGE_DIR}/usr/share/doc/auroraftp"

# Create standalone virtual environment with all dependencies
echo "Creating standalone Python environment..."
python3 -m venv "${PACKAGE_DIR}/usr/lib/auroraftp"
source "${PACKAGE_DIR}/usr/lib/auroraftp/bin/activate"
pip install --upgrade pip setuptools wheel

# Install qasync first (critical dependency)
pip install qasync

# Install the application and its dependencies
pip install .

# Verify installation
if ! python -c "import auroraftp; print('AuroraFTP imported successfully')"; then
    echo "Error: Failed to install AuroraFTP in virtual environment"
    exit 1
fi

deactivate

# Create launcher script
cat > "${PACKAGE_DIR}/usr/bin/auroraftp" << 'EOF'
#!/bin/bash
# AuroraFTP launcher script

# Set up environment
export QT_QPA_PLATFORM=xcb
export PYTHONPATH=""

# Activate the bundled virtual environment
source /usr/lib/auroraftp/bin/activate

# Launch the application
exec python -m auroraftp.app "$@"
EOF

chmod +x "${PACKAGE_DIR}/usr/bin/auroraftp"

# Create desktop file
cat > "${PACKAGE_DIR}/usr/share/applications/auroraftp.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=AuroraFTP
Comment=Modern FTP/SFTP client for Linux
GenericName=FTP Client
Exec=auroraftp %U
Icon=auroraftp
Terminal=false
Categories=Network;FileTransfer;
MimeType=x-scheme-handler/ftp;x-scheme-handler/ftps;x-scheme-handler/sftp;
StartupNotify=true
StartupWMClass=auroraftp
EOF

# Create application icon
cat > "${PACKAGE_DIR}/usr/share/pixmaps/auroraftp.xpm" << 'EOF'
/* XPM */
static char *auroraftp[] = {
/* columns rows colors chars-per-pixel */
"48 48 16 1 ",
"  c #000040",
". c #000080", 
"X c #0000C0",
"o c #4040FF",
"O c #8080FF",
"+ c #C0C0FF",
"@ c #FFFFFF",
"# c #FFE0E0",
"$ c #FFC0C0",
"% c #FF8080",
"& c #FF4040",
"* c #FF0000",
"= c #C00000",
"- c #800000",
"; c #400000",
": c #200000",
/* pixels */
"                                                ",
"  ............................................  ",
"  .XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX. ",
"  .X@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@X. ",
"  .X@                                    @X. ",
"  .X@  OOOOOO  O   O  O@@@@O  OOOOOO  OOO@X. ",
"  .X@  O    O  O   O  O@  @O  O    O  O  O@X. ", 
"  .X@  O    O  O   O  @@@@@@  O    O  @@@@@X. ",
"  .X@  OOOOOO  O   O  O@  @O  OOOOOO  O   @X. ",
"  .X@  O   O   O   O  O@  @O  O   O   O   @X. ",
"  .X@  O    O  OOOOO  O@  @O  O    O  OOOO@X. ",
"  .X@                                    @X. ",
"  .X@            Aurora FTP              @X. ",
"  .X@         Modern FTP Client          @X. ",
"  .X@                                    @X. ",
"  .X@  ####  ######  ####              $ @X. ",
"  .X@  #  #     #    #   #             $ @X. ", 
"  .X@  #  #     #    ####              $ @X. ",
"  .X@  #  #     #    #                 $ @X. ",
"  .X@  ####     #    #              $$$$ @X. ",
"  .X@                              $    $@X. ",
"  .X@  %%%%%%%%%  %%%%%%%%  %%%%%  $    $@X. ",
"  .X@  %      %      %      %   %  $    $@X. ",
"  .X@  %      %      %      %   %  $    $@X. ",
"  .X@  %%%%%%%%%     %      %%%%%  $    $@X. ",
"  .X@  %             %      %      $    $@X. ",
"  .X@  %             %      %      $$$$$$ X. ",
"  .X@                                    @X. ",
"  .X@  *  *   ****   ****   *****        @X. ",
"  .X@  *  *  *    *  *   *  *            @X. ",
"  .X@  ****  *    *  ****   ****         @X. ",
"  .X@  *  *  *    *  *   *  *            @X. ",
"  .X@  *  *   ****   ****   *****        @X. ",
"  .X@                                    @X. ",
"  .X@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@X. ",
"  .XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX. ",
"  ............................................  ",
"                                                ",
"                                                ",
"                                                ",
"                                                ",
"                                                ",
"                                                ",
"                                                ",
"                                                ",
"                                                ",
"                                                ",
"                                                "
};
EOF

# Copy documentation
cp README.md "${PACKAGE_DIR}/usr/share/doc/auroraftp/"
cp LICENSE "${PACKAGE_DIR}/usr/share/doc/auroraftp/"

# Create changelog
cat > "${PACKAGE_DIR}/usr/share/doc/auroraftp/changelog.Debian" << EOF
auroraftp ($VERSION) unstable; urgency=medium

  * Initial release of AuroraFTP
  * Modern FTP/SFTP client with PyQt6 interface
  * Support for FTP, FTPS, and SFTP protocols
  * Standalone package with bundled dependencies

 -- AuroraFTP Team <team@auroraftp.dev>  $(date -R)
EOF

gzip -9 "${PACKAGE_DIR}/usr/share/doc/auroraftp/changelog.Debian"

# Create copyright file
cat > "${PACKAGE_DIR}/usr/share/doc/auroraftp/copyright" << EOF
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: auroraftp
Source: https://github.com/auroraftp/auroraftp

Files: *
Copyright: 2024 AuroraFTP Team
License: MIT

License: MIT
 Permission is hereby granted, free of charge, to any person obtaining a
 copy of this software and associated documentation files (the "Software"),
 to deal in the Software without restriction, including without limitation
 the rights to use, copy, modify, merge, publish, distribute, sublicense,
 and/or sell copies of the Software, and to permit persons to whom the
 Software is furnished to do so, subject to the following conditions:
 .
 The above copyright notice and this permission notice shall be included
 in all copies or substantial portions of the Software.
 .
 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
 OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
 FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
 DEALINGS IN THE SOFTWARE.
EOF

# Create control file (main package metadata)
cat > "${DEBIAN_DIR}/control" << EOF
Package: auroraftp
Version: $VERSION
Section: net
Priority: optional
Architecture: all
Depends: python3 (>= 3.11), python3-venv, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0, libxcb-shape0, libxcb-xfixes0, libxcb-xkb1, libxkbcommon-x11-0
Suggests: openssh-client
Maintainer: AuroraFTP Team <team@auroraftp.dev>
Description: Modern FTP/SFTP client for Linux
 AuroraFTP is a modern, clean FTP/SFTP client with feature parity to major
 FTP clients built with Python and PyQt6.
 .
 Features include:
  - Multiple protocol support (FTP, FTPS, SFTP)
  - Site manager with secure credential storage
  - Dual-pane interface with drag-and-drop
  - Transfer queue with pause/resume
  - Folder synchronization
  - Modern UI with light/dark themes
Homepage: https://github.com/auroraftp/auroraftp
EOF

# Create postinst script
cat > "${DEBIAN_DIR}/postinst" << 'EOF'
#!/bin/bash
set -e

case "$1" in
    configure)
        # Update desktop database if available
        if command -v update-desktop-database >/dev/null 2>&1; then
            update-desktop-database -q /usr/share/applications || true
        fi
        
        # Update MIME database if available
        if command -v update-mime-database >/dev/null 2>&1; then
            update-mime-database /usr/share/mime || true
        fi
        
        echo "AuroraFTP installed successfully!"
        echo "You can launch it from the applications menu or run 'auroraftp' in terminal."
        ;;
esac

exit 0
EOF

# Create prerm script  
cat > "${DEBIAN_DIR}/prerm" << 'EOF'
#!/bin/bash
set -e

case "$1" in
    remove|upgrade|deconfigure)
        # Clean up any running instances if needed
        ;;
esac

exit 0
EOF

# Create postrm script
cat > "${DEBIAN_DIR}/postrm" << 'EOF'
#!/bin/bash
set -e

case "$1" in
    remove)
        # Update desktop database if available
        if command -v update-desktop-database >/dev/null 2>&1; then
            update-desktop-database -q /usr/share/applications || true
        fi
        ;;
    purge)
        # Remove configuration files if needed
        echo "AuroraFTP configuration files remain in user home directories"
        echo "Remove ~/.config/auroraftp/ manually if desired"
        ;;
esac

exit 0
EOF

# Make scripts executable
chmod +x "${DEBIAN_DIR}/postinst" "${DEBIAN_DIR}/prerm" "${DEBIAN_DIR}/postrm"

# Calculate package size
INSTALLED_SIZE=$(du -sk "${PACKAGE_DIR}" | cut -f1)
echo "Installed-Size: ${INSTALLED_SIZE}" >> "${DEBIAN_DIR}/control"

# Build the package
echo "Building .deb package..."
DEB_FILE="dist/auroraftp_${VERSION}_all.deb"
dpkg-deb --build --root-owner-group "${PACKAGE_DIR}" "${DEB_FILE}"

echo "Package created: ${DEB_FILE}"

# Test the package
if command -v dpkg >/dev/null 2>&1; then
    echo ""
    echo "Package info:"
    dpkg --info "${DEB_FILE}"
    echo ""
    echo "Package contents (first 20 files):"
    dpkg --contents "${DEB_FILE}" | head -20
    if [[ $(dpkg --contents "${DEB_FILE}" | wc -l) -gt 20 ]]; then
        echo "... (truncated - total $(dpkg --contents "${DEB_FILE}" | wc -l) files)"
    fi
fi

echo ""
echo "Package size: $(du -h "${DEB_FILE}" | cut -f1)"
echo ""
echo "To install the package:"
echo "  sudo dpkg -i ${DEB_FILE}"
echo "  sudo apt-get install -f  # Fix any missing dependencies"
echo ""
echo "To uninstall:"
echo "  sudo apt remove auroraftp"
echo ""
echo "To test locally:"
echo "  sudo dpkg -i ${DEB_FILE} && auroraftp --help"