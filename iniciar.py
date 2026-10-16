"""Inicia o Formato Fácil PDF e abre o navegador quando o aplicativo estiver pronto."""

from __future__ import annotations

import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

PASTA = Path(__file__).resolve().parent


def porta_livre(inicial: int = 8501) -> int:
    for porta in range(inicial, inicial + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", porta)) != 0:
                return porta
    raise RuntimeError("Nenhuma porta livre encontrada entre 8501 e 8550.")


def aguardar(porta: int, limite_s: float = 60) -> bool:
    fim = time.time() + limite_s
    while time.time() < fim:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", porta)) == 0:
                return True
        time.sleep(0.3)
    return False


def main() -> int:
    porta = porta_livre()
    print("Iniciando o Formato Fácil PDF…")
    processo = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(PASTA / "app.py"),
         "--server.port", str(porta), "--server.address", "localhost",
         "--server.headless", "true"],
        cwd=str(PASTA),
    )
    endereco = f"http://localhost:{porta}"
    if aguardar(porta):
        webbrowser.open(endereco)
        print(f"\nAplicativo aberto em {endereco}")
        print("Mantenha esta janela aberta enquanto usa o aplicativo. Para encerrar, feche-a.\n")
    else:
        print("O aplicativo demorou para iniciar. Tente abrir manualmente:", endereco)
    try:
        return processo.wait()
    except KeyboardInterrupt:
        processo.terminate()
        return 0


if __name__ == "__main__":
    sys.exit(main())
