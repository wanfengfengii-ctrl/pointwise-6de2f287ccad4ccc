# 双语字幕放映服务

地方剧场的周末晚场用两块屏幕显示中英字幕。译审员从中英对照稿保存具名提示并批准固定快照。排场员选用一个批准版，配置开场秒和两路屏幕，读彩排清单定位占用冲突，再预送正式清单。放映员用本地时钟推进，在值班过程中查缺路。编辑员可为一条已预送提示提交一对替换正文。场后按实际输出核对观众读到的原文。

## 运行

使用 Python 3.11 标准库。运行平台提供的完整原回归入口。

```text
python3 -B check_project.py
python3 -B demo.py
```

演示使用临时目录中的两个独立 SQLite 文件以及实际本地 HTTP 请求，结束时清理临时目录。它从有限样例批准稿件、计算彩排、预送、确认勘误并按本地整数时钟放映。输出包括正式清单、勘误回执和实播清单。

若要启动两端供本地 HTTP 客户端使用，先在项目目录装载样例。重复装载保留同稿号下的用户草稿及所有已存在的快照、场次、实播和回执。

```text
python3 -B -m editorial.http init --db desk.sqlite --sample
python3 -B -m projection.http init --db screen.sqlite
```

在两个终端分别启动服务。请求只在 loopback 上监听。

```text
python3 -B -m projection.http serve --db screen.sqlite --port 8765
python3 -B -m editorial.http serve --db desk.sqlite --port 8764 --projection http://127.0.0.1:8765
```

放映服务默认读取本地 Unix 整数秒。示例和回归通过 `LocalClock` 注入整数时钟。手工安排时，将 `start` 设为所需开场时点。各端启动时自动建表，可连接已有数据库。放映端一次推进按到点顺序处理该场次所有已到点且未输出的工作。实播秒记录该次实际推进时读到的本地秒，晚推进时可晚于原排定时点。

## 编审 HTTP 接口

POST 使用 JSON 对象。字符串标识和正文须非空，保留输入原值。HTTP 错误一般返回含 `error` 的 JSON 对象。

| 方法和路径 | 参数 | 结果 |
| --- | --- | --- |
| `POST /draft` | `script_id` 和 `cues`，每条含 `cue_id`、`second`、`zh`、`en` | 保存草稿，返回 `script_id`。缺译或提示重名时拒绝并保留旧稿。 |
| `GET /draft` | `script_id` | 当前草稿。 |
| `POST /approve` | `script_id` | 返回固定 `revision`。无稿或空稿拒绝。 |
| `GET /revision` | `revision` | 原批准版提示、相对秒和正文。 |
| `POST /rehearse` | `show_id`、`revision`、`start`、`lanes` | 成功返回 `show_id`、`revision` 和有序 `outputs`。未批准、空清单、合成负时点或同屏冲突拒绝。 |
| `GET /rehearse` | `show_id` | 最后一次有效正式清单。 |
| `POST /preload` | `show_id` | 200 `received` 或 202 `pending`，含 `manifest_id`。无有效清单返回 404。 |
| `POST /correct` | `show_id`、`cue_id`、`correction_id`、`zh`、`en` | 返回该号与场次提示、状态和版本。 |
| `GET /verdict` | `correction_id` | 查回原裁决或待核。未知号返回 404。 |
| `GET /readback` | `show_id`，可选 `cue_id` | 向放映端查询实际输出。 |

`lanes` 必须有 `zh`、`en` 两个键，各含整数 `offset`、非空 `screen` 和正整数 `duration`。开场秒加提示相对秒再加偏移得到该路时点。开场 100、提示相对秒 10、偏移 0 和 2，得到 110 和 112。每条输出包含提示、语言、时点、屏幕、占用时长及批准正文。同屏占用为 `[at, at + duration)`。相接允许，相交返回 409 及涉事屏和窗口。正式清单按时点、提示号及同提示固定中文优先顺序排列。预送开始后，场次绑定固定。同内容可重复彩排或预送，以新场次标识安排不同清单。

勘误针对已发起预送的场次提示。200 `accepted` 表示放映端已提交成组替换。409 `already_shown` 表示本次请求到达时已有首路正式输出。202 `pending` 表示编审尚不能确认，`version` 此时为空值。原号同参 POST 可续送或复领，GET 查询已落定的原裁决。同号异参返回 409 `correction_parameter_mismatch`，未知场次提示返回 404。已获准又被另一笔首显前的更正替换时，历史回执仍记录各自实际获准的版本。勘误版本以场次和提示为作用域。同秒内以放映端提交顺序裁定。

## 放映 HTTP 接口

| 方法和路径 | 参数 | 结果 |
| --- | --- | --- |
| `POST /advance` | `show_id` | 本次正式提交的 `records`。未知场次为 404，暂无到点工作则为空数组。 |
| `GET /readback` | `show_id`，可选 `cue_id` | 按正式输出顺序返回原版本、原文及实播秒，并列出各提示仍欠语言。未知场次或提示为 404。 |

预送的正式清单、成对正文和待播工作在放映端持久化。编审断线时已实收场次照常播出。模拟屏上显示以放映端提交的正式输出为准。读回包含顶层 `records`、`cues` 和 `complete`，提示条目也有 `records`、`missing` 和 `complete`。缺路以正式清单中应播的语言减去正式实播计算，两路均未显示的提示也列出。编审可以独立查询实播回报，回报到达时间不参与勘误裁决。

双端交接使用放映端的 `/inbox` 和 `/decision`。`/inbox` 用清单身份交接和复查实收，`/decision` 用原勘误号及原参数交接和查询裁决。放映端在其 SQLite 事务提交后答复。编审端先登记原请求，收到对应终局才确认，重开可从原号查询。
