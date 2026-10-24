# `kb.whitehorseit.com` deployment

This deployment keeps Nextcloud AIO untouched. The static page and a remotely
managed Cloudflare Tunnel run on their own Docker network and publish no host
ports.

## Cloudflare setup

1. In Cloudflare, delete the existing `kb` A record. A Tunnel public hostname
   will replace it with a proxied CNAME.
2. Go to **Networking > Tunnels**, create a remotely managed tunnel named
   `wits-keyboard`, and choose the Docker connector instructions.
3. Add a published application route:
   - Hostname: `kb.whitehorseit.com`
   - Service URL: `http://wits-keyboard-web:8080`
4. Copy the Docker installation command using its copy button. Do not run it
   directly or paste it into chat. The deployment script accepts either the
   full copied command or only its `eyJ...` token.

## Deploy

From the `wits-keyboard` project directory, run:

```bash
bash deploy/deploy-to-wits-vps.sh
```

The first run prompts invisibly for the copied Docker command or tunnel token.
Later deployments reuse the protected token file on the VPS.

The SSH host alias defaults to `wits-vps` and the SSH config to `~/.ssh/config`.
Override them with `WITS_DEPLOY_HOST` and `WITS_SSH_CONFIG` if yours differ.
