# SilkReel-01 · 江口缫丝坞

缫丝盆环状作业台。登录后看到的是沿汤池围成一圈的盆位，点盆登记汤温并改状态——不是侧栏双列表 CRUD。

## 技术栈

| 层 | 技术 |
| --- | --- |
| Web API | Quart（异步 Flask 族）· Hypercorn |
| 结构 | `repositories.py` 仓储 + `services.py` 门槛，路由不直接拼 SQL |
| 数据 | SQLAlchemy 2 async · asyncpg · PostgreSQL 15 |
| 前端 | Preact 10 · Vite |
| 部署 | Docker Compose |

## 路径与端口

- 前端：http://localhost:4760
- API：http://localhost:8760
- PostgreSQL：localhost:6160

## 演示账号

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `123456` | 管理员 |
| `worker` | `123456` | 缫丝工 |

## 业务规则

盆状态不可标成「已缫完」，除非**同时**满足（规则在 `backend/app/services.py`，两道门槛收在同一个改态口）：

1. 该盆**最近一条**汤温记录落在 **38～42℃**——出带汤温不因有合格单而放行；
2. 该盆有**合格渗透单**：未作废且**真空度 ≥ 0.08**。

### 渗透合格单

- 每单记录：盆、单号（每盆从 1 起）、真空度、渗透时刻、操作人（取登录人）、作废时刻（可空）。
- 同一盆的未作废单号不得撞车：数据库以「未作废」部分唯一索引兜底，两名质检交叉提交同盆同号只入库一张，后到者收到 409。
- 登录用户（含缫丝工）均可建单；**作废仅管理员**。
- 顶栏「渗透单」为独立专页：按盆筛选、页内建单、管理员作废；环盆作业台抽屉里的「已缫完」走同一个改态口，无单同样被中文挡住。

### 渗透单 API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/slips?basin_id=<id>` | 列单，可按盆筛选 |
| POST | `/api/slips` | 建单：`basinId` / `slipNo` / `vacuumDegree` / `penetratedAt`（可空，默认当前） |
| POST | `/api/slips/<id>/void` | 作废（仅管理员） |

## 快速启动

```bash
cd SilkReel/SilkReel-01
docker compose up --build
```
