from datetime import datetime, timezone

from quart import Quart, g, jsonify, request
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import Basin, PenetrationSlip
from app.repositories import BasinRepo, SlipRepo, UserRepo
from app.security import make_token, parse_token, verify_password
from app.services import MIN_VACUUM, RuleError, assert_can_set_status, latest_temp, qualified_slip

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
    live = [s for s in (basin.slips or []) if s.voided_at is None]
    return {
        "id": basin.id,
        "code": basin.code,
        "status": basin.status,
        "ringIndex": basin.ring_index,
        "latestTempC": latest_temp(basin),
        "readingCount": len(basin.readings or []),
        "liveSlipCount": len(live),
        "hasQualifiedSlip": qualified_slip(basin) is not None,
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


def _slip_json(slip: PenetrationSlip) -> dict:
    return {
        "id": slip.id,
        "basinId": slip.basin_id,
        "basinCode": slip.basin.code if slip.basin else None,
        "slipNo": slip.slip_no,
        "vacuumDegree": slip.vacuum_degree,
        "penetratedAt": slip.penetrated_at.isoformat() if slip.penetrated_at else None,
        "operator": slip.operator,
        "voidedAt": slip.voided_at.isoformat() if slip.voided_at else None,
        "qualified": slip.voided_at is None and slip.vacuum_degree >= MIN_VACUUM,
    }


@app.route("/api/slips", methods=["GET"])
async def list_slips():
    denied = require_user()
    if denied:
        return denied
    basin_id = None
    raw = request.args.get("basin_id", "")
    if raw:
        try:
            basin_id = int(raw)
        except ValueError:
            return jsonify({"detail": "盆编号必须是整数"}), 400
    async with SessionLocal() as session:
        slips = await SlipRepo(session).list(basin_id)
        return {"slips": [_slip_json(s) for s in slips]}


@app.route("/api/slips", methods=["POST"])
async def create_slip():
    denied = require_user()
    if denied:
        return denied
    body = await request.get_json(force=True)
    if not isinstance(body, dict):
        return jsonify({"detail": "请求体必须是 JSON 对象"}), 400

    raw_basin = body.get("basinId")
    try:
        basin_id = int(raw_basin)
    except (TypeError, ValueError):
        return jsonify({"detail": "盆不能为空"}), 400

    raw_no = body.get("slipNo")
    if isinstance(raw_no, bool):
        return jsonify({"detail": "单号必须是不小于 1 的整数"}), 400
    if isinstance(raw_no, float) and not raw_no.is_integer():
        return jsonify({"detail": "单号必须是不小于 1 的整数"}), 400
    try:
        slip_no = int(raw_no)
    except (TypeError, ValueError):
        return jsonify({"detail": "单号必须是不小于 1 的整数"}), 400
    if slip_no < 1:
        return jsonify({"detail": "单号从 1 起，必须是不小于 1 的整数"}), 400

    try:
        vacuum = float(body.get("vacuumDegree"))
    except (TypeError, ValueError):
        return jsonify({"detail": "真空度必须是数字"}), 400
    if not 0.0 <= vacuum <= 1.0:
        return jsonify({"detail": "真空度须在 0～1 之间"}), 400

    penetrated_at = None
    raw_at = body.get("penetratedAt")
    if raw_at:
        try:
            penetrated_at = datetime.fromisoformat(str(raw_at).replace("Z", "+00:00"))
        except ValueError:
            return jsonify({"detail": "渗透时刻格式不对"}), 400
        if penetrated_at.tzinfo is None:
            penetrated_at = penetrated_at.replace(tzinfo=timezone.utc)

    async with SessionLocal() as session:
        basin = await BasinRepo(session).get(basin_id)
        if basin is None:
            return jsonify({"detail": "盆不存在"}), 404
        repo = SlipRepo(session)
        if await repo.live_by_no(basin_id, slip_no) is not None:
            return jsonify({"detail": f"该盆已有未作废的 {slip_no} 号单，单号不得撞车"}), 409
        try:
            slip = await repo.create(basin, slip_no, vacuum, penetrated_at, g.user.username)
        except IntegrityError:
            await session.rollback()
            return jsonify({"detail": f"该盆已有未作废的 {slip_no} 号单，单号不得撞车"}), 409
        return _slip_json(slip), 201


@app.route("/api/slips/<int:slip_id>/void", methods=["POST"])
async def void_slip(slip_id: int):
    denied = require_user()
    if denied:
        return denied
    if g.user.role != "admin":
        return jsonify({"detail": "仅管理员可作废渗透单"}), 403
    async with SessionLocal() as session:
        repo = SlipRepo(session)
        slip = await repo.get(slip_id)
        if slip is None:
            return jsonify({"detail": "渗透单不存在"}), 404
        if slip.voided_at is not None:
            return jsonify({"detail": "该单已作废"}), 400
        await repo.void(slip)
        return _slip_json(slip)
