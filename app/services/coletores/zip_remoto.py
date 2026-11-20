"""Leitura parcial de um zip remoto: baixa só os trechos (HTTP Range) que o membro pedido ocupa."""
from __future__ import annotations

import io
import zipfile
from typing import Callable, TextIO

from ..http import criar_sessao


class LeitorIntervalo(io.RawIOBase):
    """Arquivo somente leitura e com seek, cujos bytes vêm de baixar(inicio, fim_inclusivo)."""

    def __init__(self, tamanho: int, baixar: Callable[[int, int], bytes]):
        self.tamanho = tamanho
        self.baixar = baixar
        self.pos = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, deslocamento: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            self.pos = deslocamento
        elif whence == io.SEEK_CUR:
            self.pos += deslocamento
        else:
            self.pos = self.tamanho + deslocamento
        self.pos = max(0, self.pos)
        return self.pos

    def readinto(self, b) -> int:
        if self.pos >= self.tamanho:
            return 0
        fim = min(self.pos + len(b), self.tamanho) - 1
        dados = self.baixar(self.pos, fim)
        b[:len(dados)] = dados
        self.pos += len(dados)
        return len(dados)


def abrir_membro(url: str, membro: str) -> TextIO:
    """Abre um arquivo de dentro do zip remoto, decodificado em latin-1. KeyError se não existir."""
    return io.TextIOWrapper(abrir_zip(url).open(membro), encoding="latin-1", newline="")


def abrir_zip(url: str) -> zipfile.ZipFile:
    """Zip remoto lido sob demanda (só o índice e os membros abertos são baixados). KeyError se não existir."""
    sessao = criar_sessao()
    cab = sessao.head(url, allow_redirects=True, timeout=60)
    if cab.status_code == 404:
        raise KeyError(f"zip inexistente: {url}")
    cab.raise_for_status()
    tamanho = int(cab.headers["Content-Length"])

    def baixar(inicio: int, fim: int) -> bytes:
        r = sessao.get(url, headers={"Range": f"bytes={inicio}-{fim}"}, timeout=120)
        r.raise_for_status()
        if r.status_code != 206:
            raise RuntimeError(f"o servidor ignorou o Range (HTTP {r.status_code}): {url}")
        return r.content

    return zipfile.ZipFile(io.BufferedReader(LeitorIntervalo(tamanho, baixar), 1 << 20))
