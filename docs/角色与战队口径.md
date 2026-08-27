# 角色与战队语义终审名单（2026-07-18）

本轮把角色/战队/状态口径收束为四条规则并全部落地。以下是需要你一次性过目的
全部人工结论；除标注 ⚠ 的条目外，其余均有明确来源支撑。看完没有异议即封盘。

## 口径终稿

1. **角色真值 = 生涯代表角色**（大众记忆），不是当前职务、不是近三个月数据。
   现役用当前角色；退役/转岗用选手时期角色。
2. **Coach 只给"以教练身份被记住"的人**：停止打比赛 ≥3 年且此后持续执教
   （zhokiNg 型）保留 Coach；刚退役转教练组（<3 年，Attacker 型）回退选手期
   角色。Coach 的战队仍按 HLTV Top 100 快照显示。
3. **role_set 黄色白名单**：只允许 {IGL}、{AWPer}、{Rifler}、{Coach}、
   {IGL,AWPer}（指挥狙）、{AWPer,Rifler}（换狙型）。指挥默认持步枪，
   IGL 不再与 Rifler 构成黄色重叠。
4. **无战队统一"自由身"**：退役/未签约/下放/玩票不再是不同状态；对局反馈中
   无队者互相判绿。下放但在编算原队（nota=PARIVISION）；status 只留内部
   题库过滤用。

## 一、刚退役转岗 → 回退选手角色 + 自由身（已写覆盖，7 条）

| 选手 | 原显示 | 新显示 | 证据 |
|------|--------|--------|------|
| Attacker | Coach/TYLOO | **Rifler/自由身** | 2025-12 退役转 TYLOO 助教；生涯 TYLOO 步枪手、6 次 Major |
| gla1ve | Coach/100 Thieves | **IGL/自由身** | 打到 2024 Major；100T 教练为新职 |
| NBK- | Coach/3DMAX | **Rifler/自由身** | 打到 2026 年；2026-02 首次执教（3DMAX 助教） |
| AZR | Coach/FlyQuest | **IGL/自由身** | 2025-03 Talon 解散后停赛；2025-10 才任 FlyQuest 教练 |
| tiziaN | Coach/BIG | **Rifler/自由身** | BIG 打到 2023，近期转助教 |
| mou ⚠ | Coach/HOTU | **AWPer/自由身** | 2023-10 停赛（K23）、2024-11 任 HOTU 教练；停赛 2.75 年，贴近 3 年线，按"AVANGAR Major 决赛狙击手"的记忆归选手 |
| erkaSt ⚠ | Coach/FlyQuest | **Rifler(低置信)/自由身** | 本地数据过时：2025-08 已被 FlyQuest 移除（接任者就是 AZR）；选手期 2015-2019，具体位置证据弱 |

## 二、保留 Coach + 上榜战队（18 条，无覆盖改动）

zhokiNg(TYLOO)、NEO(Astralis)、B1ad3(NaVi)、zonic(Falcons)、Xizt(NIP)、
TaZ(BC.Game)、daps(NRG)、dephh(M80)、doto(HEROIC)、HUNDEN(Sashi)、
pita(EYEBALLERS)、LETN1(MIBR)、SEMPHIS(Voca)、KrizzeN(FURIA)、
S0tF1k(Spirit)、balblna(K27)、zEVES(Metizport)、**Xyp9x(MOUZ) ⚠**

- daps 的 2025 Major 是教练身份紧急替补（2021-06 起持续执教 EG→NRG），不影响 Coach 判定。
- Xizt 2021 退役后走分析师→教练路线多年，按转型完成算 Coach。
- ⚠ **Xyp9x** 是唯一真正的边界案例：停赛约 4 年、现 MOUZ 助教，按规则算
  Coach；但他作为"五冠 clutch minister"的选手记忆极强。若你倾向按大众记忆
  显示 Rifler/自由身，加一条覆盖即可，说一声我来改。

## 三、此前待决三人（已写覆盖）

| 选手 | 结论 | 依据 |
|------|------|------|
| Stewie2K | **IGL**（自由身） | HLTV 生涯专题明确 IGL；退役型选手，近期数据不采信 |
| Maka | **IGL**，role_set 含 AWPer | HLTV 采访"IGL+AWP 双帽"；属指挥狙，猜 AWPer 得黄 |
| SmithZz | **AWPer**，role_set 含 Rifler | 你拍板 + 生涯狙击击杀 5434；换狙型，猜 Rifler 得黄 |

## 四、自动归类、无需逐个审（抽查即可）

- **指挥狙 {IGL,AWPer}（14 人）**：Jame、cadiaN、Maka、BENDJI、AlexRr、
  fox、stadodo、cxzi、Arya、Nifty、KNgV-、WOOD7、Nin9、Cool4st
- **换狙型 {AWPer,Rifler}（34 人）**：主位置仍按 Liquipedia 标签顺序
  （ZywOo/WorldEdit/markeloff=AWPer；coldzera/stavn/REZ/autimatic 等=Rifler），
  s1mple 由覆盖保持 AWPer。这批只影响黄色提示，主位置有异议随时点名。
- **无历史角色记录、默认 Rifler 低置信（17 人）**：Keshandr、ColoN、EXR 等
  冷门老将（见 player_overrides.json 中 "low confidence" 条目），仅出现在
  hard 池，维持现状。

## 五、行为变化摘要（代码已改，30 项测试通过）

- 猜测反馈：无队者战队格互相判绿（原来"退役"vs"未签约"判灰）；
  IGL vs Rifler 角色格不再判黄。
- 前端/AI 提示词中的"退役/未签约"文案统一为"自由身"。
- nota（下放）保持 PARIVISION；somebody、fer、degster、2k 等统一自由身。
- 本轮未提交、未推送、未部署。
