"""Comando ``mus-web``: arranca la web.

    mus-web                 # solo en este ordenador: http://localhost:8000
    mus-web --red           # también desde otros dispositivos de la misma wifi
    MUS_PUBLICO=1 mus-web --red --puerto 7860   # en un servidor de internet (límites estrictos)

Las mesas viven en la memoria del servidor, así que se arranca con **un solo proceso**.
"""

from __future__ import annotations

import argparse
import socket
import threading
import webbrowser
from collections.abc import Sequence


def ip_local() -> str:
    """La IP de este ordenador en la red local (para jugar desde el móvil)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no envía nada: solo elige la interfaz de salida
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mus-web", description="Arranca la web de Mus Arena.")
    parser.add_argument("--red", action="store_true",
                        help="aceptar conexiones de otros dispositivos de la red")
    parser.add_argument("--puerto", type=int, default=8000)
    parser.add_argument("--no-abrir", action="store_true", help="no abrir el navegador")
    args = parser.parse_args(argv)
    try:
        import uvicorn

        from musarena.web.app import crear_app
    except ImportError:
        parser.error('Falta el extra web: pip install -e ".[web]"')

    host = "0.0.0.0" if args.red else "127.0.0.1"
    url = f"http://localhost:{args.puerto}"
    print(f"millosolo-mus (Mus Arena) en {url}")
    if args.red:
        print(f"Desde otros dispositivos de la misma red: http://{ip_local()}:{args.puerto}")
    if not args.no_abrir:
        threading.Timer(1.0, webbrowser.open, (url,)).start()
    uvicorn.run(crear_app(), host=host, port=args.puerto, workers=1, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
