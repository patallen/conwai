from __future__ import annotations

import math


class Grid:
    """2D sugar grid with two peaks, per Epstein & Axtell."""

    def __init__(self, width: int, height: int, max_sugar: int = 4):
        self.width = width
        self.height = height
        self.max_sugar = max_sugar
        self._sugar = [[0] * width for _ in range(height)]
        self._capacity = [[0] * width for _ in range(height)]

    def seed_peaks(
        self,
        peak1: tuple[int, int] | None = None,
        peak2: tuple[int, int] | None = None,
        radius: int | None = None,
    ) -> None:
        """Two sugar mountains with capacity falling off by distance."""
        if peak1 is None:
            peak1 = (self.width // 4, self.height // 4)
        if peak2 is None:
            peak2 = (3 * self.width // 4, 3 * self.height // 4)
        if radius is None:
            radius = min(self.width, self.height) // 3

        for y in range(self.height):
            for x in range(self.width):
                d1 = math.sqrt((x - peak1[0]) ** 2 + (y - peak1[1]) ** 2)
                d2 = math.sqrt((x - peak2[0]) ** 2 + (y - peak2[1]) ** 2)
                d = min(d1, d2)
                if d <= radius:
                    cap = max(1, round(self.max_sugar * (1 - d / radius)))
                else:
                    cap = 0
                self._capacity[y][x] = cap
                self._sugar[y][x] = cap

    def sugar_at(self, x: int, y: int) -> int:
        return self._sugar[y][x]

    def capacity_at(self, x: int, y: int) -> int:
        return self._capacity[y][x]

    def harvest(self, x: int, y: int) -> int:
        """Remove and return all sugar at a cell."""
        amount = self._sugar[y][x]
        self._sugar[y][x] = 0
        return amount

    def regrow(self, rate: int = 1) -> None:
        """Grow sugar in all cells by rate, up to capacity."""
        for y in range(self.height):
            for x in range(self.width):
                cap = self._capacity[y][x]
                if cap > 0:
                    self._sugar[y][x] = min(cap, self._sugar[y][x] + rate)
