"""python -m agencia.web"""

import argparse

from .servidor import correr

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Interfaz web del sistema de agencia.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--puerto", type=int, default=8000)
    args = parser.parse_args()
    correr(args.host, args.puerto)
