# -*- coding: utf-8 -*-
"""一个人、一张图、一个随机数（§6 / §8）。

Player Performance 这一层的全部内容：`form_delta` 把一个 uniform 反演成一条
非对称分布，`under_pressure` 只**扭曲**那个已经掷出来的结果而不再掷第二次。
这两条是 v2 和 v1 最本质的差别，所以单独一个文件，改动一眼可见。
"""
import statistics as st

from .params import CHOKE_AMP, p_up, sigma_down, sigma_up

NORM = st.NormalDist()


def form_delta(u, stability):
    """§6.2：一个 uniform 反演出一条非对称分布，每人每图**恰好一个 Player RNG**。

    u < p_down 落在负半支，否则落在正半支；两支各自有自己的宽度。这样
    「往哪边偏」和「偏多少」共用同一个 u，不需要先掷方向再掷幅度。
    """
    pu = p_up(stability)
    pd = 1.0 - pu
    if u < pd:                                  # 负半支：u/pd 映到 (0, .5)
        q = max(1e-9, u / pd) * 0.5
        return sigma_down(stability) * NORM.inv_cdf(q)
    q = 0.5 + min(1.0 - 1e-9, (u - pd) / pu) * 0.5    # 正半支
    return sigma_up(stability) * NORM.inv_cdf(q)


def under_pressure(delta, experience, pressure):
    """§8.3：压力不掷新骰子，只把**负面**结果按经验放大。正向发挥不受影响。"""
    if pressure <= 0.0 or delta >= 0.0:
        return delta, 0.0
    amp = 1.0 + CHOKE_AMP * pressure * (1.0 - experience / 100.0)
    return delta * amp, delta * amp - delta     # (新值, 因压力多丢的分)


class Roll(object):
    """一个人这张图的完整账本，逐项可加回 delta。"""

    __slots__ = ("card", "eff", "delta", "form", "choke", "capped", "weight")

    def __init__(self, card, eff, delta, form, choke, capped, weight):
        self.card, self.eff, self.delta = card, eff, delta
        self.form, self.choke, self.capped = form, choke, capped
        self.weight = weight
