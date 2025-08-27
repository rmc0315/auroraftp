#!/bin/bash
# Build .deb package for AuroraFTP

set -e

# Check dependencies
command -v fpm >/dev/null 2>&1 || {
    echo "Error: fpm is required to build .deb packages"
    echo "Install with: gem install --no-document fpm"
    echo "You may need to install ruby first: sudo apt install ruby ruby-dev"
    exit 1
}

# Check if running from project root
if [[ ! -f "pyproject.toml" ]]; then
    echo "Error: Must run from project root directory"
    exit 1
fi

# Parse version from pyproject.toml or use git
if command -v git &> /dev/null && git rev-parse --git-dir > /dev/null 2>&1; then
    VERSION=$(git describe --tags --dirty --always 2>/dev/null || echo "0.1.0-dev")
else
    VERSION="0.1.0"
fi

echo "Building AuroraFTP v${VERSION} .deb package..."

# Create build directory
BUILD_DIR="build/deb"
PACKAGE_DIR="${BUILD_DIR}/auroraftp"
rm -rf "${BUILD_DIR}"
mkdir -p "${PACKAGE_DIR}"

# Create virtual environment and install all dependencies
echo "Creating standalone Python environment..."
python -m venv "${PACKAGE_DIR}/usr/lib/auroraftp"
source "${PACKAGE_DIR}/usr/lib/auroraftp/bin/activate"
pip install --upgrade pip setuptools wheel
pip install .

# Create application structure
mkdir -p "${PACKAGE_DIR}/usr/bin"
mkdir -p "${PACKAGE_DIR}/usr/share/applications"
mkdir -p "${PACKAGE_DIR}/usr/share/pixmaps"
mkdir -p "${PACKAGE_DIR}/usr/share/doc/auroraftp"

# Create launcher script
cat > "${PACKAGE_DIR}/usr/bin/auroraftp" << 'EOF'
#!/bin/bash
# AuroraFTP launcher script

# Activate the bundled virtual environment
source /usr/lib/auroraftp/bin/activate
exec python -m auroraftp.app "$@"
EOF

chmod +x "${PACKAGE_DIR}/usr/bin/auroraftp"

# Create desktop file
cat > "${PACKAGE_DIR}/usr/share/applications/auroraftp.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=AuroraFTP
Comment=Modern FTP/SFTP client
GenericName=FTP Client
Exec=auroraftp %U
Icon=auroraftp
Terminal=false
Categories=Network;FileTransfer;
MimeType=x-scheme-handler/ftp;x-scheme-handler/ftps;x-scheme-handler/sftp;
StartupNotify=true
EOF

# Create simple icon (placeholder)
cat > "${PACKAGE_DIR}/usr/share/pixmaps/auroraftp.xpm" << 'EOF'
/* XPM */
static char *auroraftp[] = {
/* columns rows colors chars-per-pixel */
"32 32 4 1 ",
"  c black",
". c blue", 
"X c white",
"o c gray",
/* pixels */
"                                ",
"  ............................  ",
"  .XXXXXXXXXXXXXXXXXXXXXXXXXXXX. ",
"  .XXXXXXXXXXXXXXXXXXXXXXXXXXXX. ",
"  .XXooooooooooooooooooooooooXX. ",
"  .XXo                    ooXX. ",
"  .XXo   AURORAFTP        ooXX. ",
"  .XXo                    ooXX. ",
"  .XXooooooooooooooooooooooooXX. ",
"  .XXXXXXXXXXXXXXXXXXXXXXXXXXXX. ",
"  .XXXXXXXXXXXXXXXXXXXXXXXXXXXX. ",
"  ............................  ",
"                                ",
"                                ",
"                                ",
"                                ",
"                                ",
"                                ",
"                                ",
"                                ",
"                                ",
"                                ",
"                                ",
"                                ",
"                                ",
"                                ",
"                                ",
"                                ",
"                                ",
"                                ",
"                                ",
"                                "
};
EOF

# Copy documentation
cp README.md "${PACKAGE_DIR}/usr/share/doc/auroraftp/"
cp LICENSE "${PACKAGE_DIR}/usr/share/doc/auroraftp/" 2>/dev/null || echo "Warning: LICENSE file not found"

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

# Build package with fpm
echo "Creating .deb package..."
fpm -s dir -t deb \
    -n auroraftp \
    -v "${VERSION}" \
    --description "Modern FTP/SFTP client for Linux" \
    --url "https://github.com/auroraftp/auroraftp" \
    --maintainer "AuroraFTP Team <team@auroraftp.dev>" \
    --license "MIT" \
    --category "net" \
    --depends "python3 (>= 3.11)" \
    --depends "python3-venv" \
    --depends "libxcb-cursor0" \
    --depends "libxcb-icccm4" \
    --depends "libxcb-image0" \
    --depends "libxcb-keysyms1" \
    --depends "libxcb-randr0" \
    --depends "libxcb-render-util0" \
    --depends "libxcb-shape0" \
    --depends "libxcb-xfixes0" \
    --depends "libxcb-xkb1" \
    --depends "libxkbcommon-x11-0" \
    --architecture "all" \
    --deb-compression bzip2 \
    --deb-suggests "python3-keyring" \
    --after-install scripts/postinst.sh \
    --before-remove scripts/prerm.sh \
    -C "${PACKAGE_DIR}" \
    --package "dist/auroraftp_${VERSION}_all.deb" \
    .

echo "Package created: dist/auroraftp_${VERSION}_all.deb"

# Create post-install script
mkdir -p scripts
cat > scripts/postinst.sh << 'EOF'
#!/bin/bash
# Post-installation script

set -e

# Update desktop database
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q
fi

# Update MIME database
if command -v update-mime-database >/dev/null 2>&1; then
    update-mime-database /usr/share/mime
fi

echo "AuroraFTP installed successfully!"
echo "You can launch it from the applications menu or run 'auroraftp' in terminal."
EOF

# Create pre-removal script
cat > scripts/prerm.sh << 'EOF'
#!/bin/bash
# Pre-removal script

set -e

# Nothing special needed for removal
exit 0
EOF

chmod +x scripts/postinst.sh scripts/prerm.sh

# Test the package
echo "Testing package installation..."
if command -v dpkg >/dev/null 2>&1; then
    echo "Package info:"
    dpkg --info "dist/auroraftp_${VERSION}_all.deb"
    echo ""
    echo "Package contents:"
    dpkg --contents "dist/auroraftp_${VERSION}_all.deb" | head -20
    if [[ $(dpkg --contents "dist/auroraftp_${VERSION}_all.deb" | wc -l) -gt 20 ]]; then
        echo "... (truncated)"
    fi
fi

echo ""
echo "To install the package:"
echo "  sudo dpkg -i dist/auroraftp_${VERSION}_all.deb"
echo "  sudo apt-get install -f  # Fix any missing dependencies"
echo ""
echo "To uninstall:"
echo "  sudo apt remove auroraftp"