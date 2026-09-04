# -*- coding: utf-8 -*-
"""形状受控的假队伍——只给验收和调参用，不参与任何一届真实比赛。

真实卡面五个维度是纠缠的（火力高的人往往稳定也高），拿真人做单变量实验永远
说不清是哪一维在动。所以这里造五个完全一样的人，只让要考察的那一维变化。
"""
from .team import Team


def fake_card(nick, fire, stab, exp=60, lead=25, pos="RIFLER"):
    return {"nickname": nick, "position": pos, "firepower": fire,
            "stability": stab, "experience": exp, "leadership": lead,
            "caller": pos == "IGL"}


def probe_team(label, fire, stab, exp=60, lead=25, igl_lead=None):
    """形状受控的探针队：五个人同参数，只有要考察的那一维在动。"""
    roster = [fake_card("%s%d" % (label, i), fire, stab, exp, lead)
              for i in range(4)]
    roster.append(fake_card("%sIGL" % label, fire, stab, exp,
                            igl_lead if igl_lead is not None else lead,
                            "IGL" if igl_lead is not None else "RIFLER"))
    return Team(label, roster)


def entry_probe(label, target, stab=70):
    """造一支 entry() 正好等于 target 的探针队。

    entry() 对火力是斜率 1 的线性函数（权重和为 1），所以一次修正就精确。
    """
    t = probe_team(label, 70.0, stab)
    return probe_team(label, 70.0 + (target - t.entry()), stab)
