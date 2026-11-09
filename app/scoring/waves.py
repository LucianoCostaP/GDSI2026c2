"""Olas de acceso por percentil del ranking (HU-36). Funciones puras, sin base de datos.

La banda k cubre los percentiles ((k − 1)·paso, k·paso] y su límite entero es
floor(k·paso·M / 100). Las bandas vacías se omiten donde caigan y las que quedan se numeran
de 1 a N, conservando el rango de percentil de su banda original.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Wave:
    order: int
    percentile_from: int
    percentile_to: int
    position_from: int
    position_to: int

    @property
    def socios(self) -> int:
        return self.position_to - self.position_from + 1


def _boundary(band: int, step: int, ranked_total: int) -> int:
    return (band * step * ranked_total) // 100


def build_waves(ranked_total: int, step: int) -> list[Wave]:
    if ranked_total < 1:
        raise ValueError("ranked_total tiene que ser al menos 1")
    if step <= 0 or 100 % step != 0:
        raise ValueError("step tiene que dividir a 100")
    waves: list[Wave] = []
    for band in range(1, 100 // step + 1):
        first = _boundary(band - 1, step, ranked_total) + 1
        last = _boundary(band, step, ranked_total)
        if last < first:
            continue
        waves.append(
            Wave(
                order=len(waves) + 1,
                percentile_from=(band - 1) * step,
                percentile_to=band * step,
                position_from=first,
                position_to=last,
            )
        )
    return waves


def wave_of(position: int, ranked_total: int, step: int) -> int | None:
    """La ola (ya renumerada) de una posición, o `None` si está fuera del ranking."""
    for wave in build_waves(ranked_total, step):
        if wave.position_from <= position <= wave.position_to:
            return wave.order
    return None
