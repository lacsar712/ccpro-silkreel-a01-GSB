from datetime import datetime

from quart import Quart, g, jsonify, request
from quart.helpers import make_response
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import Basin, PenetrationTicket, utcnow
from app.repositories import BasinRepo, TicketRepo, UserRepo
from app.security import make_token, parse_token, verify_password
from app.services import (
    RuleError,
    assert_can_create_ticket,
    assert_can_set_status,
    latest_temp,
    qualifying_ticket,
)

app = Quart(__name__)


def _bearer() -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return None


@app.before_request
async def load_user():
    g.user = None
    token = _bearer()
    if not token:
        return
    username = parse_token(token)
    if not username:
        return
    async with SessionLocal() as session:
        g.user = await UserRepo(session).by_username(username)


def require_user():
    if g.user is None:
        return jsonify({"detail": "未登录"}), 401
    return None


def require_role(role: str):
    denied = require_user()
    if denied:
        return denied
    if g.user.role != role:
        return jsonify({"detail": "无权操作"}), 403
    return None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _ticket_json(ticket: PenetrationTicket) -> dict:
    return {
        "id": ticket.id,
        "basinId": ticket.basin_id,
        "basinCode": ticket.basin.code if ticket.basin else None,
        "slipNo": ticket.slip_no,
        "vacuum": ticket.vacuum,
        "penetratedAt": _iso(ticket.penetrated_at),
        "operator": ticket.operator,
        "voidedAt": _iso(ticket.voided_at),
        "valid": ticket.voided_at is None and ticket.vacuum >= 0.08,
    }


@app.route("/api/health")
async def health():
    return {"status": "ok", "service": "SilkReel"}


@app.route("/api/auth/login", methods=["POST"])
async def login():
    body = await request.get_json(force=True)
    username = (body or {}).get("username", "")
    password = (body or {}).get("password", "")
    async with SessionLocal() as session:
        user = await UserRepo(session).by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            return jsonify({"detail": "用户名或密码错误"}), 401
        return {
            "access_token": make_token(user.username),
            "user": {"username": user.username, "role": user.role},
        }


@app.route("/api/auth/me")
async def me():
    denied = require_user()
    if denied:
        return denied
    return {"username": g.user.username, "role": g.user.role}


def _basin_json(basin: Basin) -> dict:
    ticket = qualifying_ticket(basin)
    return {
        "id": basin.id,
        "code": basin.code,
        "status": basin.status,
        "ringIndex": basin.ring_index,
        "latestTempC": latest_temp(basin),
        "readingCount": len(basin.readings or []),
        "hasQualifyingTicket": ticket is not None,
        "ticketSlipNo": ticket.slip_no if ticket else None,
    }


@app.route("/api/board")
async def board():
    denied = require_user()
    if denied:
        return denied
    async with SessionLocal() as session:
        mill = await BasinRepo(session).board()
        if mill is None:
            return jsonify({"detail": "尚无缫丝坞"}), 404
        basins = sorted(mill.basins, key=lambda b: b.ring_index)
        return {
            "filature": mill.name,
            "riverside": mill.riverside,
            "basins": [_basin_json(b) for b in basins],
        }


@app.route("/api/basins/<int:basin_id>/readings", methods=["POST"])
async def add_reading(basin_id: int):
    denied = require_user()
    if denied:
        return denied
    body = await request.get_json(force=True)
    try:
        temp = float((body or {}).get("waterTempC"))
    except (TypeError, ValueError):
        return jsonify({"detail": "汤温必须是数字"}), 400
    async with SessionLocal() as session:
        repo = BasinRepo(session)
        basin = await repo.get(basin_id)
        if basin is None:
            return jsonify({"detail": "盆不存在"}), 404
        await repo.add_reading(basin, temp, g.user.username)
        basin = await repo.get(basin_id)
        return _basin_json(basin)


@app.route("/api/basins/<int:basin_id>/status", methods=["POST"])
async def set_status(basin_id: int):
    denied = require_user()
    if denied:
        return denied
    body = await request.get_json(force=True)
    status = (body or {}).get("status", "")
    async with SessionLocal() as session:
        repo = BasinRepo(session)
        basin = await repo.get(basin_id)
        if basin is None:
            return jsonify({"detail": "盆不存在"}), 404
        try:
            assert_can_set_status(basin, status)
        except RuleError as exc:
            return jsonify({"detail": str(exc)}), 400
        await repo.save_status(basin, status)
        basin = await repo.get(basin_id)
        return _basin_json(basin)


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise RuleError("渗透时刻格式无效")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return dt


@app.route("/api/tickets")
async def list_tickets():
    denied = require_user()
    if denied:
        return denied
    basin_id: int | None = None
    raw = request.args.get("basin_id")
    if raw:
        try:
            basin_id = int(raw)
        except ValueError:
            return jsonify({"detail": "盆编号无效"}), 400
    async with SessionLocal() as session:
        tickets = await TicketRepo(session).list(basin_id)
        return {"tickets": [_ticket_json(t) for t in tickets]}


@app.route("/api/tickets", methods=["POST"])
async def create_ticket():
    # 缫丝工可建单；任何已登录用户（含管理员）均可。
    denied = require_user()
    if denied:
        return denied
    body = await request.get_json(force=True) or {}
    try:
        basin_id = int(body.get("basinId"))
    except (TypeError, ValueError):
        return jsonify({"detail": "必须指定盆"}), 400
    raw_slip = body.get("slipNo")
    if isinstance(raw_slip, bool) or not isinstance(raw_slip, int):
        return jsonify({"detail": "单号必须是整数"}), 400
    slip_no = raw_slip
    try:
        vacuum = float(body.get("vacuum"))
    except (TypeError, ValueError):
        return jsonify({"detail": "真空度必须是数字"}), 400
    try:
        penetrated_at = _parse_dt(body.get("penetratedAt"))
    except RuleError as exc:
        return jsonify({"detail": str(exc)}), 400

    async with SessionLocal() as session:
        basin_repo = BasinRepo(session)
        basin = await basin_repo.get(basin_id)
        if basin is None:
            return jsonify({"detail": "盆不存在"}), 404
        try:
            assert_can_create_ticket(slip_no, vacuum)
        except RuleError as exc:
            return jsonify({"detail": str(exc)}), 400
        try:
            ticket = await TicketRepo(session).create(
                basin, slip_no, vacuum, g.user.username, penetrated_at
            )
        except IntegrityError:
            # 两名质检并发提交同盆同号：库里只许一张未作废单。
            await session.rollback()
            return jsonify({"detail": "同盆该单号已有未作废单，不得重复"}), 409
        return _ticket_json(ticket), 201


@app.route("/api/tickets/<int:ticket_id>/void", methods=["POST"])
async def void_ticket(ticket_id: int):
    # 作废只给管理员。
    denied = require_role("admin")
    if denied:
        return denied
    async with SessionLocal() as session:
        repo = TicketRepo(session)
        ticket = await repo.get(ticket_id)
        if ticket is None:
            return jsonify({"detail": "渗透单不存在"}), 404
        if ticket.voided_at is not None:
            return jsonify({"detail": "该单已作废"}), 400
        await repo.void(ticket, utcnow())
        ticket = await repo.get(ticket_id)
        return _ticket_json(ticket)
