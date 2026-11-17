#!/bin/sh
# Ensayo aislado OAuth: no modifica el addon, rclone.conf ni servicios.
set -eu
umask 077

REF="1c93724af66532c627dfe0fb5e943f7a733ed253"
URL="https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/$REF/service.cloud.masqelec"
BASE="/tmp/masqelec-oauth-lab"
mkdir -p "$BASE/lib" "$BASE/tools"
chmod 700 "$BASE" "$BASE/lib" "$BASE/tools"

for name in lib/chacha_pure.py lib/rclone_conf_merge.py lib/rclone_token_policy.py tools/rclone_oauth_pilot.py; do
    dst="$BASE/$name"
    tmp="$dst.download"
    rm -f "$tmp"
    if ! wget -q "$URL/$name" -O "$tmp"; then
        rm -f "$tmp"
        echo "LAB_SETUP=DOWNLOAD_FAILED"
        exit 1
    fi
    if [ ! -s "$tmp" ]; then
        rm -f "$tmp"
        echo "LAB_SETUP=EMPTY_FILE"
        exit 1
    fi
    chmod 600 "$tmp"
    mv "$tmp" "$dst"
done

# Configuración mínima de laboratorio: solo lectura de cloud/develop.
cat >"$BASE/lib/constants.py" <<'EOF'
CLOUD_BRANCH = "develop"
CLOUD_RAW_BASE = "https://raw.githubusercontent.com/masQelec/cloud.masqelec/develop"
EOF
: >"$BASE/lib/__init__.py"

if ! python3 -m py_compile "$BASE/lib/"*.py "$BASE/tools/rclone_oauth_pilot.py"; then
    echo "LAB_SETUP=SYNTAX_FAILED"
    exit 1
fi

echo "LAB_SETUP=PASS"
echo "LAB_CODE_REF=$REF"
echo "LAB_LIVE_CONFIG_MODIFIED=NO"
echo "LAB_ADDON_MODIFIED=NO"
echo "LAB_GITHUB_UPLOAD=NO"
echo "Ejecutar: python3 /tmp/masqelec-oauth-lab/tools/rclone_oauth_pilot.py"
