# PokemonWeb

Pokemon damage calculator web app built with Flask.

## Run locally

```powershell
pip install -r requirements.txt
$env:POKEMONWEB_PUBLIC="1"
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Deploy

This app is ready for Render.

Build command:

```text
pip install -r requirements.txt
```

Start command:

```text
gunicorn app:app
```

Environment variables:

```text
POKEMONWEB_PUBLIC=1
POKEMONWEB_SESSION_SECRET=<long random string>
```

See `README_DEPLOY.md` for the full deployment checklist.
