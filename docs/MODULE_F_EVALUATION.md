# 模块 F：循环发送（计划 + 定时任务）— 评估与调整建议

基于当前代码（send 流程、EmailRecord 队列、BackgroundTasks）对计划逐项评估，并给出需调整处。

---

## 一、与现有架构的对应关系

| 计划中的概念 | 当前实现 | 说明 |
|-------------|----------|------|
| 「写入 send_queue」 | **无 send_queue 表**，队列即 `email_records` 表中 `status='queued'` 的记录 | 需在计划中统一表述为「创建 EmailRecord(status=queued)」 |
| send_worker 限频发送 | `_run_batch_send(sales_id, template_id)` + 全局限速 1 封/分钟 | 定时任务只需「建队 + 调用现有发送逻辑」即可复用限频 |

结论：**不新增 send_queue 表**，沿用 `email_records` 作为队列；「send_worker」即现有的 `_run_batch_send` 或对其的封装。

---

## 二、各步骤评估与调整建议

### F.1 发送计划表迁移

**计划字段**：`id, sales_id, day_of_week (0–6), time (TIME), repeat_count, current_count, status, created_at`

**建议调整**：

1. **时区**：`time` 建议明确为「北京时间」存储（或增加 `timezone` 字段）。当前项目 `sent_at` 等已按北京时间展示，调度也应统一为北京时区，APScheduler 使用 `Asia/Shanghai` 即可。
2. **template_id**：F.2 的 body 含可选 `template_id`，表结构应增加 `template_id`（FK → email_templates，可空）。
3. **image_ids**：当前批量发送未使用图片（仅正文），若计划保留「可选 image_ids」为后续扩展，可用 JSON 列（如 `image_ids JSON` 或 `TEXT` 存 JSON）存储；若近期不做图片发送，可暂不建列，接口先忽略该参数。

**建议表结构**（Alembic）：

```text
send_schedules:
  id, sales_id (FK users), day_of_week (0-6), time (TIME),
  repeat_count, current_count (default 0), status (active/completed/cancelled),
  template_id (FK email_templates, nullable),
  image_ids (JSON/TEXT nullable, 可选),
  created_at
```

---

### F.2 创建计划 API

**计划**：`POST /api/send/schedule`，body `{ "day_of_week", "time", "repeat_count" }`，可选 `template_id`、`image_ids`。

**建议**：

- **time 格式**：建议约定为 `"HH:MM"` 或 `"HH:MM:SS"`（北京时间），便于前端与 cron 一致。
- **校验**：`day_of_week` 0–6；`repeat_count >= 1`；若传 `template_id` 则校验存在且可访问。
- **image_ids**：若表有该列则校验为 id 数组并落库；否则接口暂不接收或忽略。

与现有代码无冲突，按上表结构实现即可。

---

### F.3 计划列表与取消

**计划**：`GET /api/send/schedules`（当前销售）、`DELETE` 或 `PATCH` 取消。

**建议**：

- **GET**：仅返回当前用户的计划；支持按 `status` 筛选（如只看 active）更佳。
- **取消**：统一用 **PATCH** `status=cancelled` 更稳妥，保留记录便于审计；若用 DELETE，与「计划历史」需求是否一致需产品确认。当前邮件记录有「取消发送」且为物理删除，计划取消建议以「软取消」为主。

与现有权限模型（销售只看自己）一致。

---

### F.4 APScheduler 集成（需与当前实现对齐）

**计划**：「每分钟或每 5 分钟检查一次，匹配 day_of_week 与 time，且 current_count < repeat_count，则执行『该 sales 的客户列表 → 写入 send_queue』，current_count+1；达 repeat_count 则 status=completed。」

**关键调整**：

1. **“写入 send_queue” 改为“建队 + 触发发送”**  
   - 与现有实现一致的做法是：  
     - 为该 sales 的客户**创建** `EmailRecord(sales_id, to_email, ..., status='queued')`（与当前 `POST /api/send/batch` 的建队逻辑一致）；  
     - 然后**调用现有发送逻辑**：`_run_batch_send(sales_id, template_id)`。  
   - 不新增 send_queue 表，不新增队列消费 worker，仅复用 `_run_batch_send` 的限频与发送。

