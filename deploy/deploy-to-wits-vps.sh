#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SSH_CONFIG="${WITS_SSH_CONFIG:-$HOME/.ssh/config}"
REMOTE_HOST="${WITS_DEPLOY_HOST:-wits-vps}"
REMOTE_DIR="services/wits-keyboard"
REMOTE_ARCHIVE="/tmp/wits-keyboard-deploy.tar.gz"
TEMP_DIR="$(mktemp -d)"

cleanup() {
    rm -rf -- "$TEMP_DIR"
}
trap cleanup EXIT

for file in \
    "$PROJECT_DIR/web/index.html" \
    "$PROJECT_DIR/web/app.js" \
    "$PROJECT_DIR/web/styles.css" \
    "$PROJECT_DIR/deploy/compose.yaml" \
    "$PROJECT_DIR/deploy/nginx.conf"; do
    if [[ ! -s "$file" ]]; then
        printf 'Required deployment file is missing or empty: %s\n' "$file" >&2
        exit 1
    fi
done

install -d -m 0755 "$TEMP_DIR/release/web"
install -m 0644 "$PROJECT_DIR/web/index.html" "$TEMP_DIR/release/web/index.html"
install -m 0644 "$PROJECT_DIR/web/app.js" "$TEMP_DIR/release/web/app.js"
install -m 0644 "$PROJECT_DIR/web/styles.css" "$TEMP_DIR/release/web/styles.css"
install -m 0644 "$PROJECT_DIR/deploy/compose.yaml" "$TEMP_DIR/release/compose.yaml"
install -m 0644 "$PROJECT_DIR/deploy/nginx.conf" "$TEMP_DIR/release/nginx.conf"
tar -C "$TEMP_DIR/release" -czf "$TEMP_DIR/release.tar.gz" .

printf 'Preparing deployment directory on %s...\n' "$REMOTE_HOST"
ssh -F "$SSH_CONFIG" "$REMOTE_HOST" \
    'umask 077; install -d -m 0700 "$HOME/services/wits-keyboard/secrets"'

if ! ssh -F "$SSH_CONFIG" "$REMOTE_HOST" \
    'test -s "$HOME/services/wits-keyboard/secrets/tunnel-token"'; then
    printf 'Paste the copied Cloudflare Docker command or only its tunnel token.\n'
    printf 'It will not be echoed or saved in shell history.\n'
    IFS= read -r -s -p 'Docker command or tunnel token: ' TUNNEL_INPUT
    printf '\n'
    case "$TUNNEL_INPUT" in
        *" --token "*)
            TUNNEL_TOKEN="${TUNNEL_INPUT##* --token }"
            TUNNEL_TOKEN="${TUNNEL_TOKEN%%[[:space:]]*}"
            ;;
        *" --token="*)
            TUNNEL_TOKEN="${TUNNEL_INPUT##* --token=}"
            TUNNEL_TOKEN="${TUNNEL_TOKEN%%[[:space:]]*}"
            ;;
        *)
            TUNNEL_TOKEN="$TUNNEL_INPUT"
            ;;
    esac
    unset TUNNEL_INPUT
    if [[ "$TUNNEL_TOKEN" != eyJ* ]]; then
        printf 'The value does not look like a Cloudflare Tunnel token.\n' >&2
        exit 1
    fi
    umask 077
    printf '%s' "$TUNNEL_TOKEN" > "$TEMP_DIR/tunnel-token"
    unset TUNNEL_TOKEN
    scp -F "$SSH_CONFIG" -q "$TEMP_DIR/tunnel-token" \
        "$REMOTE_HOST:$REMOTE_ARCHIVE.token"
    ssh -F "$SSH_CONFIG" "$REMOTE_HOST" \
        'install -m 0600 /tmp/wits-keyboard-deploy.tar.gz.token "$HOME/services/wits-keyboard/secrets/tunnel-token" && rm -f /tmp/wits-keyboard-deploy.tar.gz.token'
else
    printf 'Reusing the existing tunnel token on %s.\n' "$REMOTE_HOST"
fi

printf 'Uploading static site and container configuration...\n'
scp -F "$SSH_CONFIG" -q "$TEMP_DIR/release.tar.gz" \
    "$REMOTE_HOST:$REMOTE_ARCHIVE"

ssh -F "$SSH_CONFIG" "$REMOTE_HOST" '
set -eu
TARGET="$HOME/services/wits-keyboard"
tar -xzf /tmp/wits-keyboard-deploy.tar.gz -C "$TARGET"
rm -f /tmp/wits-keyboard-deploy.tar.gz
chmod 0755 "$TARGET/web"
chmod 0644 "$TARGET/web/index.html" "$TARGET/web/app.js" "$TARGET/web/styles.css"
cd "$TARGET"
export WITS_UID="$(id -u)"
export WITS_GID="$(id -g)"
docker compose config --quiet
docker compose pull
docker compose up -d --force-recreate --remove-orphans
docker compose ps
'

printf '\nDeployment started. Cloudflare may take a minute to report the connector healthy.\n'
printf 'Expected public URL: https://kb.whitehorseit.com/\n'
