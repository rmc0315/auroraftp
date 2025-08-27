#!/bin/bash
# Build AppImage for AuroraFTP

set -e

# Check if running from project root
if [[ ! -f "pyproject.toml" ]]; then
    echo "Error: Must run from project root directory"
    exit 1
fi

# Parse version
if command -v git &> /dev/null && git rev-parse --git-dir > /dev/null 2>&1; then
    VERSION=$(git describe --tags --dirty --always 2>/dev/null || echo "0.1.0-dev")
else
    VERSION="0.1.0"
fi

echo "Building AuroraFTP v${VERSION} AppImage..."

# Create AppDir structure
APPDIR="build/appimage/AuroraFTP.AppDir"
rm -rf build/appimage
mkdir -p "${APPDIR}"

# Install Python environment
echo "Setting up Python environment..."
python -m venv "${APPDIR}/usr"
source "${APPDIR}/usr/bin/activate"

# Install package and dependencies
pip install --upgrade pip
pip install .
pip install PyQt6

# Create AppImage structure
mkdir -p "${APPDIR}/usr/share/applications"
mkdir -p "${APPDIR}/usr/share/icons/hicolor/256x256/apps"

# Create desktop file
cat > "${APPDIR}/auroraftp.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=AuroraFTP
Comment=Modern FTP/SFTP client
GenericName=FTP Client
Exec=auroraftp
Icon=auroraftp
Terminal=false
Categories=Network;FileTransfer;
MimeType=x-scheme-handler/ftp;x-scheme-handler/ftps;x-scheme-handler/sftp;
StartupNotify=true
EOF

cp "${APPDIR}/auroraftp.desktop" "${APPDIR}/usr/share/applications/"

# Create simple icon (PNG format for AppImage)
# In a real project, you'd have proper icons
convert -size 256x256 xc:lightblue \
    -gravity center -pointsize 24 -fill darkblue \
    -annotate +0+0 "AuroraFTP" \
    "${APPDIR}/auroraftp.png" 2>/dev/null || {
    echo "Warning: ImageMagick not available, creating placeholder icon"
    # Create a simple placeholder icon file
    echo "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==" | base64 -d > "${APPDIR}/auroraftp.png"
}

cp "${APPDIR}/auroraftp.png" "${APPDIR}/usr/share/icons/hicolor/256x256/apps/"

# Create AppRun script
cat > "${APPDIR}/AppRun" << 'EOF'
#!/bin/bash
# AppRun script for AuroraFTP

HERE="$(dirname "$(readlink -f "${0}")")"

# Set up environment
export PATH="${HERE}/usr/bin:${PATH}"
export PYTHONPATH="${HERE}/usr/lib/python3.11/site-packages:${PYTHONPATH}"
export LD_LIBRARY_PATH="${HERE}/usr/lib:${LD_LIBRARY_PATH}"

# Set Qt platform
export QT_QPA_PLATFORM_PLUGIN_PATH="${HERE}/usr/lib/python3.11/site-packages/PyQt6/Qt6/plugins/platforms"

# Run AuroraFTP
cd "${HERE}"
exec "${HERE}/usr/bin/python" -m auroraftp.app "$@"
EOF

chmod +x "${APPDIR}/AppRun"

# Download appimagetool if not available
APPIMAGETOOL="build/appimagetool-x86_64.AppImage"
if [[ ! -f "${APPIMAGETOOL}" ]]; then
    echo "Downloading appimagetool..."
    mkdir -p build
    wget -O "${APPIMAGETOOL}" \
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "${APPIMAGETOOL}"
fi

# Build AppImage
echo "Building AppImage..."
mkdir -p dist
ARCH=x86_64 "${APPIMAGETOOL}" "${APPDIR}" "dist/AuroraFTP-${VERSION}-x86_64.AppImage"

echo "AppImage created: dist/AuroraFTP-${VERSION}-x86_64.AppImage"

# Make it executable
chmod +x "dist/AuroraFTP-${VERSION}-x86_64.AppImage"

echo ""
echo "To run the AppImage:"
echo "  ./dist/AuroraFTP-${VERSION}-x86_64.AppImage"
echo ""
echo "To install system-wide:"
echo "  sudo cp dist/AuroraFTP-${VERSION}-x86_64.AppImage /usr/local/bin/auroraftp"