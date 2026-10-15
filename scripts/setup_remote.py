"""Configure private Tailscale Serve after both computers have signed in."""
import json
from pathlib import Path
import re
import shutil
import subprocess


def main():
    if not shutil.which('tailscale'):
        raise SystemExit('Install Tailscale first, then run sudo tailscale up and sign in.')
    result = subprocess.run(['tailscale', 'status', '--json'], capture_output=True, text=True)
    if result.returncode:
        raise SystemExit('Tailscale is not ready. Run sudo tailscale up and sign in first.')
    status = json.loads(result.stdout)
    if status.get('BackendState') != 'Running':
        raise SystemExit('Tailscale is not signed in. Run sudo tailscale up first.')
    hostname = status.get('Self', {}).get('DNSName', '').rstrip('.').lower()
    if not re.fullmatch(r'[a-z0-9-]+\.[a-z0-9.-]+\.ts\.net', hostname):
        raise SystemExit('No Tailscale DNS name found. Enable MagicDNS in Tailscale settings.')
    root = Path(__file__).resolve().parents[1]
    config = root / 'data' / 'remote-host.txt'
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(hostname + '\n')
    print('Private website address: https://' + hostname, flush=True)
    print('If prompted, enable HTTPS using the Tailscale link. This uses private Serve, not public Funnel.', flush=True)
    subprocess.run(['sudo', 'tailscale', 'serve', '--bg', 'http://127.0.0.1:7860'], check=True)
    print('Restart AI Closet to load its private address. On your signed-in Mac, open https://' + hostname)


if __name__ == '__main__':
    main()
