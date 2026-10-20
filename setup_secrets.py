"""Create fresh server-side staging secrets; never ship real secrets in the ZIP."""
import os
from pathlib import Path
import secrets
from cryptography.fernet import Fernet

destination = Path(__file__).parent / '.env'
if destination.exists():
    raise SystemExit('.env already exists. It was NOT overwritten. Keep its original key to decrypt saved playlists.')
with destination.open('x', encoding='ascii') as f:
    f.write('# Keep private; back up with database; do not commit to source control.\n')
    f.write('TUNELY_ENV=production\n')
    f.write('TUNELY_FERNET_KEY=' + Fernet.generate_key().decode() + '\n')
    code = secrets.token_urlsafe(24)
    f.write('TUNELY_SIGNUP_CODE=' + code + '\n')
try:
    os.chmod(destination, 0o600)
except OSError:
    pass
print('Created .env securely (no secrets printed).')
print('Copy your signup code from TUNELY_SIGNUP_CODE in .env and enter it when creating a test account.')
