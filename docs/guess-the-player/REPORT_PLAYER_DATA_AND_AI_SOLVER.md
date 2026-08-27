# CStrikle 选手数据与 AI 求解器改造报告

日期：2026-07-17

生产站点：<https://cs2.estia.moe>

数据榜单快照：[HLTV World Ranking 2026-07-13](https://www.hltv.org/ranking/teams/2026/july/13)

## 1. 执行摘要

本轮改造解决了三类相互关联的问题：

1. `ALEX`、`AdreN` 等常见 ID 同时存在完整人物和全空白 stub，空白记录还能成为谜底。
2. Liquipedia 当前职务直接污染游戏属性，例如教练战队、主播组织和历史比赛位置混在同一字段。
3. AI 依赖 Grok 自行搜索和猜测，缺少本地候选过滤与最优落子算法；CPA 全局搜索、SDK/CPA 重试和上游账号状态共同放大延迟。

最终结果：

- 从运行时剔除 7 条全空 stub，同时保留真实的同名选手。
- 搜索资料库为 649 人，合格答案池为 607 人；任何难度均不会再抽到缺少核心属性的谜底。
- Coach 成为合法游戏位置；教练战队只有进入 HLTV Top 100 快照时才保留，否则显示 Free Agent。
- 建立 CPA 专用模型别名 `grok-4.5-cstrikle`，CStrikle 请求跳过 Grok 原生搜索，其他 canonical Grok 请求仍保留原规则。
- 恢复项目 DDGS，加入缓存与每回合一次的硬限制。
- 实现严格候选过滤、全局信息增益评分和小候选集合的有限步精确求解。
- AI 强度拆分为下饭、普通、作弊三种职责：模型自由猜、模型自主选候选、确定性最优求解。
- 下饭允许模型最多执行两步自由动作且共享 20 秒总预算；普通每轮只调用模型一次。作弊仍由求解器确定落子，但增加一次只负责 `say` 的模型调用，聊天失败不影响提交。

## 2. 空白 ALEX / AdreN 的根因

数据库并不是缺少 Liquipedia 数据，而是同时保存了正确的消歧人物和错误的裸标题记录。

典型情况：

| 裸昵称 | 正确记录 | 错误记录 |
|---|---|---|
| ALEX | `ALEX (British player)`、`Alex (Spanish player)` | `page=ALEX` 的全空 stub |
| AdreN | `AdreN (Kazakh player)`、`AdreN (American player)` | `page=AdreN` 的全空 stub |

抓取器从 BLAST 得到的只是昵称。昵称未命中 Major 数据库时，程序会直接把裸昵称当成 Liquipedia 标题；同名人物需要消歧，但原逻辑只取 opensearch 第一项。即使没有解析出有效人物 infobox，裸标题仍可能被组装成：

```text
country=""
birth_date=""
roles=[]
majors_count=0
in_blast_pool=true
```

随后两个运行时规则放大了问题：

- autocomplete 无条件返回所有数据库记录；
- medium 答案池接纳所有 `in_blast_pool=true` 记录，hard 直接接纳全部记录。

因此空 ALEX 会出现在搜索列表，空 AdreN 也能被 `random.choice()` 抽成无限模式谜底。

审计共发现 7 条同类 stub：

```text
ALEX, Zeus, Lucky, ScreaM, fox, AdreN, Sonic
```

修复后：

- 抓取器先按 Major 页面中的 nickname 判断 BLAST 人物是否已存在，不再把 ALEX/AdreN 裸昵称重复加入；
- 空 infobox 不再因为写入 `_final_title` 而被误判为有效记录；
- 全空 stub 在 PlayerDB 加载阶段被拒绝；
- 合法同名人物继续保留；
- `ALEX` 默认解析到英国 ALEX；
- `AdreN` 默认解析到哈萨克 AdreN；
- 答案池额外要求国籍、生日和可比较位置完整。

## 3. Coach 与 HLTV Top 100 战队规则

项目保存一份离线排名快照：

```text
data/hltv_top100.json
generated_at=2026-07-13
limit=100
```

HLTV 说明其世界排名按周更新，并综合长期成绩、近期状态和 LAN 表现。[排名说明与当前榜单](https://www.hltv.org/ranking/teams/2026/july/13)

采用离线快照而非生产实时抓取的原因：

- HLTV 对 Oracle ARM 直连返回 Cloudflare 403；
- 排名变化不应造成应用启动或每局请求失败；
- 快照可以版本控制、审计和回滚。

当前规则：

1. `coach` 和 `assistant coach` 统一显示为 `Coach`。
2. 当前角色是 Coach 时：
   - 战队命中 Top 100：保留战队；
   - 未命中 Top 100：显示 Free Agent。
3. 队名比较先做规范化和别名映射。

典型结果：

| 人物 | 当前结果 | 原因 |
|---|---|---|
| friberg | Free Agent / Coach | Johnny Speeds 不在当前 Top 100 |
| NEO | Astralis / Coach | Astralis 当前第 18 |
| s1mple | BC.Game Esports / AWPer | BC.Game 当前第 77，位置有人工覆盖 |
| olofmeister | Free Agent / Rifler | FaZe 关系是主播身份，不是选手/教练战队 |
| AdreN（哈萨克） | Free Agent / Rifler | 当前经理职务不能抹掉历史比赛位置 |

队名别名示例：

```text
Team Falcons -> Falcons
Team Vitality -> Vitality
FaZe Clan -> FaZe
BC.Game Esports -> BC.Game
Team Liquid -> Liquid
```

## 4. CPA 专用路由

CLIProxyAPI 官方配置支持 OAuth/file-backed provider 使用 `oauth-model-alias`，并可通过 `fork: true` 同时保留 canonical 和 alias。[官方配置示例](https://github.com/router-for-me/CLIProxyAPI/blob/main/config.example.yaml)

生产配置：

```yaml
oauth-model-alias:
  xai:
    - name: grok-4.5
      alias: grok-4.5-cstrikle
      fork: true
```

CPA 原有规则会给 canonical `grok-4.5` 追加 Grok 原生 `web_search`：

```yaml
payload:
  override-raw:
    - models:
        - name: grok-4.5
      not-match:
        - metadata.client: cstrikle
      params:
        "tools.-1": {"type": "web_search"}
```

需要 `metadata.not-match` 的原因是：alias 在 CPA 内部解析回上游 canonical 名称后，单纯按 alias 名字无法避开原规则。实测曾出现：

```text
Duplicate tool names: web_search
```

这证明 alias 请求仍命中了 canonical payload。最终方案：

- CStrikle 每个请求携带 `metadata.client=cstrikle`；
- CPA 原生搜索规则排除该 metadata；
- 项目本地工具更名为 `ddgs_search`，避免任何工具名碰撞。

验证结果：

- `/v1/models` 同时返回 `grok-4.5` 与 `grok-4.5-cstrikle`；
- alias function-calling 冒烟请求 HTTP 200；
- 搜索隔离修复后的真实 AI 事件只有 `solver/reasoning/say/guess`，无 native search、无协议降级。

## 5. DDGS 本地搜索

DDGS 只作为资料补充工具，不能参与本局真值判定。

约束：

- 第一轮提示模型不要搜索；
- 每回合最多一次；
- 查询结果在同一 AIPlayer 内缓存 3600 秒；
- 网页结果不能改变服务器指定落子。

生产烟测：

| 请求 | 耗时 | 返回长度 |
|---|---:|---:|
| `s1mple BC.Game AWP` 首次 | 2.21 秒 | 1650 字符 |
| 同查询缓存命中 | 0.0003 秒 | 1650 字符 |

与此前 50–80 秒的 Grok 原生搜索相比，本地搜索的延迟和可控性明显更好。

## 6. 确定性求解算法

### 6.1 严格候选过滤

对每个历史猜测 `g` 和实际反馈 `f`，候选答案 `c` 只有在以下条件成立时才保留：

```text
signature(compare(g, c)) == signature(f)
```

反馈签名只包含：

```text
(属性 key, 颜色 state, 方向 dir)
```

不会把猜测行显示值误当成答案条件。若某次猜测没有猜中，该选手身份本身也会从候选中排除。

### 6.2 大候选集合的信息增益

对每个合法未猜选手，按可能反馈把当前候选集合 `C` 分桶。

主要指标是期望后验大小：

```text
E(g) = Σ |B_i|² / |C|
```

数值越小，代表平均一次猜测后剩余候选越少。

排序 tie-break：

1. 最小期望后验；
2. 最小最坏分支；
3. 最大信息熵；
4. 优先候选集合内部猜测；
5. Major 经历和稳定昵称排序。

当前清洗后的 medium 484 人池，首轮最优猜测为：

```text
refrezh
期望后验=5.06
最坏分支=16
信息熵=7.084 bits
```

旧数据库上得到的 SENER1 不再是最优首猜，因为 Coach、位置优先级、战队和答案池清洗改变了属性分布。

### 6.3 小候选集合精确求解

候选数不超过 10 时，算法不再只看一步信息增益，而是递归计算剩余回合内的实际解出概率。

对猜测 `g`：

```text
P(C,t,g) =
  [g 在 C 中的立即命中数
   + Σ |B_i| × V(B_i,t-1)]
  / |C|
```

其中：

- `t` 是剩余猜测次数；
- `B_i` 是猜错后各反馈分支；
- `V` 是对子状态继续选择最优猜测的概率。

算法使用缓存避免重复计算，并把候选本身与少量高信息探针合并为动作集合。

## 7. 专用提示词与模型职责

当前三档职责：

1. 下饭读取自己全部猜测与反馈，但不运行候选过滤、信息增益或精确求解；模型凭自己的 CS 常识和直觉自由选择库内未猜过的选手。第一轮不搜索，之后确有需要时每轮最多使用一次 DDGS，也可简短聊天。
2. 普通首轮在信息增益前五中随机开局；获得反馈后，服务器只提供完整候选名单和公开属性，由模型按自己的 CS 常识与偏好选择，并附一句玩家能看懂的理由。
3. 作弊全程采用确定性求解器；候选多时选最容易继续排除的落子，候选少时使用有限步精确求解。

下饭模式恢复求解器引入前的自由 Agent 语义：模型可以先说话，再在下一步提交 `submit_guess`；最多执行 `AI_MAX_STEPS` 步，全部步骤共享 20 秒等待预算。它只受“选手必须在库内且没有猜过”的校验，不受答案池、求解器候选或最优落子的限制。CStrikle 的 Grok 专用路由不注入原生搜索。

普通模式的自主决策请求同时提供 `say` 与 `submit_guess`，要求在同一响应中完成聊天和候选内选择，最多等待 20 秒；开局或候选唯一时先由服务器确定落子，再让模型只调用一次 `say`。作弊使用相同的只聊天调用，但最终人选始终由求解器决定。模型超时、429、提交库外人选或提交与反馈矛盾的人选时，Room 立即采用已经确定的合法人选。

回放只展示“范围如何缩小、这档难度如何选人、AI 的一句公开理由”，不再向玩家展示期望后验、最坏桶或信息熵等内部指标。

## 8. low 与 medium 同批基准

四个固定场景：

1. opening：无反馈；
2. one_feedback：一次反馈后只剩 s1mple；
3. coach_feedback：Coach 谜底、16 候选；
4. two_feedback：两次反馈后只剩 AdreN。

所有场景使用相同数据库、相同历史行、相同指定落子、相同 35 秒上限和零 SDK 重试。

| Effort | 场景 | 候选 | 结果 | 总耗时 | 搜索 |
|---|---|---:|---|---:|---:|
| low | opening | 484 | timeout | 38.54 秒 | 0 |
| low | one_feedback | 1 | xAI quota 429 | 22.26 秒 | 0 |
| low | coach_feedback | 16 | 成功，Golden | 20.58 秒 | 0 |
| low | two_feedback | 1 | timeout | 35.48 秒 | 0 |
| medium | opening | 484 | 成功，refrezh | 27.85 秒 | 0 |
| medium | one_feedback | 1 | 成功，s1mple | 33.22 秒 | 0 |
| medium | coach_feedback | 16 | timeout | 35.57 秒 | 0 |
| medium | two_feedback | 1 | 成功，AdreN | 34.93 秒 | 0 |

汇总：

| 指标 | low | medium |
|---|---:|---:|
| 成功率 | 1/4 | 3/4 |
| timeout | 2 | 1 |
| quota 429 | 1 | 0 |
| 成功样本平均耗时 | 20.58 秒 | 32.00 秒 |
| 成功时遵循求解器 | 100% | 100% |

结论：

- 算法质量已经由服务器保证，reasoning effort 不再决定猜谁。
- low 的唯一成功样本更快，但本批可用性很差。
- medium 在本批 3/4 成功，因此生产采用 medium。
- 样本只有四局，不能把差异全部归因于 effort；账号轮换、上游负载和免费额度同样影响结果。
- xAI 曾明确返回 `free-usage-exhausted`，账号池健康仍是外部风险。

## 9. 生产配置

```text
AI_MODEL=grok-4.5-cstrikle
AI_SEARCH_ENABLED=1
AI_MAX_STEPS=2
AI_TIMEOUT_SECONDS=35
AI_EXACT_THRESHOLD=10
AI_SEARCH_CACHE_TTL_SECONDS=3600
AI_REASONING_EFFORT=medium
```

保护措施：

- OpenAI SDK `max_retries=0`；
- CPA 仍有全局 retry，但应用请求最多等待 35 秒；
- 模型失败后立即 solver fallback；
- 不再随机猜；
- DDGS 最多每回合一次并缓存；
- 游戏答案池只含核心属性完整人物。

## 10. 验证结果

- Python `compileall`：通过。
- unittest：14/14 通过。
- `git diff --check`：通过。
- CPA alias `/v1/models`：通过。
- alias function calling：通过。
- DDGS 首次/缓存：通过。
- Docker build：通过。
- CStrikle container health：healthy。
- 公网 `/api/meta`：通过。
- ALEX/AdreN 同名映射：通过。
- friberg/NEO/s1mple/olofmeister 规则：通过。

当前公网数据摘要：

```text
player_count=649
answer_player_count=607
excluded_stubs=7
easy=341
medium=484
hard=607
team_ranking_date=2026-07-13
ai_model=grok-4.5-cstrikle
```

## 11. 维护建议

### 每周

- 更新 `data/hltv_top100.json`；
- 保留 `generated_at` 和 `source_url`；
- 检查队名别名；
- 运行完整测试后再部署。

### 每次重建玩家库

- 禁止组装没有有效 infobox 的 BLAST 裸昵称；
- 输出 stub、重复昵称和不合格答案统计；
- 人工检查 `data/player_overrides.json` 是否仍需要；
- 确保任何难度答案池都满足 `is_game_ready`。

### AI 运维

- 观察 CPA 的 429、120 秒 upstream 失败和账号额度；
- 不因单次基准结果频繁切换 effort；
- 若 Grok 继续高频超时，可只替换 CStrikle alias 的上游模型，求解算法和提示词无需改变；
- medium/low 的后续对比应至少扩展到 30–50 个同批状态，并分别统计成功率、首调用工具遵循率和 p50/p95 延迟。

### chatgpt2api 文本协议门槛测试

2026-07-19 使用春川现有 14 个免费 ChatGPT 网页账号，以真实 medium 题库反馈生成
21–28 人候选局面，单请求上限 8 秒：

- `gpt-5-mini`：1/1 超时；
- `gpt-5-5-mini`：6 局中 4 局返回合法候选 JSON，2 局超时；成功耗时约 5.82–8.04 秒；
- `gpt-5-3-mini`：3 局中 2 局返回合法候选 JSON，1 局超时；
- 将输入压缩为 8 人短名单后，`gpt-5-3-mini` 3/3 超时。

结论：正文 JSON 可以替代 function calling，协议本身没有问题；但该逆向号池的
8 秒内稳定率不足，压缩提示词也没有改善首包延迟，因此停止 100 局扩展，不接入
公开游戏主路由。标准对战统一延长到 120 秒，但普通 AI 仍保留单手 8 秒超时和合法
候选兜底，避免整局被上游请求阻塞。
