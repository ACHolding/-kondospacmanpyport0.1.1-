#!/usr/bin/env python3
"""Kondo's Pacman Py Port 0.1.2 — Famicom-style Pac-Man, one file, no assets.

* Python 3.14 (3.9+): stdlib + pygame only.  "files = off" — no image / sound /
  data files are read or written: sprites, font, audio and every Namco level
  table below are generated / stored in this one file (no .pyc either).
* 60 FPS: drift-free fixed-timestep loop (perf_counter), cached glyphs,
  pre-rendered dot / wall layers, cached rotated sprites, allocation-free scaling.
* Namco arcade engine data (level table, ghost-house counters, Elroy, fright,
  scatter/chase timers, fruit, bonus scoring) lives in the NAMCO ENGINE DATA block.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # files = off

import argparse
import array
import math
import os
import random
import time
from enum import Enum, auto
from typing import NamedTuple

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

# ---------------------------------------------------------------------------
# Constants / NES palette
# ---------------------------------------------------------------------------
TITLE = "KONDO'S PACMAN PY PORT"
VERSION = "0.1.2"
CREDIT = "BY AC"
FPS = 60
DT = 1.0 / FPS
INTERNAL_W, INTERNAL_H = 480, 270
WINDOW_W, WINDOW_H = 600, 400  # laptop window; canvas letterboxed inside
# Nearest-neighbor fit of internal canvas into the window (preserves aspect)
_FIT = min(WINDOW_W / INTERNAL_W, WINDOW_H / INTERNAL_H)
SCALED_W = int(INTERNAL_W * _FIT)  # 600
SCALED_H = int(INTERNAL_H * _FIT)  # 337
TILE = 8
MAZE_W, MAZE_H = 28, 31
MAZE_PX_W, MAZE_PX_H = MAZE_W * TILE, MAZE_H * TILE  # 224x248
MAZE_OX = (INTERNAL_W - MAZE_PX_W) // 2  # 128
MAZE_OY = 11

# Namco arcade: 100% speed = 75.75 px/s -> 1.2625 px/frame @ 60 Hz
FULL_SPEED = 75.75 / 60.0

BLACK = (0, 0, 0)
MAZE_BLUE = (0x20, 0x38, 0xEC)
PAC_YELLOW = (0xF8, 0xD8, 0x78)
BLINKY_C = (0xF8, 0x38, 0x00)
PINKY_C = (0xF8, 0x78, 0xF8)
INKY_C = (0x3C, 0xBC, 0xFC)
CLYDE_C = (0xFC, 0xA0, 0x44)
FRIGHT_BLUE = (0x00, 0x00, 0xBC)
WHITE = (0xFC, 0xFC, 0xFC)
DOT_PINK = (0xFC, 0xC4, 0xD8)
WALL_FLASH = (0xFC, 0xFC, 0xFC)
DARK_YELLOW = (0xBC, 0x88, 0x00)
GRAY = (0x7C, 0x7C, 0x7C)

DIRS = {
    "UP": (0, -1),
    "DOWN": (0, 1),
    "LEFT": (-1, 0),
    "RIGHT": (1, 0),
}
DIR_ORDER = ("UP", "LEFT", "DOWN", "RIGHT")  # tie-break
OPPOSITE = {"UP": "DOWN", "DOWN": "UP", "LEFT": "RIGHT", "RIGHT": "LEFT"}

# ---------------------------------------------------------------------------
# NAMCO ENGINE DATA (arcade Pac-Man / Famicom port level logic)
# ---------------------------------------------------------------------------
class Level(NamedTuple):
    fruit: str        # bonus symbol
    fruit_pts: int
    pac: int          # Pac-Man speed %, normal
    gh: int           # ghost speed %, normal
    gh_tunnel: int    # ghost speed % in the tunnel
    e1_dots: int      # Cruise Elroy 1 when dots left <=
    e1_spd: int       #   ... Blinky speed %
    e2_dots: int      # Cruise Elroy 2 when dots left <=
    e2_spd: int       #   ... Blinky speed %
    pac_fright: int   # Pac-Man speed % while ghosts frightened (0 = n/a)
    gh_fright: int    # frightened ghost speed %
    fright_secs: int  # frightened time (0 = ghosts only reverse)
    flashes: int      # white/blue flashes at the end of fright


_FRU = ("CHERRY", 100), ("STRAW", 300), ("ORANGE", 500), ("APPLE", 700), \
       ("MELON", 1000), ("GALAX", 2000), ("BELL", 3000), ("KEY", 5000)
_C, _S, _O, _A, _M, _G, _B, _K = _FRU

# fruit, pts, pac, gh, tun, e1d, e1s, e2d, e2s, pacF, ghF, secs, flashes
LEVELS = (
    Level(*_C, 80, 75, 40, 20, 80, 10, 85, 90, 50, 6, 5),   # 1
    Level(*_S, 90, 85, 45, 30, 90, 15, 95, 95, 55, 5, 5),   # 2
    Level(*_O, 90, 85, 45, 40, 90, 20, 95, 95, 55, 4, 5),   # 3
    Level(*_O, 90, 85, 45, 40, 90, 20, 95, 95, 55, 3, 5),   # 4
    Level(*_A, 100, 95, 50, 40, 100, 20, 105, 100, 60, 2, 5),  # 5
    Level(*_A, 100, 95, 50, 50, 100, 25, 105, 100, 60, 5, 5),  # 6
    Level(*_M, 100, 95, 50, 50, 100, 25, 105, 100, 60, 2, 5),  # 7
    Level(*_M, 100, 95, 50, 50, 100, 25, 105, 100, 60, 2, 5),  # 8
    Level(*_G, 100, 95, 50, 60, 100, 30, 105, 100, 60, 1, 3),  # 9
    Level(*_G, 100, 95, 50, 60, 100, 30, 105, 100, 60, 5, 5),  # 10
    Level(*_B, 100, 95, 50, 60, 100, 30, 105, 100, 60, 2, 5),  # 11
    Level(*_B, 100, 95, 50, 80, 100, 40, 105, 100, 60, 1, 3),  # 12
    Level(*_K, 100, 95, 50, 80, 100, 40, 105, 100, 60, 1, 3),  # 13
    Level(*_K, 100, 95, 50, 80, 100, 40, 105, 100, 60, 3, 5),  # 14
    Level(*_K, 100, 95, 50, 100, 100, 50, 105, 100, 60, 1, 3),  # 15
    Level(*_K, 100, 95, 50, 100, 100, 50, 105, 100, 60, 1, 3),  # 16
    Level(*_K, 100, 95, 50, 100, 100, 50, 105, 0, 0, 0, 0),    # 17
    Level(*_K, 100, 95, 50, 100, 100, 50, 105, 100, 60, 1, 3),  # 18
    Level(*_K, 100, 95, 50, 120, 100, 60, 105, 0, 0, 0, 0),    # 19
    Level(*_K, 100, 95, 50, 120, 100, 60, 105, 0, 0, 0, 0),    # 20
    Level(*_K, 90, 95, 50, 120, 100, 60, 105, 0, 0, 0, 0),     # 21+
)

# Pac-Man slows while eating: 1 frame per dot, 3 per power pellet (arcade).
DOT_STALL, PELLET_STALL = 1, 3
# Bonus fruit: appears after 70 and 170 dots, lives 9-10 s, drawn below the house.
FRUIT_DOTS = (70, 170)
FRUIT_TIME = (9.0, 10.0)
# Ghost score chain and the "all four on all four pellets" jackpot.
GHOST_POINTS = (200, 400, 800, 1600)
ALL_GHOSTS_BONUS = 12000
EXTRA_LIFE_AT = 10000
DOT_POINTS, PELLET_POINTS = 10, 50
FRIGHT_FLASH_FRAMES = 14  # one blue+white flash cycle

# Ghost house: personal dot-counter limits (pinky, inky, clyde) per level.
HOUSE_LIMITS = {1: (0, 30, 60), 2: (0, 0, 50)}  # level 3+ -> (0, 0, 0)
# After losing a life the shared "global" counter is used instead.
GLOBAL_LIMITS = {"pinky": 7, "inky": 17, "clyde": 32}
RELEASE_ORDER = ("pinky", "inky", "clyde")
# Idle timer: force the next ghost out when Pac-Man eats nothing for this long.
FORCE_RELEASE_SECS = {1: 4, 2: 4, 3: 4, 4: 4}  # level 5+ -> 3 s

# Classic ghost roll call: CHARACTER / NICKNAME
GHOST_ROLL = (
    ("blinky", "SHADOW", "BLINKY", BLINKY_C),
    ("pinky", "SPEEDY", "PINKY", PINKY_C),
    ("inky", "BASHFUL", "INKY", INKY_C),
    ("clyde", "POKEY", "CLYDE", CLYDE_C),
)

# Tiles where ghosts (not eyes) may not choose UP (arcade "ghost house exits")
NO_UP_TILES = {(12, 11), (15, 11), (12, 23), (15, 23)}

# Scatter home corners (tile coords; negative Y is above the maze — arcade)
SCATTER_TARGETS = {
    "blinky": (25, -3),   # NE
    "pinky": (2, -3),     # NW
    "inky": (27, 32),     # SE
    "clyde": (0, 32),     # SW
}

# Frightened RNG direction order (Namco: bits map to R, D, L, U — not chase tie-break)
FRIGHT_DIR_ORDER = ("RIGHT", "DOWN", "LEFT", "UP")

# Intermissions after clearing these levels (arcade)
INTERMISSION_AFTER = {2: 1, 5: 2, 9: 3, 13: 3, 17: 3}


class State(Enum):
    MENU = auto()
    HELP = auto()
    ABOUT = auto()
    ROLL_CALL = auto()
    READY = auto()
    PLAYING = auto()
    PAUSED = auto()
    DYING = auto()
    LEVEL_CLEAR = auto()
    INTERMISSION = auto()
    GAME_OVER = auto()
    KILL_SCREEN = auto()


# ---------------------------------------------------------------------------
# Bitmap font (8x8) — A-Z 0-9 ! . - : © × space '
# ---------------------------------------------------------------------------
_FONT_RAW = {
    " ": ["00000000"] * 8,
    "A": ["00111000", "01000100", "01000100", "01111100", "01000100", "01000100", "01000100", "00000000"],
    "B": ["01111000", "01000100", "01000100", "01111000", "01000100", "01000100", "01111000", "00000000"],
    "C": ["00111000", "01000100", "01000000", "01000000", "01000000", "01000100", "00111000", "00000000"],
    "D": ["01111000", "01000100", "01000100", "01000100", "01000100", "01000100", "01111000", "00000000"],
    "E": ["01111100", "01000000", "01000000", "01111000", "01000000", "01000000", "01111100", "00000000"],
    "F": ["01111100", "01000000", "01000000", "01111000", "01000000", "01000000", "01000000", "00000000"],
    "G": ["00111000", "01000100", "01000000", "01011100", "01000100", "01000100", "00111000", "00000000"],
    "H": ["01000100", "01000100", "01000100", "01111100", "01000100", "01000100", "01000100", "00000000"],
    "I": ["00111000", "00010000", "00010000", "00010000", "00010000", "00010000", "00111000", "00000000"],
    "J": ["00011100", "00001000", "00001000", "00001000", "00001000", "01001000", "00110000", "00000000"],
    "K": ["01000100", "01001000", "01010000", "01100000", "01010000", "01001000", "01000100", "00000000"],
    "L": ["01000000", "01000000", "01000000", "01000000", "01000000", "01000000", "01111100", "00000000"],
    "M": ["01000100", "01101100", "01010100", "01000100", "01000100", "01000100", "01000100", "00000000"],
    "N": ["01000100", "01100100", "01010100", "01001100", "01000100", "01000100", "01000100", "00000000"],
    "O": ["00111000", "01000100", "01000100", "01000100", "01000100", "01000100", "00111000", "00000000"],
    "P": ["01111000", "01000100", "01000100", "01111000", "01000000", "01000000", "01000000", "00000000"],
    "Q": ["00111000", "01000100", "01000100", "01000100", "01010100", "01001000", "00110100", "00000000"],
    "R": ["01111000", "01000100", "01000100", "01111000", "01010000", "01001000", "01000100", "00000000"],
    "S": ["00111000", "01000100", "01000000", "00111000", "00000100", "01000100", "00111000", "00000000"],
    "T": ["01111100", "00010000", "00010000", "00010000", "00010000", "00010000", "00010000", "00000000"],
    "U": ["01000100", "01000100", "01000100", "01000100", "01000100", "01000100", "00111000", "00000000"],
    "V": ["01000100", "01000100", "01000100", "01000100", "01000100", "00101000", "00010000", "00000000"],
    "W": ["01000100", "01000100", "01000100", "01010100", "01010100", "01101100", "01000100", "00000000"],
    "X": ["01000100", "01000100", "00101000", "00010000", "00101000", "01000100", "01000100", "00000000"],
    "Y": ["01000100", "01000100", "00101000", "00010000", "00010000", "00010000", "00010000", "00000000"],
    "Z": ["01111100", "00000100", "00001000", "00010000", "00100000", "01000000", "01111100", "00000000"],
    "0": ["00111000", "01000100", "01001100", "01010100", "01100100", "01000100", "00111000", "00000000"],
    "1": ["00010000", "00110000", "00010000", "00010000", "00010000", "00010000", "00111000", "00000000"],
    "2": ["00111000", "01000100", "00000100", "00011000", "00100000", "01000000", "01111100", "00000000"],
    "3": ["00111000", "01000100", "00000100", "00011000", "00000100", "01000100", "00111000", "00000000"],
    "4": ["00001000", "00011000", "00101000", "01001000", "01111100", "00001000", "00001000", "00000000"],
    "5": ["01111100", "01000000", "01111000", "00000100", "00000100", "01000100", "00111000", "00000000"],
    "6": ["00111000", "01000000", "01000000", "01111000", "01000100", "01000100", "00111000", "00000000"],
    "7": ["01111100", "00000100", "00001000", "00010000", "00100000", "00100000", "00100000", "00000000"],
    "8": ["00111000", "01000100", "01000100", "00111000", "01000100", "01000100", "00111000", "00000000"],
    "9": ["00111000", "01000100", "01000100", "00111100", "00000100", "00000100", "00111000", "00000000"],
    "!": ["00010000", "00010000", "00010000", "00010000", "00010000", "00000000", "00010000", "00000000"],
    ".": ["00000000", "00000000", "00000000", "00000000", "00000000", "00010000", "00010000", "00000000"],
    "-": ["00000000", "00000000", "00000000", "01111100", "00000000", "00000000", "00000000", "00000000"],
    ":": ["00000000", "00010000", "00010000", "00000000", "00010000", "00010000", "00000000", "00000000"],
    "'": ["00010000", "00010000", "00000000", "00000000", "00000000", "00000000", "00000000", "00000000"],
    '"': ["01001000", "01001000", "00000000", "00000000", "00000000", "00000000", "00000000", "00000000"],
    "/": ["00000100", "00001000", "00010000", "00100000", "01000000", "00000000", "00000000", "00000000"],
    ",": ["00000000", "00000000", "00000000", "00000000", "00010000", "00010000", "00100000", "00000000"],
    "(": ["00001000", "00010000", "00100000", "00100000", "00100000", "00010000", "00001000", "00000000"],
    ")": ["00100000", "00010000", "00001000", "00001000", "00001000", "00010000", "00100000", "00000000"],
    "©": ["00111000", "01000100", "01011000", "01010000", "01011000", "01000100", "00111000", "00000000"],
    "×": ["00000000", "01000100", "00101000", "00010000", "00101000", "01000100", "00000000", "00000000"],
}


def _build_font():
    font = {}
    for ch, rows in _FONT_RAW.items():
        surf = pygame.Surface((8, 8))
        surf.set_colorkey((0, 0, 0))
        surf.fill((0, 0, 0))
        for y, row in enumerate(rows):
            for x, bit in enumerate(row):
                if bit == "1":
                    surf.set_at((x, y), WHITE)
        font[ch] = surf.convert()
    return font


_GLYPHS = {}  # (ch, color, scale) -> pre-tinted, pre-scaled glyph


def _glyph(font, ch, color, scale):
    key = (ch, color, scale)
    g = _GLYPHS.get(key)
    if g is None:
        base = font.get(ch) or font.get(" ")
        g = pygame.Surface((8, 8))
        g.set_colorkey(BLACK)
        g.fill(BLACK)
        tint = pygame.Surface((8, 8))
        tint.fill(color)
        g.blit(base, (0, 0))
        g.blit(tint, (0, 0), special_flags=pygame.BLEND_RGB_MULT)  # white -> color
        if scale != 1:
            g = pygame.transform.scale(g, (8 * scale, 8 * scale))
            g.set_colorkey(BLACK)
        g = g.convert()
        _GLYPHS[key] = g
    return g


def draw_text(surface, text, x, y, color, font, scale=1):
    step = 8 * scale
    color = tuple(color)
    blit = surface.blit
    for ch in text.upper():
        if ch != " ":
            blit(_glyph(font, ch, color, scale), (x, y))
        x += step


# ---------------------------------------------------------------------------
# Classic maze 28x31 — # wall . dot o power   empty - door T tunnel
# ---------------------------------------------------------------------------
MAZE_TEMPLATE = [
    "############################",
    "#............##............#",
    "#.####.#####.##.#####.####.#",
    "#o####.#####.##.#####.####o#",
    "#.####.#####.##.#####.####.#",
    "#..........................#",
    "#.####.##.########.##.####.#",
    "#.####.##.########.##.####.#",
    "#......##....##....##......#",
    "######.##### ## #####.######",
    "     #.##### ## #####.#     ",
    "     #.##          ##.#     ",
    "     #.## ###--### ##.#     ",
    "######.## #      # ##.######",
    "TTTTTT.   #      #   .TTTTTT",
    "######.## #      # ##.######",
    "     #.## ######## ##.#     ",
    "     #.##          ##.#     ",
    "     #.## ######## ##.#     ",
    "######.## ######## ##.######",
    "#............##............#",
    "#.####.#####.##.#####.####.#",
    "#.####.#####.##.#####.####.#",
    "#o..##.......  .......##..o#",
    "###.##.##.########.##.##.###",
    "###.##.##.########.##.##.###",
    "#......##....##....##......#",
    "#.##########.##.##########.#",
    "#.##########.##.##########.#",
    "#..........................#",
    "############################",
]


def count_dots(grid):
    return sum(row.count(".") + row.count("o") for row in grid)


# ---------------------------------------------------------------------------
# Audio synth (NES-ish pulse / triangle / noise)
# ---------------------------------------------------------------------------
class Synth:
    def __init__(self):
        self.ok = False
        self.sounds = {}
        self.channels = {}
        try:
            pygame.mixer.pre_init(44100, -16, 1, 512)
            pygame.mixer.init()
            self.ok = True
            self._build_all()
            self.channels = {
                "siren": pygame.mixer.Channel(0),
                "power": pygame.mixer.Channel(1),
                "eyes": pygame.mixer.Channel(2),
                "fx": pygame.mixer.Channel(3),
                "waka": pygame.mixer.Channel(4),
                "jingle": pygame.mixer.Channel(5),
            }
        except Exception:
            self.ok = False
            self.jingle_frames = int(4 * FPS)

    def _pulse(self, freq, dur, duty=0.25, vol=0.25, slide=0.0):
        sr = 44100
        n = int(sr * dur)
        buf = array.array("h")
        amp = int(32767 * vol)
        phase = 0.0
        f = float(freq)
        for i in range(n):
            if slide:
                f = freq + slide * (i / max(1, n - 1))
            phase += f / sr
            phase %= 1.0
            sample = amp if phase < duty else -amp
            # soft envelope
            env = 1.0
            if i < sr * 0.005:
                env = i / (sr * 0.005)
            rem = n - i
            if rem < sr * 0.01:
                env *= rem / (sr * 0.01)
            buf.append(int(sample * env))
        return pygame.mixer.Sound(buffer=buf)

    def _triangle(self, freq, dur, vol=0.2):
        sr = 44100
        n = int(sr * dur)
        buf = array.array("h")
        amp = int(32767 * vol)
        phase = 0.0
        for i in range(n):
            phase += freq / sr
            phase %= 1.0
            # 4-bit stepped triangle
            t = int(phase * 16) % 16
            if t < 8:
                v = t / 7.0
            else:
                v = (15 - t) / 7.0
            sample = int((v * 2 - 1) * amp)
            buf.append(sample)
        return pygame.mixer.Sound(buffer=buf)

    def _noise(self, dur, vol=0.15, pitch=0.5):
        sr = 44100
        n = int(sr * dur)
        buf = array.array("h")
        amp = int(32767 * vol)
        reg = 1
        hold = 0
        val = 0
        period = max(1, int(8 / pitch))
        for i in range(n):
            if hold <= 0:
                bit = ((reg >> 0) ^ (reg >> 1)) & 1
                reg = (reg >> 1) | (bit << 14)
                val = amp if (reg & 1) else -amp
                hold = period
            hold -= 1
            env = 1.0 - i / n
            buf.append(int(val * env))
        return pygame.mixer.Sound(buffer=buf)

    def _mix(self, *parts):
        """Mix Sound buffers of equal length (first sets length)."""
        arrs = []
        for s in parts:
            raw = s.get_raw()
            arrs.append(array.array("h", raw))
        n = max(len(a) for a in arrs)
        out = array.array("h", [0] * n)
        for a in arrs:
            for i, v in enumerate(a):
                out[i] = max(-32767, min(32767, out[i] + v))
        return pygame.mixer.Sound(buffer=out)

    def _build_all(self):
        self.sounds["menu_move"] = self._pulse(880, 0.04, 0.25, 0.2)
        a = self._pulse(523, 0.06, 0.25, 0.22)
        b = self._pulse(784, 0.08, 0.25, 0.22)
        ra, rb = array.array("h", a.get_raw()), array.array("h", b.get_raw())
        self.sounds["menu_select"] = pygame.mixer.Sound(buffer=ra + rb)

        # Authentic Pac-Man start jingle (not the baseball/charge organ fanfare).
        # Melody: C-C'-G-E / Bb-Bb'-F-D / Ab-Ab'-Eb-C then climb to C'.
        # Two pulse voices + triangle bass, ~4s (FR-30).
        N = {
            "C4": 262, "D4": 294, "E4": 330, "F4": 349, "G4": 392, "Ab4": 415, "Bb4": 466,
            "C5": 523, "D5": 587, "Eb5": 622, "E5": 659, "F5": 698, "G5": 784,
            "Ab5": 831, "Bb5": 932, "C6": 1047,
        }
        beat = 0.22  # whole jingle ~4s (FR-30)
        melody = [
            ("C5", beat), ("C6", beat), ("G5", beat), ("E5", beat),
            ("C6", beat), ("G5", beat), ("E5", beat * 2),
            ("Bb4", beat), ("Bb5", beat), ("F5", beat), ("D5", beat),
            ("Bb5", beat), ("F5", beat), ("D5", beat * 2),
            ("Ab4", beat), ("Ab5", beat), ("Eb5", beat), ("C5", beat),
            ("Ab5", beat), ("Eb5", beat), ("C5", beat * 2),
            ("G4", beat), ("C5", beat), ("E5", beat), ("G5", beat),
            ("C6", beat), ("G5", beat), ("E5", beat), ("C5", beat * 2),
        ]
        jingle = array.array("h")
        for name, dur in melody:
            f = N[name]
            p = array.array("h", self._pulse(f, dur, 0.125, 0.22).get_raw())
            p2 = array.array("h", self._pulse(f * 2 if f < 800 else f, dur, 0.25, 0.08).get_raw())
            t = array.array("h", self._triangle(f / 2, dur, 0.14).get_raw())
            n = len(p)
            m = array.array("h", [0] * n)
            for i in range(n):
                s = p[i] + (p2[i] if i < len(p2) else 0) + (t[i] if i < len(t) else 0)
                m[i] = max(-32767, min(32767, s))
            jingle.extend(m)
        self.sounds["start_jingle"] = pygame.mixer.Sound(buffer=jingle)
        # Frames to freeze gameplay while the intro jingle ("duh duh duh") plays
        self.jingle_frames = max(1, int(round(self.sounds["start_jingle"].get_length() * FPS)))
        self.jingle_frames_fallback = int(4 * FPS)

        self.sounds["waka0"] = self._pulse(740, 0.055, 0.5, 0.18)
        self.sounds["waka1"] = self._pulse(580, 0.055, 0.5, 0.18)
        self.sounds["eat_ghost"] = self._pulse(200, 0.25, 0.25, 0.25, slide=600)
        self.sounds["eat_fruit"] = self._pulse(880, 0.12, 0.125, 0.22)
        self.sounds["extra_life"] = self._pulse(1046, 0.4, 0.25, 0.25, slide=200)
        # death
        dparts = array.array("h")
        for f in (880, 740, 620, 520, 400, 300, 200):
            dparts.extend(array.array("h", self._pulse(f, 0.08, 0.5, 0.2).get_raw()))
        dparts.extend(array.array("h", self._noise(0.25, 0.12, 0.8).get_raw()))
        self.sounds["death"] = pygame.mixer.Sound(buffer=dparts)

        # looping sirens
        self.sounds["siren"] = self._pulse(180, 0.4, 0.25, 0.08)
        self.sounds["power_siren"] = self._pulse(120, 0.35, 0.5, 0.1, slide=40)
        self.sounds["eyes_return"] = self._pulse(600, 0.2, 0.125, 0.12, slide=200)

        for name in ("siren", "power_siren", "eyes_return"):
            self.sounds[name].set_volume(0.35)

    def play(self, name, loop=False, channel="fx"):
        if not self.ok:
            return
        snd = self.sounds.get(name)
        if not snd:
            return
        ch = self.channels.get(channel)
        if ch:
            ch.play(snd, loops=-1 if loop else 0)
        else:
            snd.play(loops=-1 if loop else 0)

    def jingle_busy(self):
        if not self.ok:
            return False
        ch = self.channels.get("jingle")
        return bool(ch and ch.get_busy())

    def play_start_jingle(self):
        """Play intro jingle; returns how many READY frames to hold opcodes."""
        if not self.ok:
            return int(4 * FPS)
        self.stop_all_loops()
        self.play("start_jingle", channel="jingle")
        return getattr(self, "jingle_frames", int(4 * FPS))

    def stop(self, channel):
        if not self.ok:
            return
        ch = self.channels.get(channel)
        if ch:
            ch.stop()

    def stop_all_loops(self):
        for c in ("siren", "power", "eyes"):
            self.stop(c)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def level_data(level):
    return LEVELS[min(level, len(LEVELS)) - 1]


def fruit_for_level(level):
    d = level_data(level)
    return d.fruit, d.fruit_pts


def fright_time(level):
    return level_data(level).fright_secs


def house_limit(level, name):
    lim = HOUSE_LIMITS.get(level, (0, 0, 0))
    return lim[RELEASE_ORDER.index(name)]


def force_release_frames(level):
    return FORCE_RELEASE_SECS.get(level, 3) * FPS


def scatter_chase_schedule(level):
    """Namco scatter/chase timer table -> [(mode, frames)], last entry = forever."""
    if level == 1:
        secs = [7, 20, 7, 20, 5, 20, 5]
    elif level < 5:
        secs = [7, 20, 7, 20, 5, 1033, 1 / 60]
    else:
        secs = [5, 20, 5, 20, 5, 1037, 1 / 60]
    modes = []
    for i, s in enumerate(secs):
        mode = "scatter" if i % 2 == 0 else "chase"
        modes.append((mode, max(1, int(round(s * FPS)))))
    modes.append(("chase", 10**9))
    return modes


# ---------------------------------------------------------------------------
# Entity base
# ---------------------------------------------------------------------------
class Actor:
    def __init__(self, tx, ty, direction="LEFT"):
        self.x = tx * TILE + TILE // 2
        self.y = ty * TILE + TILE // 2
        self.dir = direction
        self.next_dir = direction
        self.stopped = False
        self.pixel_acc = 0.0

    @property
    def tile(self):
        return int(self.x // TILE), int(self.y // TILE)

    def center_of_tile(self):
        tx, ty = self.tile
        return tx * TILE + TILE // 2, ty * TILE + TILE // 2

    def at_tile_center(self, tol=0.6):
        cx, cy = self.center_of_tile()
        return abs(self.x - cx) <= tol and abs(self.y - cy) <= tol


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------
class Game:
    def __init__(self, frame_limit=None):
        self.frame_limit = frame_limit
        flags = 0
        if frame_limit is not None and os.environ.get("SDL_VIDEODRIVER") == "dummy":
            flags = 0
        self.fullscreen = False
        self.screen = self._open_window(flags)
        pygame.display.set_caption(TITLE)
        self.canvas = pygame.Surface((INTERNAL_W, INTERNAL_H)).convert()
        self.clock = pygame.time.Clock()
        self._rot_cache = {}
        self._prepare_screen()
        self.font = _build_font()
        self.synth = Synth()
        self.high_score = 0
        self.state = State.MENU
        self.menu_idx = 0
        self.menu_items = ["PLAY GAME", "ROLL CALL", "HELP", "ABOUT", "EXIT"]
        self.menu_anim = 0
        self.menu_idle = 0
        self.roll_timer = 0
        self.roll_phase = 0
        self.intermission_kind = 0
        self.intermission_timer = 0
        self.inter_actors = []
        self.frame = 0
        self.logic_frames = 0
        self.waka_toggle = 0
        self._fright_rng = 0x0001
        self._init_sprites()
        self._reset_session()

    def _init_sprites(self):
        # Pac-Man mouths: closed, half, open — facing right base
        self.pac_frames = []
        for mouth in (0, 2, 4):  # half-open angles approx via masks
            s = pygame.Surface((16, 16))
            s.set_colorkey(BLACK)
            s.fill(BLACK)
            pygame.draw.circle(s, PAC_YELLOW, (8, 8), 7)
            if mouth:
                pts = [(8, 8)]
                for a in range(-mouth * 12, mouth * 12 + 1, 4):
                    rad = math.radians(a)
                    pts.append((8 + int(math.cos(rad) * 8), 8 + int(math.sin(rad) * 8)))
                if len(pts) > 2:
                    pygame.draw.polygon(s, BLACK, pts)
            self.pac_frames.append(s)

        self.ghost_body = {}
        for name, col in (("blinky", BLINKY_C), ("pinky", PINKY_C),
                          ("inky", INKY_C), ("clyde", CLYDE_C)):
            frames = []
            for wobble in (0, 1):
                s = pygame.Surface((16, 16))
                s.set_colorkey(BLACK)
                s.fill(BLACK)
                pygame.draw.circle(s, col, (8, 7), 6)
                pygame.draw.rect(s, col, (2, 7, 12, 6))
                # scalloped bottom
                for i, ox in enumerate((2, 5, 8, 11)):
                    yy = 13 + ((i + wobble) % 2)
                    pygame.draw.circle(s, col, (ox + 1, yy), 2)
                # eyes
                pygame.draw.circle(s, WHITE, (5, 6), 2)
                pygame.draw.circle(s, WHITE, (11, 6), 2)
                frames.append(s)
            self.ghost_body[name] = frames

        self.fright_frames = []
        for wobble in (0, 1):
            s = pygame.Surface((16, 16))
            s.set_colorkey(BLACK)
            s.fill(BLACK)
            pygame.draw.circle(s, FRIGHT_BLUE, (8, 7), 6)
            pygame.draw.rect(s, FRIGHT_BLUE, (2, 7, 12, 6))
            for i, ox in enumerate((2, 5, 8, 11)):
                yy = 13 + ((i + wobble) % 2)
                pygame.draw.circle(s, FRIGHT_BLUE, (ox + 1, yy), 2)
            pygame.draw.circle(s, WHITE, (5, 7), 1)
            pygame.draw.circle(s, WHITE, (11, 7), 1)
            pygame.draw.line(s, WHITE, (4, 11), (6, 10), 1)
            pygame.draw.line(s, WHITE, (10, 10), (12, 11), 1)
            self.fright_frames.append(s)

        self.fright_flash = []
        for wobble in (0, 1):
            s = pygame.Surface((16, 16))
            s.set_colorkey(BLACK)
            s.fill(BLACK)
            pygame.draw.circle(s, WHITE, (8, 7), 6)
            pygame.draw.rect(s, WHITE, (2, 7, 12, 6))
            self.fright_flash.append(s)

        self.eyes_surf = pygame.Surface((16, 16))
        self.eyes_surf.set_colorkey(BLACK)
        self.eyes_surf.fill(BLACK)
        pygame.draw.circle(self.eyes_surf, WHITE, (5, 6), 2)
        pygame.draw.circle(self.eyes_surf, WHITE, (11, 6), 2)
        pygame.draw.circle(self.eyes_surf, (0, 0, 0xBC), (5, 6), 1)
        pygame.draw.circle(self.eyes_surf, (0, 0, 0xBC), (11, 6), 1)

        # display-format copies blit much faster every frame
        self.pac_frames = [s.convert() for s in self.pac_frames]
        self.ghost_body = {k: [s.convert() for s in v] for k, v in self.ghost_body.items()}
        self.fright_frames = [s.convert() for s in self.fright_frames]
        self.fright_flash = [s.convert() for s in self.fright_flash]
        self.eyes_surf = self.eyes_surf.convert()

    def _reset_session(self):
        self.score = 0
        self.lives = 3
        self.level = 1
        self.extra_life_awarded = False
        self.fruit_history = []
        self.ghost_kills = 0
        self.elroy_hold = False
        self.use_global = False
        self.global_counter = 0

    def _new_maze(self, kill=False):
        self.grid = [list(row) for row in MAZE_TEMPLATE]
        if kill:
            # Level 256 kill screen: overflow trash on the right half
            rng = random.Random(256)
            junk = list("#.#o #T-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
            for y in range(MAZE_H):
                for x in range(MAZE_W // 2, MAZE_W):
                    self.grid[y][x] = rng.choice(junk)
            # Fruit-draw overflow garbage strip (classic look)
            for i in range(64):
                x = MAZE_W // 2 + (i % 14)
                y = 1 + (i // 14)
                if 0 <= y < MAZE_H and 0 <= x < MAZE_W:
                    self.grid[y][x] = rng.choice(".#o# ")
            # Leave far too few dots to clear (impossible under normal play)
            for y in range(MAZE_H):
                for x in range(MAZE_W // 2, MAZE_W):
                    if self.grid[y][x] in ".o":
                        self.grid[y][x] = " "
        self.dots_total = count_dots(self.grid)
        self.dots_left = self.dots_total
        self.dots_eaten = 0
        self._build_wall_surface()
        self._build_dot_layers()

    def _build_dot_layers(self):
        """Pre-render dots once; eating a dot just erases its 8x8 cell."""
        self.dot_surf = pygame.Surface((MAZE_PX_W, MAZE_PX_H))
        self.dot_surf.set_colorkey(BLACK)
        self.dot_surf.fill(BLACK)
        self.pellets = []
        self.junk_tiles = []
        for ty, row in enumerate(self.grid):
            for tx, ch in enumerate(row):
                px, py = tx * TILE, ty * TILE
                if ch == ".":
                    pygame.draw.rect(self.dot_surf, DOT_PINK, (px + 3, py + 3, 2, 2))
                elif ch == "o":
                    self.pellets.append((px, py))
                elif self.level >= 256 and ch not in ("#", " ", "-", "T"):
                    self.junk_tiles.append((tx, ty, ch if ch.isalnum() else "?"))
        self.dot_surf = self.dot_surf.convert()
        self.pellet_surf = pygame.Surface((8, 8))
        self.pellet_surf.set_colorkey(BLACK)
        self.pellet_surf.fill(BLACK)
        pygame.draw.circle(self.pellet_surf, DOT_PINK, (4, 4), 4)
        self.pellet_surf = self.pellet_surf.convert()

    def _build_wall_surface(self):
        self.maze_surf = pygame.Surface((MAZE_PX_W, MAZE_PX_H))
        self.maze_surf.fill(BLACK)
        for ty, row in enumerate(self.grid):
            for tx, ch in enumerate(row):
                if ch == "#":
                    self._draw_wall_tile(tx, ty)
                elif ch == "-":
                    pygame.draw.rect(
                        self.maze_surf, PINKY_C,
                        (tx * TILE, ty * TILE + 3, TILE, 2)
                    )
        self.maze_surf = self.maze_surf.convert()
        # white "level clear" flash frame, built once instead of every frame
        flash = pygame.Surface((MAZE_PX_W, MAZE_PX_H))
        flash.fill(BLACK)
        for ty, row in enumerate(self.grid):
            for tx, ch in enumerate(row):
                if ch == "#":
                    self._draw_wall_tile(tx, ty, WALL_FLASH, flash)
        self.flash_surf = flash.convert()

    def _draw_wall_tile(self, tx, ty, color=MAZE_BLUE, surf=None):
        surf = surf or self.maze_surf
        # rounded outline based on neighbors
        def wall(x, y):
            if not (0 <= x < MAZE_W and 0 <= y < MAZE_H):
                return True
            return self.grid[y][x] == "#"

        px, py = tx * TILE, ty * TILE
        # fill dark blue center outline style
        pygame.draw.rect(surf, color, (px + 1, py + 1, TILE - 2, TILE - 2), 1)
        # connect to neighbors
        if wall(tx, ty - 1):
            pygame.draw.line(surf, color, (px + 1, py), (px + TILE - 2, py))
        if wall(tx, ty + 1):
            pygame.draw.line(surf, color, (px + 1, py + TILE - 1), (px + TILE - 2, py + TILE - 1))
        if wall(tx - 1, ty):
            pygame.draw.line(surf, color, (px, py + 1), (px, py + TILE - 2))
        if wall(tx + 1, ty):
            pygame.draw.line(surf, color, (px + TILE - 1, py + 1), (px + TILE - 1, py + TILE - 2))

    def _tile_passable(self, tx, ty, for_ghost=False, door_ok=False):
        if ty < 0 or ty >= MAZE_H:
            return False
        if tx < 0 or tx >= MAZE_W:
            return True
        ch = self.grid[ty][tx]
        if ch == "#":
            return False
        # On kill screen, treat most garbage as solid except empty / dots / tunnel
        if self.level >= 256 and ch not in (".", "o", " ", "-", "T"):
            return False
        if ch == "-" and not door_ok:
            return False
        return True

    def _start_level(self, keep_dots=False):
        kill = self.level >= 256
        if not keep_dots:
            self._new_maze(kill=kill)
        self.state = State.KILL_SCREEN if kill else State.READY
        self.dying_timer = 0
        self.clear_timer = 0
        self.game_over_timer = 0
        self.eat_pause = 0
        self.ghost_score_idx = 0
        self.score_popups = []
        self.fruit = None
        self.fruit_timer = 0
        self.fruit_shown = 0
        self.mode_schedule = scatter_chase_schedule(self.level)
        self.mode_idx = 0
        self.mode_timer = self.mode_schedule[0][1]
        self.global_mode = self.mode_schedule[0][0]
        self.fright_timer = 0
        self.fright_flash_frames = 0
        self.dot_timer = 0  # frames since last dot
        self.house_dots = {"pinky": 0, "inky": 0, "clyde": 0}
        self.release_order = list(RELEASE_ORDER)
        if keep_dots:
            # Namco: after a death the shared counter (7/17/32) takes over and
            # Blinky stops being Elroy until Clyde leaves the house.
            self.use_global = True
            self.global_counter = 0
            self.elroy_hold = True
        else:
            self.use_global = False
            self.elroy_hold = False
        pac_tx, pac_ty = 14, 23
        self.pac = Actor(pac_tx, pac_ty, "LEFT")
        self.pac.mouth = 0
        self.pac.anim = 0
        self.pac.eat_stop = 0
        # ghosts start positions
        self.ghosts = {
            "blinky": self._make_ghost("blinky", 14, 11, "LEFT", "outside"),
            "pinky": self._make_ghost("pinky", 14, 14, "DOWN", "house"),
            "inky": self._make_ghost("inky", 12, 14, "UP", "house"),
            "clyde": self._make_ghost("clyde", 16, 14, "UP", "house"),
        }
        self.scatter_targets = dict(SCATTER_TARGETS)
        self._fright_rng = 0x0001  # 16-bit LFSR seed (arcade-style)
        # Ghosts whose house limit is 0 leave straight away (Pinky always on a
        # fresh level; Inky from level 2; Clyde from level 3).
        self._release_check()
        # Freeze all movement opcodes while the intro jingle plays; start when it ends.
        # After a death (keep_dots), short READY only — no jingle.
        self.waiting_for_jingle = False
        if kill:
            self.ready_timer = int(2 * FPS)
        elif not keep_dots:
            self.ready_timer = self.synth.play_start_jingle()
            self.waiting_for_jingle = True
        else:
            self.ready_timer = int(2 * FPS)

    def _make_ghost(self, name, tx, ty, direction, status):
        g = Actor(tx, ty, direction)
        g.name = name
        g.status = status  # house | leaving | outside | eyes | entering
        g.frightened = False
        g.in_tunnel = False
        g.anim = 0
        g.target = (tx, ty)
        g.home_y = ty * TILE + TILE // 2
        return g

    def start_game(self):
        self._reset_session()
        self._start_level()

    # -- input ---------------------------------------------------------------
    def handle_events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return False
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_F11 or (
                    ev.key == pygame.K_RETURN and (ev.mod & pygame.KMOD_ALT)
                ):
                    self._toggle_fullscreen()
                    continue
                if self.state == State.MENU:
                    self._menu_key(ev.key)
                elif self.state in (State.HELP, State.ABOUT, State.ROLL_CALL):
                    if ev.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_BACKSPACE, pygame.K_z):
                        self.state = State.MENU
                        self.menu_idle = 0
                elif self.state == State.INTERMISSION:
                    if ev.key == pygame.K_ESCAPE:
                        self.synth.stop_all_loops()
                        self.state = State.MENU
                    elif ev.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_z):
                        self._finish_intermission()
                elif self.state == State.PLAYING:
                    if ev.key in (pygame.K_p, pygame.K_RETURN):
                        self.state = State.PAUSED
                        self.synth.stop_all_loops()
                    elif ev.key == pygame.K_ESCAPE:
                        self.synth.stop_all_loops()
                        self.state = State.MENU
                    else:
                        self._play_dir_key(ev.key)
                elif self.state == State.PAUSED:
                    if ev.key in (pygame.K_p, pygame.K_RETURN):
                        self.state = State.PLAYING
                    elif ev.key == pygame.K_ESCAPE:
                        self.state = State.MENU
                elif self.state in (State.READY, State.DYING, State.LEVEL_CLEAR,
                                    State.GAME_OVER, State.KILL_SCREEN):
                    if ev.key == pygame.K_ESCAPE:
                        self.synth.stop_all_loops()
                        self.state = State.MENU
                        self.menu_idle = 0
                    elif self.state in (State.READY, State.PLAYING, State.KILL_SCREEN):
                        self._play_dir_key(ev.key)
        # held keys for continuous buffer
        if self.state in (State.PLAYING, State.READY, State.KILL_SCREEN):
            keys = pygame.key.get_pressed()
            if keys[pygame.K_UP] or keys[pygame.K_w]:
                self.pac.next_dir = "UP"
            elif keys[pygame.K_DOWN] or keys[pygame.K_s]:
                self.pac.next_dir = "DOWN"
            elif keys[pygame.K_LEFT] or keys[pygame.K_a]:
                self.pac.next_dir = "LEFT"
            elif keys[pygame.K_RIGHT] or keys[pygame.K_d]:
                self.pac.next_dir = "RIGHT"
        return True

    def _open_window(self, flags=0):
        """Open a 600x400 window centered on the desktop (or fullscreen desktop)."""
        if self.fullscreen:
            info = pygame.display.Info()
            return pygame.display.set_mode((info.current_w, info.current_h), pygame.FULLSCREEN)
        # Center the 600x400 window on the laptop screen
        os.environ["SDL_VIDEO_CENTERED"] = "1"
        if "SDL_VIDEO_WINDOW_POS" in os.environ:
            del os.environ["SDL_VIDEO_WINDOW_POS"]
        try:
            info = pygame.display.Info()
            if info.current_w > 0 and info.current_h > 0:
                wx = max(0, (info.current_w - WINDOW_W) // 2)
                wy = max(0, (info.current_h - WINDOW_H) // 2)
                os.environ["SDL_VIDEO_WINDOW_POS"] = f"{wx},{wy}"
        except Exception:
            pass
        return pygame.display.set_mode((WINDOW_W, WINDOW_H), flags)

    def _prepare_screen(self):
        """(Re)build the letterbox buffer after every set_mode()."""
        self.screen.fill(BLACK)
        sw, sh = self.screen.get_size()
        self._scaled = pygame.Surface((SCALED_W, SCALED_H)).convert()
        self._scaled_pos = ((sw - SCALED_W) // 2, (sh - SCALED_H) // 2)
        self._rot_cache.clear()

    def _toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        self.screen = self._open_window()
        self._prepare_screen()

    def _menu_key(self, key):
        self.menu_idle = 0
        if key in (pygame.K_UP, pygame.K_w):
            self.menu_idx = (self.menu_idx - 1) % len(self.menu_items)
            self.synth.play("menu_move")
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.menu_idx = (self.menu_idx + 1) % len(self.menu_items)
            self.synth.play("menu_move")
        elif key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_z):
            self.synth.play("menu_select")
            item = self.menu_items[self.menu_idx]
            if item == "PLAY GAME":
                self.start_game()
            elif item == "ROLL CALL":
                self._begin_roll_call()
            elif item == "HELP":
                self.state = State.HELP
            elif item == "ABOUT":
                self.state = State.ABOUT
            elif item == "EXIT":
                pygame.event.post(pygame.event.Event(pygame.QUIT))
        elif key == pygame.K_ESCAPE:
            pygame.event.post(pygame.event.Event(pygame.QUIT))

    def _begin_roll_call(self):
        self.state = State.ROLL_CALL
        self.roll_timer = 0
        self.roll_phase = 0
        # demo actors for the chase strip
        self.roll_pac_x = -20.0
        self.roll_ghost_x = -80.0
        self.roll_power = False
        self.roll_scared = False

    def _start_intermission(self, kind):
        self.state = State.INTERMISSION
        self.intermission_kind = kind
        self.intermission_timer = 0
        self.synth.stop_all_loops()
        # actors: pac + blinky crossing the screen
        self.inter_actors = {
            "pac_x": -30.0,
            "blinky_x": -70.0,
            "phase": 0,
            "tear": False,
            "naked": False,
            "big": False,
            "scared": False,
        }

    def _finish_intermission(self):
        self._start_level()

    def _play_dir_key(self, key):
        mapping = {
            pygame.K_UP: "UP", pygame.K_w: "UP",
            pygame.K_DOWN: "DOWN", pygame.K_s: "DOWN",
            pygame.K_LEFT: "LEFT", pygame.K_a: "LEFT",
            pygame.K_RIGHT: "RIGHT", pygame.K_d: "RIGHT",
        }
        if key in mapping:
            self.pac.next_dir = mapping[key]

    # -- update --------------------------------------------------------------
    def update(self):
        self.frame += 1
        self.logic_frames += 1
        self.menu_anim += 1
        if self.state == State.MENU:
            self.menu_idle += 1
            if self.menu_idle >= 8 * FPS:
                self._begin_roll_call()
            return
        if self.state == State.ROLL_CALL:
            self._update_roll_call()
            return
        if self.state == State.INTERMISSION:
            self._update_intermission()
            return
        if self.state in (State.HELP, State.ABOUT, State.PAUSED):
            return
        if self.state == State.READY:
            # Pac-Man / ghost opcodes frozen while READY! / intro jingle plays
            self.ready_timer -= 1
            # Real audio: if jingle ends early, start; never wait past the timed length
            # (dummy audio drivers may report busy forever, so timer is authoritative)
            if self.waiting_for_jingle and self.ready_timer > 0:
                if self.synth.ok and not self.synth.jingle_busy():
                    # Only trust an early end after we've heard a bit of the jingle
                    elapsed = self.synth.jingle_frames - self.ready_timer
                    if elapsed > FPS // 2:
                        self.ready_timer = 0
            if self.ready_timer <= 0:
                self.waiting_for_jingle = False
                self.state = State.PLAYING if self.level < 256 else State.KILL_SCREEN
            return
        if self.state == State.DYING:
            self.dying_timer -= 1
            if self.dying_timer == int(1.5 * FPS):
                self.synth.play("death")
            if self.dying_timer <= 0:
                self.lives -= 1
                if self.lives < 0:
                    self.state = State.GAME_OVER
                    self.game_over_timer = int(3 * FPS)
                    self.synth.stop_all_loops()
                else:
                    self._start_level(keep_dots=True)
            return
        if self.state == State.LEVEL_CLEAR:
            self.clear_timer -= 1
            if self.clear_timer <= 0:
                completed = self.level
                self.level += 1
                fn, _ = fruit_for_level(completed)
                if fn not in self.fruit_history:
                    self.fruit_history.append(fn)
                if len(self.fruit_history) > 7:
                    self.fruit_history = self.fruit_history[-7:]
                kind = INTERMISSION_AFTER.get(completed)
                if kind and self.level < 256:
                    self._start_intermission(kind)
                else:
                    self._start_level()
            return
        if self.state == State.GAME_OVER:
            self.game_over_timer -= 1
            if self.game_over_timer <= 0:
                self.state = State.MENU
                self.menu_idle = 0
            return

        # PLAYING or KILL_SCREEN
        if self.eat_pause > 0:
            self.eat_pause -= 1
            self._update_score_popups()
            return

        self._update_mode()
        self._update_pac()
        self._update_ghosts()
        self._check_collisions()
        self._update_fruit()
        self._update_score_popups()
        self._update_audio_loops()
        self.dot_timer += 1
        if self.dot_timer >= force_release_frames(self.level):
            self._force_release_next()
            self.dot_timer = 0

        if self.dots_left <= 0 and self.level < 256:
            self.state = State.LEVEL_CLEAR
            self.clear_timer = int(2.5 * FPS)
            self.synth.stop_all_loops()

    def _update_roll_call(self):
        self.roll_timer += 1
        # Phase: reveal ghosts one by one, then pts, then chase demo
        # 0-60 title, then each ghost ~90 frames, then pts, then chase
        reveal_at = 40 + self.roll_phase * 70
        if self.roll_phase < 4 and self.roll_timer >= reveal_at:
            self.roll_phase += 1
            self.synth.play("menu_move")
        if self.roll_timer > 40 + 4 * 70 + 90:
            # chase demo
            spd = 1.4
            if not self.roll_scared:
                self.roll_pac_x += spd
                self.roll_ghost_x += spd
                if self.roll_pac_x > 200 and not self.roll_power:
                    self.roll_power = True
                    self.roll_scared = True
                    self.synth.play("eat_ghost")
            else:
                self.roll_pac_x += spd * 1.2
                self.roll_ghost_x += spd * 0.7
            if self.roll_pac_x > INTERNAL_W + 40:
                self.roll_pac_x = -20
                self.roll_ghost_x = -80
                self.roll_power = False
                self.roll_scared = False
        if self.roll_timer > 22 * FPS:
            self.state = State.MENU
            self.menu_idle = 0

    def _update_intermission(self):
        self.intermission_timer += 1
        a = self.inter_actors
        t = self.intermission_timer
        kind = self.intermission_kind
        # Shared: run left-to-right then reverse scenes
        if kind == 1:
            # I: Blinky chases Pac, exit; big Pac chases scared Blinky
            if a["phase"] == 0:
                a["pac_x"] += 2.2
                a["blinky_x"] += 2.2
                if a["pac_x"] > INTERNAL_W + 40:
                    a["phase"] = 1
                    a["pac_x"] = INTERNAL_W + 40
                    a["blinky_x"] = INTERNAL_W + 80
                    a["big"] = True
                    a["scared"] = True
            else:
                a["pac_x"] -= 2.6
                a["blinky_x"] -= 1.8
                if a["pac_x"] < -60:
                    self._finish_intermission()
        elif kind == 2:
            # II: chase, Blinky hits nail mid-screen, tear
            if a["phase"] == 0:
                a["pac_x"] += 2.0
                a["blinky_x"] += 2.0
                if a["blinky_x"] >= INTERNAL_W // 2:
                    a["tear"] = True
                    a["phase"] = 1
            elif a["phase"] == 1:
                a["pac_x"] += 2.0
                a["blinky_x"] += 1.2  # snagged, slower
                if a["pac_x"] > INTERNAL_W + 40:
                    self._finish_intermission()
        else:
            # III: chase with tear, then naked Blinky dragging sheet
            if a["phase"] == 0:
                a["tear"] = True
                a["pac_x"] += 2.0
                a["blinky_x"] += 2.0
                if a["pac_x"] > INTERNAL_W + 40:
                    a["phase"] = 1
                    a["naked"] = True
                    a["tear"] = False
                    a["pac_x"] = -999
                    a["blinky_x"] = -40
            else:
                a["blinky_x"] += 1.4
                if a["blinky_x"] > INTERNAL_W + 60:
                    self._finish_intermission()
        if t > 12 * FPS:
            self._finish_intermission()

    def _update_mode(self):
        if self.fright_timer > 0:
            self.fright_timer -= 1
            if self.fright_timer == 0:
                for g in self.ghosts.values():
                    g.frightened = False
                self.ghost_score_idx = 0
            return
        self.mode_timer -= 1
        if self.mode_timer <= 0:
            self.mode_idx = min(self.mode_idx + 1, len(self.mode_schedule) - 1)
            self.global_mode = self.mode_schedule[self.mode_idx][0]
            self.mode_timer = self.mode_schedule[self.mode_idx][1]
            for g in self.ghosts.values():
                if g.status == "outside" and not g.frightened:
                    g.dir = OPPOSITE[g.dir]

    def _pac_speed(self):
        d = level_data(self.level)
        pct = d.pac_fright if (self.fright_timer > 0 and d.pac_fright) else d.pac
        return FULL_SPEED * pct / 100.0

    # ------------------------------------------------------------------
    # Ghost AI 1:1 (Namco arcade / Pac-Man Dossier)
    # ------------------------------------------------------------------
    def _elroy_stage(self):
        """Cruise Elroy 0/1/2 from the Namco per-level dots-left table."""
        if self.level >= 256:
            return 0
        # After a death, Elroy is suppressed until Clyde has left the house
        if self.elroy_hold and self.ghosts["clyde"].status in ("house", "leaving", "entering"):
            return 0
        d = level_data(self.level)
        if self.dots_left <= d.e2_dots:
            return 2
        if self.dots_left <= d.e1_dots:
            return 1
        return 0

    def _ghost_target(self, g):
        """Chase / scatter / eyes target tile — arcade personalities + Pinky/Inky UP bug."""
        if g.status == "eyes":
            return (14, 11)  # ghost-house door
        if g.frightened:
            return g.tile  # unused; frightened picks via RNG
        # Cruise Elroy: Blinky ignores scatter and always chases
        elroy = self._elroy_stage() if g.name == "blinky" else 0
        if self.global_mode == "scatter" and elroy == 0:
            return self.scatter_targets[g.name]

        ptx, pty = self.pac.tile
        pdir = self.pac.dir
        pdx, pdy = DIRS[pdir]

        if g.name == "blinky":
            return (ptx, pty)

        if g.name == "pinky":
            # Ambush 4 ahead. Arcade overflow: facing UP also subtracts 4 from X.
            if pdir == "UP":
                return (ptx - 4, pty - 4)
            return (ptx + pdx * 4, pty + pdy * 4)

        if g.name == "inky":
            # Pivot = 2 ahead of Pac (same UP overflow), then 2*(pivot - Blinky)
            if pdir == "UP":
                ax, ay = ptx - 2, pty - 2
            else:
                ax, ay = ptx + pdx * 2, pty + pdy * 2
            bx, by = self.ghosts["blinky"].tile
            return (2 * ax - bx, 2 * ay - by)

        # Clyde (Pokey): chase when Euclidean distance > 8 tiles, else scatter
        gx, gy = g.tile
        if (gx - ptx) * (gx - ptx) + (gy - pty) * (gy - pty) > 64:
            return (ptx, pty)
        return self.scatter_targets["clyde"]

    def _ghost_speed(self, g):
        d = level_data(self.level)
        if g.status == "eyes":
            return FULL_SPEED * 2.0
        if g.frightened:
            return FULL_SPEED * ((d.gh_fright or 50) / 100.0)
        pct = d.gh
        if g.name == "blinky" and g.status == "outside":
            elroy = self._elroy_stage()
            if elroy == 2:
                pct = d.e2_spd
            elif elroy == 1:
                pct = d.e1_spd
        if self._in_tunnel(g):
            pct = d.gh_tunnel
        return FULL_SPEED * pct / 100.0

    def _in_tunnel(self, actor):
        tx, ty = actor.tile
        if ty == 14 and (tx <= 5 or tx >= 22):
            return True
        return False

    def _can_move(self, actor, direction, door_ok=False):
        dx, dy = DIRS[direction]
        tx, ty = actor.tile
        ntx, nty = tx + dx, ty + dy
        if nty < 0 or nty >= MAZE_H:
            return False
        if ntx < 0 or ntx >= MAZE_W:
            return ty == 14  # tunnel row
        return self._tile_passable(ntx, nty, door_ok=door_ok)

    def _tunnel_wrap(self, actor):
        if actor.x < -TILE:
            actor.x = MAZE_PX_W + TILE
        elif actor.x > MAZE_PX_W + TILE:
            actor.x = -TILE

    def _advance(self, actor, speed, door_ok=False):
        """Move along rails. Never overshoot a wall — snap to tile center instead."""
        dx, dy = DIRS[actor.dir]
        cx, cy = actor.center_of_tile()
        # stay on rails (perpendicular axis)
        if dx != 0:
            actor.y = cy
        if dy != 0:
            actor.x = cx

        if not self._can_move(actor, actor.dir, door_ok=door_ok):
            # glide to center then stop — fixes permanent off-center stuck
            if dx > 0:
                actor.x = min(actor.x + speed, cx) if actor.x < cx else cx
            elif dx < 0:
                actor.x = max(actor.x - speed, cx) if actor.x > cx else cx
            elif dy > 0:
                actor.y = min(actor.y + speed, cy) if actor.y < cy else cy
            elif dy < 0:
                actor.y = max(actor.y - speed, cy) if actor.y > cy else cy
            self._tunnel_wrap(actor)
            return abs(actor.x - cx) > 0.05 or abs(actor.y - cy) > 0.05

        actor.x += dx * speed
        actor.y += dy * speed
        self._tunnel_wrap(actor)
        return True

    def _update_pac(self):
        if self.pac.eat_stop > 0:
            self.pac.eat_stop -= 1
            return

        # Reverse is always immediate (arcade)
        if self.pac.next_dir == OPPOSITE.get(self.pac.dir) and self.pac.next_dir != self.pac.dir:
            self.pac.dir = self.pac.next_dir
        elif self.pac.next_dir != self.pac.dir:
            if self._try_turn(self.pac, self.pac.next_dir, corner=4):
                self.pac.dir = self.pac.next_dir

        moving = self._advance(self.pac, self._pac_speed())
        self.pac.stopped = not moving

        # If stopped at center, accept a buffered turn even if slightly late
        if self.pac.stopped and self.pac.next_dir != self.pac.dir:
            cx, cy = self.pac.center_of_tile()
            self.pac.x, self.pac.y = cx, cy
            if self._can_move(self.pac, self.pac.next_dir):
                self.pac.dir = self.pac.next_dir
                self.pac.stopped = False
                self._advance(self.pac, self._pac_speed())

        if not self.pac.stopped:
            self.pac.anim += 1
            if self.pac.anim % 3 == 0:
                self.pac.mouth = (self.pac.mouth + 1) % 3
        self._eat_tile()

    def _try_turn(self, actor, new_dir, corner=0):
        if not self._can_move(actor, new_dir):
            return False
        cx, cy = actor.center_of_tile()
        ndx, ndy = DIRS[new_dir]
        # reverse handled separately; cornering for 90° turns
        if ndx != 0:  # horizontal turn
            if abs(actor.y - cy) <= corner and abs(actor.x - cx) <= corner + 2:
                actor.y = cy
                return True
        else:
            if abs(actor.x - cx) <= corner and abs(actor.y - cy) <= corner + 2:
                actor.x = cx
                return True
        return False

    def _snap_axis(self, actor):
        dx, dy = DIRS[actor.dir]
        cx, cy = actor.center_of_tile()
        if dx != 0:
            actor.y = cy
        if dy != 0:
            actor.x = cx

    def _eat_tile(self):
        tx, ty = self.pac.tile
        if not (0 <= tx < MAZE_W and 0 <= ty < MAZE_H):
            return
        ch = self.grid[ty][tx]
        if ch == ".":
            self.grid[ty][tx] = " "
            self.dot_surf.fill(BLACK, (tx * TILE, ty * TILE, TILE, TILE))
            self.dots_left -= 1
            self.dots_eaten += 1
            self._add_score(DOT_POINTS)
            self.pac.eat_stop = DOT_STALL
            self.dot_timer = 0
            self._on_dot_eaten()
            name = "waka0" if self.waka_toggle == 0 else "waka1"
            self.waka_toggle ^= 1
            self.synth.play(name, channel="waka")
        elif ch == "o":
            self.grid[ty][tx] = " "
            self.dots_left -= 1
            self.dots_eaten += 1
            self._add_score(PELLET_POINTS)
            self.pac.eat_stop = PELLET_STALL
            self.dot_timer = 0
            self._on_dot_eaten()
            self._trigger_fright()

    def _on_dot_eaten(self):
        if self.use_global:
            self.global_counter += 1
        else:
            for name in self.release_order:  # only the preferred ghost counts
                if self.ghosts[name].status == "house":
                    self.house_dots[name] += 1
                    break
        self._release_check()
        # fruit triggers
        if self.dots_eaten in FRUIT_DOTS and self.fruit_shown < 2:
            self._spawn_fruit()

    def _release_check(self):
        """Namco ghost-house rule: release in Pinky > Inky > Clyde order."""
        for name in self.release_order:
            g = self.ghosts[name]
            if g.status != "house":
                continue
            if self.use_global:
                limit, count = GLOBAL_LIMITS[name], self.global_counter
            else:
                limit, count = house_limit(self.level, name), self.house_dots[name]
            if count < limit:
                break
            g.status = "leaving"
            if self.use_global and name == "clyde":
                self.use_global = False  # arcade drops back to personal counters

    def _force_release_next(self):
        for name in self.release_order:
            g = self.ghosts[name]
            if g.status == "house":
                g.status = "leaving"
                break

    def _trigger_fright(self):
        t = fright_time(self.level)
        if t <= 0:
            for g in self.ghosts.values():
                if g.status == "outside":
                    g.dir = OPPOSITE[g.dir]
            return
        self.fright_timer = int(t * FPS)
        self.fright_flash_frames = level_data(self.level).flashes * FRIGHT_FLASH_FRAMES
        self.ghost_score_idx = 0
        # Reseed fright LFSR from frame counter (arcade pulls a fresh stream)
        self._fright_rng = ((self.frame * 0x5BD1) ^ 0xACE1) & 0xFFFF or 1
        for g in self.ghosts.values():
            if g.status in ("outside", "leaving"):
                g.frightened = True
                g.dir = OPPOSITE[g.dir]

    def _spawn_fruit(self):
        self.fruit_shown += 1
        name, pts = fruit_for_level(self.level)
        self.fruit = {"name": name, "pts": pts, "x": 14 * TILE, "y": 17 * TILE + 4}
        self.fruit_timer = int(random.uniform(*FRUIT_TIME) * FPS)

    def _update_fruit(self):
        if self.fruit is None:
            return
        self.fruit_timer -= 1
        if self.fruit_timer <= 0:
            self.fruit = None
            return
        px, py = self.pac.x, self.pac.y
        if abs(px - self.fruit["x"]) < 8 and abs(py - self.fruit["y"]) < 8:
            self._add_score(self.fruit["pts"])
            self.score_popups.append({
                "x": self.fruit["x"], "y": self.fruit["y"],
                "text": str(self.fruit["pts"]), "timer": FPS
            })
            self.synth.play("eat_fruit")
            self.fruit = None

    def _add_score(self, n):
        self.score += n
        if self.score > self.high_score:
            self.high_score = self.score
        if not self.extra_life_awarded and self.score >= EXTRA_LIFE_AT:
            self.extra_life_awarded = True
            self.lives += 1
            self.synth.play("extra_life")

    def _fright_rand_dir(self, g):
        """Namco frightened pick: LFSR -> R/D/L/U, then walk that order until legal."""
        s = self._fright_rng & 0xFFFF
        bit = ((s >> 0) ^ (s >> 2)) & 1
        s = ((s >> 1) | (bit << 15)) & 0xFFFF
        self._fright_rng = s
        start = (s >> 14) & 0x3  # 0=RIGHT, 1=DOWN, 2=LEFT, 3=UP
        for i in range(4):
            d = FRIGHT_DIR_ORDER[(start + i) % 4]
            if d != OPPOSITE[g.dir] and self._ghost_dir_allowed(g, d):
                return d
        for d in FRIGHT_DIR_ORDER:
            if self._ghost_dir_allowed(g, d):
                return d
        return g.dir

    def _ghost_dir_allowed(self, g, d):
        """Passable exit + arcade no-UP tiles (eyes may go UP everywhere)."""
        door_ok = g.status == "eyes"
        if not self._can_move(g, d, door_ok=door_ok):
            return False
        if d == "UP" and g.status != "eyes" and g.tile in NO_UP_TILES:
            return False
        return True

    def _choose_ghost_dir(self, g):
        """At tile center: pick exit. Chase/scatter = min Euclidean^2, ties UP>LEFT>DOWN>RIGHT."""
        if g.frightened and g.status != "eyes":
            return self._fright_rand_dir(g)

        target = self._ghost_target(g)
        tx, ty = g.tile
        best = None
        best_dist = 1e18
        for d in DIR_ORDER:  # arcade chase tie-break: UP, LEFT, DOWN, RIGHT
            if d == OPPOSITE[g.dir]:
                continue
            if not self._ghost_dir_allowed(g, d):
                continue
            dx, dy = DIRS[d]
            nx, ny = tx + dx, ty + dy
            dist = (nx - target[0]) * (nx - target[0]) + (ny - target[1]) * (ny - target[1])
            if dist < best_dist:
                best_dist = dist
                best = d
        if best is not None:
            return best
        if self._ghost_dir_allowed(g, OPPOSITE[g.dir]):
            return OPPOSITE[g.dir]
        return g.dir

    def _update_ghosts(self):
        for g in self.ghosts.values():
            g.anim += 1
            if g.status == "house":
                base_y = g.home_y if hasattr(g, "home_y") else g.y
                g.y = base_y + math.sin(g.anim * 0.15) * 2.0
                continue
            if g.status == "leaving":
                target_x = 14 * TILE + TILE // 2
                target_y = 11 * TILE + TILE // 2
                if abs(g.x - target_x) > 0.5:
                    step = min(1.0, abs(g.x - target_x))
                    g.x += step if g.x < target_x else -step
                    g.dir = "RIGHT" if g.x < target_x else "LEFT"
                elif abs(g.y - target_y) > 0.5:
                    g.y -= min(1.0, abs(g.y - target_y))
                    g.dir = "UP"
                else:
                    g.x, g.y = target_x, target_y
                    g.status = "outside"
                    g.dir = "LEFT"
                    if g.name == "clyde":
                        self.elroy_hold = False
                continue
            if g.status == "entering":
                target_x = 14 * TILE + TILE // 2
                target_y = 14 * TILE + TILE // 2
                if abs(g.x - target_x) > 0.5:
                    g.x += 1.0 if g.x < target_x else -1.0
                elif abs(g.y - target_y) > 0.5:
                    g.y += 1.0
                    g.dir = "DOWN"
                else:
                    g.x, g.y = target_x, target_y
                    g.home_y = target_y
                    g.status = "leaving"
                    g.frightened = False
                continue

            door_ok = g.status == "eyes"
            # Arcade: at every tile center, choose among legal exits (never reverse
            # unless it's the only option). Covers corridors, corners, and crosses.
            if g.at_tile_center(tol=1.2):
                g.x, g.y = g.center_of_tile()
                g.dir = self._choose_ghost_dir(g)

            if not self._can_move(g, g.dir, door_ok=door_ok):
                g.x, g.y = g.center_of_tile()
                g.dir = self._choose_ghost_dir(g)

            self._advance(g, self._ghost_speed(g), door_ok=door_ok)

            if g.status == "eyes":
                tx, ty = g.tile
                if (tx, ty) in ((14, 11), (14, 12), (13, 14), (14, 14), (15, 14), (14, 13)):
                    g.status = "entering"

    def _check_collisions(self):
        ptx, pty = self.pac.tile
        for g in self.ghosts.values():
            if g.status in ("house", "leaving", "entering"):
                continue
            gtx, gty = g.tile
            if (gtx, gty) != (ptx, pty):
                continue
            if g.status == "eyes":
                continue
            if g.frightened:
                pts = GHOST_POINTS[min(self.ghost_score_idx, 3)]
                self.ghost_score_idx += 1
                self.ghost_kills += 1
                self._add_score(pts)
                if self.ghost_kills == 16:  # all 4 ghosts on all 4 pellets
                    self._add_score(ALL_GHOSTS_BONUS)
                self.score_popups.append({
                    "x": g.x, "y": g.y, "text": str(pts), "timer": FPS
                })
                g.frightened = False
                g.status = "eyes"
                self.eat_pause = 60
                self.synth.play("eat_ghost")
            else:
                self.state = State.DYING
                self.dying_timer = int(2.5 * FPS)
                self.synth.stop_all_loops()
                return

    def _update_score_popups(self):
        for p in self.score_popups[:]:
            p["timer"] -= 1
            if p["timer"] <= 0:
                self.score_popups.remove(p)

    def _update_audio_loops(self):
        if not self.synth.ok:
            return
        eyes = any(g.status == "eyes" for g in self.ghosts.values())
        if eyes:
            if not self.synth.channels["eyes"].get_busy():
                self.synth.play("eyes_return", loop=True, channel="eyes")
            self.synth.stop("siren")
            self.synth.stop("power")
        elif self.fright_timer > 0:
            if not self.synth.channels["power"].get_busy():
                self.synth.play("power_siren", loop=True, channel="power")
            self.synth.stop("siren")
            self.synth.stop("eyes")
        else:
            if not self.synth.channels["siren"].get_busy():
                self.synth.play("siren", loop=True, channel="siren")
            self.synth.stop("power")
            self.synth.stop("eyes")

    # -- draw ----------------------------------------------------------------
    def draw(self):
        self.canvas.fill(BLACK)
        if self.state == State.MENU:
            self._draw_menu()
        elif self.state == State.HELP:
            self._draw_help()
        elif self.state == State.ABOUT:
            self._draw_about()
        elif self.state == State.ROLL_CALL:
            self._draw_roll_call()
        elif self.state == State.INTERMISSION:
            self._draw_intermission()
        else:
            self._draw_hud()
            self._draw_maze()
            self._draw_actors()
            self._draw_overlays()
        # Scale internal canvas into the letterboxed rect (no per-frame allocation)
        pygame.transform.scale(self.canvas, (SCALED_W, SCALED_H), self._scaled)
        self.screen.blit(self._scaled, self._scaled_pos)
        pygame.display.flip()

    def _draw_menu(self):
        # logo
        logo = "KONDO'S"
        draw_text(self.canvas, logo, INTERNAL_W // 2 - len(logo) * 8, 28, BLINKY_C, self.font, 2)
        draw_text(self.canvas, logo, INTERNAL_W // 2 - len(logo) * 8 - 1, 27, PAC_YELLOW, self.font, 2)
        sub = "PACMAN PY PORT"
        draw_text(self.canvas, sub, INTERNAL_W // 2 - len(sub) * 4, 56, PAC_YELLOW, self.font, 1)
        draw_text(self.canvas, CREDIT, INTERNAL_W // 2 - len(CREDIT) * 4, 72, WHITE, self.font)
        draw_text(self.canvas, VERSION, INTERNAL_W - 40, INTERNAL_H - 16, GRAY, self.font)

        for i, item in enumerate(self.menu_items):
            y = 100 + i * 18
            col = WHITE if i == self.menu_idx else GRAY
            draw_text(self.canvas, item, INTERNAL_W // 2 - len(item) * 4, y, col, self.font)
            if i == self.menu_idx:
                frame = self.pac_frames[(self.menu_anim // 8) % 3]
                self.canvas.blit(frame, (INTERNAL_W // 2 - len(item) * 4 - 24, y - 4))

        # attract strip
        ax = (self.menu_anim // 2) % (INTERNAL_W + 80) - 40
        self.canvas.blit(self.pac_frames[(self.menu_anim // 6) % 3], (ax, 230))
        for i, name in enumerate(("blinky", "pinky", "inky", "clyde")):
            self.canvas.blit(self.ghost_body[name][(self.menu_anim // 10) % 2], (ax - 30 - i * 20, 230))

    def _draw_roll_call(self):
        draw_text(self.canvas, "CHARACTER / NICKNAME", 80, 16, WHITE, self.font)
        for i, (name, char, nick, col) in enumerate(GHOST_ROLL):
            if i >= self.roll_phase:
                break
            y = 48 + i * 28
            body = self.ghost_body[name][(self.menu_anim // 10) % 2]
            self.canvas.blit(body, (48, y - 4))
            draw_text(self.canvas, f"-{char}", 80, y, col, self.font)
            draw_text(self.canvas, f'"{nick}"', 200, y, col, self.font)

        if self.roll_phase >= 4:
            draw_text(self.canvas, "10 PTS", 120, 170, DOT_PINK, self.font)
            pygame.draw.rect(self.canvas, DOT_PINK, (100, 173, 2, 2))
            draw_text(self.canvas, "50 PTS", 280, 170, DOT_PINK, self.font)
            pygame.draw.circle(self.canvas, DOT_PINK, (260, 174), 4)
            draw_text(self.canvas, f"{CREDIT}  {VERSION}", 140, 200, GRAY, self.font)

        # chase demo strip
        if self.roll_timer > 40 + 4 * 70 + 90:
            y = 230
            frame = self.pac_frames[(self.menu_anim // 6) % 3]
            if self.roll_scared:
                # Pac chasing scared ghosts right-to-left feel: still draw left-to-right swapped
                self.canvas.blit(frame, (int(self.roll_pac_x), y))
                for i, name in enumerate(("blinky", "pinky", "inky", "clyde")):
                    self.canvas.blit(
                        self.fright_frames[(self.menu_anim // 10) % 2],
                        (int(self.roll_ghost_x) + i * 20, y),
                    )
            else:
                self.canvas.blit(frame, (int(self.roll_pac_x), y))
                for i, name in enumerate(("blinky", "pinky", "inky", "clyde")):
                    self.canvas.blit(
                        self.ghost_body[name][(self.menu_anim // 10) % 2],
                        (int(self.roll_ghost_x) + i * 20, y),
                    )
            if self.roll_power and not self.roll_scared:
                pygame.draw.circle(self.canvas, DOT_PINK, (220, y + 8), 4)

        draw_text(self.canvas, "ESC / ENTER  BACK", 140, 256, GRAY, self.font)

    def _draw_intermission(self):
        a = self.inter_actors
        kind = self.intermission_kind
        title = {1: "INTERMISSION I", 2: "INTERMISSION II", 3: "INTERMISSION III"}[kind]
        draw_text(self.canvas, title, INTERNAL_W // 2 - len(title) * 4, 20, PAC_YELLOW, self.font)
        y = 140
        # nail for II
        if kind == 2:
            pygame.draw.line(self.canvas, WHITE, (INTERNAL_W // 2, y + 20), (INTERNAL_W // 2, y + 28), 2)
            pygame.draw.circle(self.canvas, GRAY, (INTERNAL_W // 2, y + 18), 2)

        pac_x = a["pac_x"]
        blinky_x = a["blinky_x"]
        if pac_x > -80:
            frame = self.pac_frames[(self.intermission_timer // 6) % 3]
            if a.get("big"):
                big = pygame.transform.scale(frame, (32, 32))
                self.canvas.blit(big, (int(pac_x) - 8, y - 8))
            else:
                facing = "LEFT" if (kind == 1 and a["phase"] == 1) else "RIGHT"
                if facing == "LEFT":
                    frame = pygame.transform.flip(frame, True, False)
                self.canvas.blit(frame, (int(pac_x), y))

        if blinky_x > -80:
            if a.get("naked"):
                # eyes + stick legs + dragging sheet
                self.canvas.blit(self.eyes_surf, (int(blinky_x), y))
                pygame.draw.line(self.canvas, WHITE, (int(blinky_x) + 6, y + 14), (int(blinky_x) + 6, y + 22), 1)
                pygame.draw.line(self.canvas, WHITE, (int(blinky_x) + 10, y + 14), (int(blinky_x) + 10, y + 22), 1)
                pygame.draw.rect(self.canvas, BLINKY_C, (int(blinky_x) - 18, y + 10, 16, 10))
            elif a.get("scared"):
                self.canvas.blit(self.fright_frames[(self.intermission_timer // 8) % 2], (int(blinky_x), y))
            else:
                body = self.ghost_body["blinky"][(self.intermission_timer // 8) % 2]
                self.canvas.blit(body, (int(blinky_x), y))
                if a.get("tear"):
                    # torn hem
                    pygame.draw.rect(self.canvas, BLACK, (int(blinky_x) + 4, y + 12, 8, 4))
                    pygame.draw.line(self.canvas, WHITE, (int(blinky_x) + 6, y + 14), (int(blinky_x) + 6, y + 22), 1)

        draw_text(self.canvas, "ENTER TO SKIP", 160, 240, GRAY, self.font)

    def _draw_help(self):
        draw_text(self.canvas, "HELP", 200, 20, PAC_YELLOW, self.font, 2)
        lines = [
            "ARROWS / WASD  MOVE",
            "P / ENTER  PAUSE",
            "ESC  MENU",
            "",
            "DOT           10",
            "POWER PELLET  50",
            "GHOSTS  200 400 800 1600",
            "FRUIT  100 TO 5000",
            "EXTRA LIFE AT 10000",
            "",
            "LEVELS 1-255  THEN KILL",
            "SCREEN AT 256",
            "",
            "PRESS ESC TO RETURN",
        ]
        for i, line in enumerate(lines):
            draw_text(self.canvas, line, 40, 60 + i * 12, WHITE, self.font)

    def _draw_about(self):
        draw_text(self.canvas, TITLE[:14], 80, 40, PAC_YELLOW, self.font)
        draw_text(self.canvas, "PACMAN PY PORT", 100, 56, PAC_YELLOW, self.font)
        draw_text(self.canvas, f"VERSION {VERSION}", 140, 88, WHITE, self.font)
        draw_text(self.canvas, CREDIT, 180, 108, WHITE, self.font)
        draw_text(self.canvas, "FAMICOM-STYLE TRIBUTE", 80, 140, GRAY, self.font)
        draw_text(self.canvas, "MADE IN PYTHON+PYGAME", 80, 156, GRAY, self.font)
        draw_text(self.canvas, "SPEED = FAMICOM  60 FPS", 80, 172, GRAY, self.font)
        draw_text(self.canvas, "PRESS ESC TO RETURN", 100, 220, WHITE, self.font)

    def _draw_hud(self):
        draw_text(self.canvas, "1UP", 40, 4, WHITE, self.font)
        draw_text(self.canvas, f"{self.score:06d}", 24, 16, WHITE, self.font)
        draw_text(self.canvas, "HIGH SCORE", 24, 40, WHITE, self.font)
        draw_text(self.canvas, f"{self.high_score:06d}", 24, 52, WHITE, self.font)
        draw_text(self.canvas, f"L{self.level}", 40, 80, GRAY, self.font)

        # lives
        for i in range(max(0, self.lives)):
            self.canvas.blit(self.pac_frames[1], (360 + i * 18, 20))
        # fruit history
        for i, _ in enumerate(self.fruit_history[-5:]):
            draw_text(self.canvas, "F", 360 + i * 16, 50, CLYDE_C, self.font)

    def _draw_maze(self):
        canvas = self.canvas
        # flash on level clear
        if self.state == State.LEVEL_CLEAR and (self.clear_timer // 8) % 2 == 0:
            canvas.blit(self.flash_surf, (MAZE_OX, MAZE_OY))
        else:
            canvas.blit(self.maze_surf, (MAZE_OX, MAZE_OY))
        canvas.blit(self.dot_surf, (MAZE_OX, MAZE_OY))

        if (self.frame // 10) % 2 == 0:
            grid = self.grid
            for px, py in self.pellets:
                if grid[py // TILE][px // TILE] == "o":
                    canvas.blit(self.pellet_surf, (MAZE_OX + px, MAZE_OY + py))

        if self.junk_tiles and self.level >= 256:
            cols = (BLINKY_C, PINKY_C, INKY_C, CLYDE_C, PAC_YELLOW, WHITE)
            f8 = self.frame // 8
            for tx, ty, ch in self.junk_tiles:
                draw_text(canvas, ch, MAZE_OX + tx * TILE, MAZE_OY + ty * TILE,
                          cols[(tx + ty + f8) % 6], self.font)

        if self.fruit and self.level < 256:
            fx = MAZE_OX + int(self.fruit["x"]) - 4
            fy = MAZE_OY + int(self.fruit["y"]) - 4
            pygame.draw.circle(canvas, BLINKY_C, (fx + 4, fy + 4), 5)
            pygame.draw.circle(canvas, (0, 0xB8, 0), (fx + 4, fy + 1), 2)

    def _blit_rot(self, surf, x, y, direction):
        key = (id(surf), direction)
        s = self._rot_cache.get(key)
        if s is None:
            angles = {"RIGHT": 0, "UP": 90, "LEFT": 180, "DOWN": 270}
            s = pygame.transform.rotate(surf, angles.get(direction, 0)).convert()
            s.set_colorkey(BLACK)
            self._rot_cache[key] = s
        self.canvas.blit(s, (MAZE_OX + int(x) - 8, MAZE_OY + int(y) - 8))

    def _draw_actors(self):
        if self.state == State.DYING:
            # death shrink
            t = 1.0 - self.dying_timer / (2.5 * FPS)
            if t < 0.7:
                frame = self.pac_frames[min(2, int(t * 5))]
                self._blit_rot(frame, self.pac.x, self.pac.y, self.pac.dir)
            return

        # fruit already drawn
        for g in self.ghosts.values():
            self._draw_ghost(g)

        if self.state != State.DYING:
            frame = self.pac_frames[self.pac.mouth if not self.pac.stopped else 1]
            self._blit_rot(frame, self.pac.x, self.pac.y, self.pac.dir)

        for p in self.score_popups:
            draw_text(
                self.canvas, p["text"],
                MAZE_OX + int(p["x"]) - 8, MAZE_OY + int(p["y"]) - 12,
                WHITE, self.font
            )

    def _draw_ghost(self, g):
        x = MAZE_OX + int(g.x) - 8
        y = MAZE_OY + int(g.y) - 8
        if g.status == "eyes":
            self.canvas.blit(self.eyes_surf, (x, y))
            return
        if g.frightened:
            flash_phase = (self.fright_timer <= self.fright_flash_frames
                           and (self.fright_timer * 2 // FRIGHT_FLASH_FRAMES) % 2 == 0)
            frames = self.fright_flash if flash_phase else self.fright_frames
            self.canvas.blit(frames[(g.anim // 8) % 2], (x, y))
            return
        body = self.ghost_body[g.name][(g.anim // 8) % 2]
        self.canvas.blit(body, (x, y))
        # pupils toward dir
        dx, dy = DIRS[g.dir]
        pygame.draw.circle(self.canvas, (0, 0, 0xBC), (x + 5 + dx, y + 6 + dy), 1)
        pygame.draw.circle(self.canvas, (0, 0, 0xBC), (x + 11 + dx, y + 6 + dy), 1)

    def _draw_overlays(self):
        if self.state == State.READY:
            draw_text(self.canvas, "READY!", MAZE_OX + 80, MAZE_OY + 160, PAC_YELLOW, self.font)
        elif self.state == State.PAUSED:
            draw_text(self.canvas, "PAUSED", MAZE_OX + 80, MAZE_OY + 120, WHITE, self.font)
        elif self.state == State.GAME_OVER:
            draw_text(self.canvas, "GAME OVER", MAZE_OX + 64, MAZE_OY + 160, BLINKY_C, self.font)
        elif self.state == State.KILL_SCREEN:
            if self.frame % 60 < 40:
                draw_text(self.canvas, "KILL SCREEN", MAZE_OX + 56, MAZE_OY + 4, BLINKY_C, self.font)
            draw_text(self.canvas, "LEVEL 256", MAZE_OX + 72, MAZE_OY + 240, WHITE, self.font)

    # -- main loop -----------------------------------------------------------
    def run(self):
        """Drift-free 60 Hz fixed timestep.

        pygame's Clock.tick(60) only has 1 ms resolution (16 ms -> ~62 FPS, i.e.
        the game would run ~4% fast), so pace with perf_counter deadlines instead.
        If a frame runs long, extra logic steps catch up without extra draws.
        """
        perf = time.perf_counter
        next_t = perf()
        running = True
        while running:
            running = self.handle_events()
            self.update()
            self.draw()
            if self.frame_limit is not None and self.logic_frames >= self.frame_limit:
                break
            next_t += DT
            now = perf()
            lag = now - next_t
            skipped = 0
            while lag >= DT and skipped < 4:  # fell behind: catch up logic only
                self.update()
                next_t += DT
                lag -= DT
                skipped += 1
            if lag >= DT:  # hopelessly late (window drag, breakpoint): resync
                next_t = now
            elif lag < 0:
                wait = -lag
                if wait > 0.002:
                    time.sleep(wait - 0.0015)
                while perf() < next_t:
                    pass
        pygame.quit()
        return 0


def main():
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument("--frames", type=int, default=None,
                        help="Run N logic frames then exit (smoke test)")
    args = parser.parse_args()
    try:
        pygame.mixer.pre_init(44100, -16, 1, 512)
    except Exception:
        pass
    # Center 600x400 window on the laptop before the display opens
    os.environ["SDL_VIDEO_CENTERED"] = "1"
    pygame.init()
    game = Game(frame_limit=args.frames)
    raise SystemExit(game.run())


if __name__ == "__main__":
    main()
