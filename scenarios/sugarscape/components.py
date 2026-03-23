from dataclasses import dataclass

from conwai.component import Component


@dataclass
class Position(Component):
    x: int = 0
    y: int = 0


@dataclass
class Sugar(Component):
    """Agent's sugar stockpile. Gathered from the grid, burned by metabolism."""

    wealth: int = 10
    metabolism: int = 1


@dataclass
class Vision(Component):
    range: int = 3
