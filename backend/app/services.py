"""缫丝盆门槛：标成已缫完须最近一次汤温落在 38～42℃，且该盆有合格渗透单。

两套检查收在同一个 assert_can_set_status 里，由同一个改态路由调用：
- 汤温出带照样拦，不因为已有合格单就放过；
- 无合格渗透单（未作废且真空度不低于 0.08）也拦。
"""

from app.models import Basin, PenetrationSlip

MIN_TEMP = 38.0
MAX_TEMP = 42.0
MIN_VACUUM = 0.08


class RuleError(ValueError):
    pass


def latest_temp(basin: Basin) -> float | None:
    if not basin.readings:
        return None
    latest = max(basin.readings, key=lambda r: r.taken_at)
    return latest.water_temp_c


def qualified_slip(basin: Basin) -> PenetrationSlip | None:
    """该盆当前可作放行依据的渗透单：未作废且真空度达标。"""
    for slip in basin.slips or []:
        if slip.voided_at is None and slip.vacuum_degree >= MIN_VACUUM:
            return slip
    return None


def assert_can_set_status(basin: Basin, new_status: str) -> None:
    allowed = {Basin.STATUS_SOAKING, Basin.STATUS_REELING, Basin.STATUS_REELED}
    if new_status not in allowed:
        raise RuleError(f"无效状态：{new_status}")
    if new_status != Basin.STATUS_REELED:
        return
    temp = latest_temp(basin)
    if temp is None:
        raise RuleError("该盆尚无汤温记录，不能标已缫完")
    if temp < MIN_TEMP or temp > MAX_TEMP:
        raise RuleError(
            f"最近汤温 {temp}℃ 不在 {MIN_TEMP:.0f}～{MAX_TEMP:.0f}℃，不能标已缫完"
        )
    if qualified_slip(basin) is None:
        raise RuleError(
            f"该盆无合格渗透单（须未作废且真空度≥{MIN_VACUUM}），不能标已缫完"
        )
