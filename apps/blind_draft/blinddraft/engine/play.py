# -*- coding: utf-8 -*-
"""一张图和一场 BO（§13）。

这一层只做两件事：把双方的 Team Performance 之差加上 Map Residual 得到
Margin，以及把若干张图凑成一场 BO1/BO3。**没有第二次胜负骰**——Residual
本身就是那层随机，它代表引擎没有展开模拟的地图/经济/timing，所以它不进
任何 Player Story（MVP / LIFE GAME 只看 Roll）。
"""
import math

from . import params as PA


def map_residual(rng, scale=None):
    """§13.3 Logistic(0, MAP_SCALE) 的逆变换采样。一张图掷一次。"""
    scale = PA.MAP_SCALE if scale is None else scale
    if scale <= 0.0:
        return 0.0
    u = min(1.0 - 1e-12, max(1e-12, rng.random()))
    return scale * math.log(u / (1.0 - u))


class MapResult(object):
    def __init__(self, sa, sb, da, db, a, b, residual=0.0):
        self.sa, self.sb, self.da, self.db = sa, sb, da, db
        self.a, self.b = a, b
        self.residual = residual
        # §13.2 Final Margin = 双方表现差 + Map Residual，正者获胜。
        # 没有第二次 Bernoulli——残差本身就是那层随机。
        self.margin = (sa - sb) + residual
        self.winner_a = self.margin > 0

    def _pick(self, key, chooser):
        ta, tb = chooser(self.da, key=key), chooser(self.db, key=key)
        return ((ta, True) if chooser(key(ta), key(tb)) == key(ta)
                else (tb, False))

    @property
    def mvp(self):                        # §0.5 打得最好 = 最终有效火力最高
        return self._pick(lambda t: t.eff, max)

    @property
    def life(self):                       # §0.5 最超常
        return self._pick(lambda t: t.delta, max)

    @property
    def under(self):                      # §0.5 最崩
        return self._pick(lambda t: t.delta, min)


def play_map(a, b, rng, pressure, scale=None):
    sa, da = a.play_map(rng, pressure)
    sb, db = b.play_map(rng, pressure)
    return MapResult(sa, sb, da, db, a, b, map_residual(rng, scale))


class MatchResult(object):
    def __init__(self, a, b, bo, pressure, maps):
        self.a, self.b, self.bo, self.pressure, self.maps = a, b, bo, pressure, maps
        self.a_maps = sum(1 for m in maps if m.winner_a)
        self.b_maps = len(maps) - self.a_maps
        self.winner = a if self.a_maps > self.b_maps else b
        self.loser = b if self.winner is a else a


def play_match(a, b, rng, bo, pressure, scale=None):
    maps, aw, bw = [], 0, 0
    need = bo // 2 + 1
    while aw < need and bw < need:
        m = play_map(a, b, rng, pressure, scale)
        maps.append(m)
        if m.winner_a:
            aw += 1
        else:
            bw += 1
    return MatchResult(a, b, bo, pressure, maps)
