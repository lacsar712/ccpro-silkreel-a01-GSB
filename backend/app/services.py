"""缫丝盆改态门槛（唯一改态口）。

标成已缫完须同时满足：
1. 最近一次汤温落在 38～42℃（旧的汤温带，继续拦）；
2. 该盆持有一张未作废、真空度不低于 0.08 的渗透合格单。

两套检查都收在 assert_can_set_status 里，别处不得另开放行绿灯。
"""

from app.models import Basin, PenetrationTicket

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


def qualifying_ticket(basin: Basin) -> PenetrationTicket | None:
    """返回可充当放行依据的渗透单：未作废且真空度达标，否则 None。"""
    for ticket in basin.tickets or []:
        if ticket.voided_at is not None:
            continue
        if ticket.vacuum is None or ticket.vacuum < MIN_VACUUM:
            continue
        return ticket
    return None


def assert_can_create_ticket(slip_no: int, vacuum: float) -> None:
    if not isinstance(slip_no, int) or slip_no < 1:
        raise RuleError("单号必须是不小于 1 的整数")
    if vacuum != vacuum or vacuum < 0:  # NaN 或负值不接受
        raise RuleError("真空度必须是非负数字")


def assert_can_set_status(basin: Basin, new_status: str) -> None:
    allowed = {Basin.STATUS_SOAKING, Basin.STATUS_REELING, Basin.STATUS_REELED}
    if new_status not in allowed:
        raise RuleError(f"无效状态：{new_status}")
    if new_status != Basin.STATUS_REELED:
        return

    failures: list[str] = []

    temp = latest_temp(basin)
    if temp is None:
        failures.append("该盆尚无汤温记录")
    elif temp < MIN_TEMP or temp > MAX_TEMP:
        failures.append(
            f"最近汤温 {temp}℃ 不在 {MIN_TEMP:.0f}～{MAX_TEMP:.0f}℃"
        )

    ticket = qualifying_ticket(basin)
    if ticket is None:
        failures.append(
            f"该盆没有未作废、真空度不低于 {MIN_VACUUM:g} 的渗透合格单"
        )

    if failures:
        raise RuleError("不能标已缫完：" + "；".join(failures))
