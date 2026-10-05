from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Basin, BathReading, Filature, PenetrationSlip, User, utcnow


class UserRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()


class BasinRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def board(self) -> Filature | None:
        result = await self.session.execute(
            select(Filature).options(
                selectinload(Filature.basins).selectinload(Basin.readings),
                selectinload(Filature.basins).selectinload(Basin.slips),
            )
        )
        return result.scalars().first()

    async def get(self, basin_id: int) -> Basin | None:
        result = await self.session.execute(
            select(Basin)
            .options(selectinload(Basin.readings), selectinload(Basin.slips))
            .where(Basin.id == basin_id)
        )
        return result.scalar_one_or_none()

    async def add_reading(self, basin: Basin, temp_c: float, operator: str) -> BathReading:
        row = BathReading(basin=basin, water_temp_c=temp_c, operator=operator)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def save_status(self, basin: Basin, status: str) -> None:
        basin.status = status
        await self.session.commit()


class SlipRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, basin_id: int | None = None) -> list[PenetrationSlip]:
        stmt = (
            select(PenetrationSlip)
            .options(selectinload(PenetrationSlip.basin))
            .order_by(PenetrationSlip.basin_id, PenetrationSlip.slip_no, PenetrationSlip.id)
        )
        if basin_id is not None:
            stmt = stmt.where(PenetrationSlip.basin_id == basin_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, slip_id: int) -> PenetrationSlip | None:
        result = await self.session.execute(
            select(PenetrationSlip)
            .options(selectinload(PenetrationSlip.basin))
            .where(PenetrationSlip.id == slip_id)
        )
        return result.scalar_one_or_none()

    async def live_by_no(self, basin_id: int, slip_no: int) -> PenetrationSlip | None:
        result = await self.session.execute(
            select(PenetrationSlip).where(
                PenetrationSlip.basin_id == basin_id,
                PenetrationSlip.slip_no == slip_no,
                PenetrationSlip.voided_at.is_(None),
            )
        )
        return result.scalars().first()

    async def create(
        self,
        basin: Basin,
        slip_no: int,
        vacuum_degree: float,
        penetrated_at,
        operator: str,
    ) -> PenetrationSlip:
        slip = PenetrationSlip(
            basin=basin,
            slip_no=slip_no,
            vacuum_degree=vacuum_degree,
            operator=operator,
        )
        if penetrated_at is not None:
            slip.penetrated_at = penetrated_at
        self.session.add(slip)
        await self.session.commit()
        await self.session.refresh(slip)
        return slip

    async def void(self, slip: PenetrationSlip) -> None:
        slip.voided_at = utcnow()
        await self.session.commit()