2. **调度触发方式**  
   - 当前「即刻群发」使用 FastAPI `BackgroundTasks.add_task(_run_batch_send, ...)`，在同一进程内异步执行。  
   - 定时任务在 APScheduler 里运行（通常在同一进程的线程中），**不能**拿到请求的 `BackgroundTasks`，因此应：  
     - 在调度 job 内直接调用 `_run_batch_send(sales_id, template_id)`（或抽一层「创建 queued 记录 + 调用 _run_batch_send」的共用函数），保证与手动群发同路径、同限频。  
   - 若未来改为独立 worker 进程，再考虑「只写队列 + 独立 worker 读队列」不迟。

3. **执行频率**  
   - 「每分钟检查一次」即可；若希望更细粒度，可每分钟检查，用 `time` 的**小时+分钟**与当前北京时间的时分匹配（秒可忽略或固定为 0）。  
   - 不需要「每 5 分钟」两种策略，统一每分钟更简单，且与 1 封/分钟的限速自然配合。

4. **并发与幂等**  
   - 同一 schedule 在同一分钟可能被多次匹配（例如多实例或 job 重跑），建议：  
     - 在「执行前」用 DB 事务：`SELECT ... FOR UPDATE`（或等效）该 schedule，校验 `current_count < repeat_count` 且 `status='active'`，再执行建队 + `current_count += 1`（或 +1 后置为 completed），然后 commit。  
   - 这样避免同一计划在同一周期内被执行多次。

5. **template_id 来源**  
   - 从 `send_schedules.template_id` 读取，传入 `_run_batch_send(sales_id, template_id)`，与当前 batch 行为一致。

**建议伪代码**（在 APScheduler 的 job 内）：

```text
每分钟（北京时间）:
  1. 取当前北京时间 now，today_weekday = now.weekday()，hm = (now.hour, now.minute)
  2. 查询 send_schedules：status='active' AND day_of_week = today_weekday AND time 的 时:分 = hm AND current_count < repeat_count
  3. 对每条 schedule（加锁/事务）：
     a. 再次校验 current_count < repeat_count 且 status='active'
     b. 为该 sales 的客户创建 EmailRecord(..., status='queued')（与 batch 一致）
     c. current_count += 1；若 current_count >= repeat_count 则 status='completed'
     d. commit
     e. 调用 _run_batch_send(schedule.sales_id, schedule.template_id)
```

这样与现有「队列 = EmailRecord」「限频 = _run_batch_send」完全一致。

---

### F.5 持久化与重启

**计划**：调度状态以 DB 为准（send_schedules）；应用重启后 APScheduler 重新加载，不依赖内存 job，避免计划丢失。

**建议**：

- **不**用 APScheduler 的“持久化 job 存储”（如数据库 jobstore）存 cron 表达式；**只**用 DB 的 `send_schedules` 表作为“哪些计划存在、何时执行”的唯一数据源。
- 实现方式：应用启动时只注册**一个**固定 job，例如「每分钟跑一次」的 `check_and_run_schedules()`，该函数内按当前北京时间查询 `send_schedules` 并执行上述 F.4 逻辑。这样：
  - 计划的新增/修改/取消都只改 `send_schedules` 表；
  - 重启后无需“重新加载 job”，因为只有一个常驻的检查 job，所有计划来自 DB。
- 与 F.5 目标一致，且实现更简单、不易出现“内存 job 与 DB 不一致”的问题。

---

## 三、小结：建议在计划中直接改动的点

| 项目 | 建议 |
|------|------|
| 队列 | 不引入 send_queue，统一为「创建 EmailRecord(queued) + 调用 _run_batch_send」 |
| F.1 表结构 | 增加 `template_id`（可空）；`time` 约定为北京时间；可选 `image_ids`（JSON） |
| F.2 API | time 格式约定为 "HH:MM"（北京时间）；校验 template_id 存在 |
| F.3 取消 | 优先 PATCH status=cancelled，保留记录 |
| F.4 执行逻辑 | 明确为「建队（EmailRecord queued）+ 调用 _run_batch_send」；调度 job 内直接调用发送逻辑；每分钟检查；事务内更新 current_count 防重跑 |
| F.5 持久化 | 以 send_schedules 为唯一数据源；单一定时 job「每分钟检查 DB」即可，重启无需恢复 job 列表 |

按上述调整后，模块 F 与当前「邮件记录、批量发送、限频、取消发送」的实现可以完全对齐，且扩展（如后续 image 发送）只需在表与 API 预留字段即可。
