import secrets, pathlib, os


d_garage = pathlib.Path("/secrets/garage")
d_garage.mkdir(parents=True, exist_ok=True)

d_app = pathlib.Path("/secrets/app")
d_app.mkdir(parents=True, exist_ok=True)


for name, value in {
    "garage_rpc_secret": secrets.token_hex(32),
    "garage_admin_token": secrets.token_urlsafe(32),
}.items():
    p = d_garage / name
    if not p.exists():
        fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(value)

for name, value in {
    "django_secret_key": secrets.token_urlsafe(50),
    "django_admin_password": secrets.token_urlsafe(16),
}.items():
    p = d_app / name
    if not p.exists():
        fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(value)