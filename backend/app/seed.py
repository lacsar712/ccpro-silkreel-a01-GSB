from datetime import timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Basin, BathReading, Filature, PenetrationTicket, User, utcnow
from app.security import hash_password


async def seed_demo() -> None:
    async with SessionLocal() as session:
        existing = await session.execute(select(User).where(User.username == "admin"))
        admin = existing.scalar_one_or_none()
        if admin is None:
            admin = User(username="admin", password_hash=hash_password("123456"), role="admin")
            session.add(admin)
        else:
            admin.password_hash = hash_password("123456")
            admin.role = "admin"

        existing_w = await session.execute(select(User).where(User.username == "worker"))
        worker = existing_w.scalar_one_or_none()
        if worker is None:
            session.add(User(username="worker", password_hash=hash_password("123456"), role="worker"))
        else:
            worker.password_hash = hash_password("123456")
            worker.role = "worker"

        mill = (await session.execute(select(Filature))).scalars().first()
        if mill:
            await session.commit()
            return

        mill = Filature(name="江口缫丝坞", riverside="东津渡")
        session.add(mill)
        await session.flush()
        now = utcnow()
        # (code, status, temp, ring_index, vacuum) — vacuum 非 None 时补一张渗透单
        specs = [
            ("甲-1", Basin.STATUS_REELING, 40.5, 0, None),
            ("甲-2", Basin.STATUS_SOAKING, None, 1, None),
            ("乙-1", Basin.STATUS_REELED, 39.2, 2, 0.09),
            ("乙-2", Basin.STATUS_REELING, 36.0, 3, 0.10),
            ("丙-1", Basin.STATUS_SOAKING, None, 4, None),
            ("丙-2", Basin.STATUS_REELED, 41.0, 5, 0.06),
        ]
        for idx, (code, status, temp, ring, vacuum) in enumerate(specs):
            basin = Basin(filature_id=mill.id, code=code, status=status, ring_index=ring)
            session.add(basin)
            await session.flush()
            if temp is not None:
                session.add(
                    BathReading(
                        basin_id=basin.id,
                        water_temp_c=temp,
                        operator="worker",
                        taken_at=now - timedelta(hours=2),
                    )
                )
            if vacuum is not None:
                session.add(
                    PenetrationTicket(
                        basin_id=basin.id,
                        slip_no=1,
                        vacuum=vacuum,
                        operator="worker",
                        penetrated_at=now - timedelta(hours=1),
                    )
                )
        await session.commit()
