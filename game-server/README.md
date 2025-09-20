# Game server

This folder contains a lightweight static experience that you can embed inside other
interfaces. The HTML entry point is `index.html` and the `run_server.py` helper wraps the
Python standard library HTTP server while adding ngrok tunnelling helpers so that you can
expose the content behind an HTTPS URL that works inside an `<iframe>`.

## Running locally

```bash
uv run python game-server/run_server.py
```

By default the command serves the `game-server` directory on <http://0.0.0.0:8000/> and
attempts to start an ngrok tunnel by executing `ngrok http {port}`. The ngrok process
output is streamed with a `[ngrok]` prefix so you can copy the generated public URL.

### Command line options

The helper script includes several switches that make it easier to fit into your
workflow:

| Flag | Description |
| --- | --- |
| `--directory PATH` | Serve a different directory (useful when you replace the sample UI). |
| `--port PORT` | Change the local port. |
| `--host HOST` | Override the bind address; defaults to `0.0.0.0`. |
| `--no-ngrok` | Skip launching ngrok and only serve the local HTTP endpoint. |
| `--ngrok-template STRING` | Provide a custom command template. `{port}` is replaced with the selected port. |
| `--ngrok-extra ARG [ARG ...]` | Append extra arguments to the ngrok command. |
| `--open-browser` | Open the served page in your default browser once the server is ready. |

If ngrok is not installed or the executable lives under a different name, point the
`--ngrok-template` flag at the correct binary. For example:

```bash
uv run python game-server/run_server.py --ngrok-template "/opt/ngrok/bin/ngrok http {port}"
```

Any additional arguments that the ngrok CLI expects (such as region selection or
authentication tokens) can be appended with `--ngrok-extra`. The template and extra
arguments give you enough flexibility to match the conventions outlined in the ngrok
documentation.

## Exposing the server via ngrok

Make sure you have an ngrok account and have installed the CLI on your machine. Export
any authentication token it requires (for example `NGROK_AUTHTOKEN`) following the official
documentation, then run the helper:

```bash
uv run python game-server/run_server.py --ngrok-extra --label example
```

Watch the console for a line similar to:

```
[ngrok] https://your-subdomain.ngrok.io -> http://localhost:8000
```

Use that URL as the `src` of your iframe inside the other UI:

```html
<iframe src="https://your-subdomain.ngrok.io" width="100%" height="720" allow="fullscreen" style="border:0"></iframe>
```

The server removes `X-Frame-Options` and applies basic cache busting headers, so the page
can be embedded safely while you iterate. If you want to run without tunnelling (for
instance when debugging locally), add `--no-ngrok` or run a plain `python -m
http.server` inside this folder.

## Customising the UI

`index.html` currently ships with a small animated scoreboard. Replace this file with your
own HTML/CSS/JavaScript to render the real game interface—`run_server.py` automatically
serves whatever is inside the target directory. Because the helper uses the standard
library web server there is no build step; simply refresh the iframe and the changes will
appear immediately.

> **Tip:** If the iframe host enforces HTTPS you should keep using the ngrok tunnel even
> when everything runs on the same development machine. That avoids mixed-content issues.
