# PokemonWeb deployment

## Render

1. Put this folder in a GitHub repository.
2. Create a new Web Service on Render from that repository.
3. Use these settings:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
4. Add environment variables:
   - `POKEMONWEB_PUBLIC=1`
   - `POKEMONWEB_SESSION_SECRET=<any long random string>`
5. Deploy and open the public URL Render gives you.

`render.yaml` contains the same settings, so Render can also detect them as Blueprint settings.

## Local check

```powershell
pip install -r requirements.txt
$env:POKEMONWEB_PUBLIC="1"
python app.py
```

Then open:

```text
http://127.0.0.1:5000
```

If `POKEMONWEB_PUBLIC` is not set to `1`, the app still requires the `?key=...` access key.
