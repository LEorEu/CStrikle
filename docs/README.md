# 文档索引

这个仓库里有**两个游戏**，共用同一份选手数据库。之前所有文档堆在根目录，
分不清哪份属于哪个，所以按游戏拆开了。

## [guess-the-player/](guess-the-player/) — 猜选手（已上线）

CStrikle，blast.tv 那个 Counter-Strikle 的自建版：猜一名神秘 CS 职业选手，
按国籍 / 战队 / 年龄 / 位置 / Major 次数给反馈。带每日挑战、双人对战、
随机匹配和 LLM AI 对手。**产品说明在仓库根的 [README.md](../README.md)。**

## [blind-draft/](blind-draft/) — Blind Draft（在做）

用 $15 预算、在身份不完全公开的情况下签 5 名职业选手，组一支临时战队，
再让它去打一届真实的 Major。选人这一层已经可玩，比赛这一层还没做。

## 两边共用的

- [角色与战队口径.md](角色与战队口径.md) — 角色真值 = **生涯代表角色**，
  不是当前职务。两个游戏的位置字段都按这条走，Blind Draft 的 Draft Role
  也是它的下游。

---

## 还留在根目录的

`progress.md` / `task_plan.md` / `findings.md` 是 gitignore 掉的本地工作文件
（猜选手时期留下的），没有跟着搬，也不在版本库里。
