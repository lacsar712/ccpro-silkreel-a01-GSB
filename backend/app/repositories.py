from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Basin, BathReading, Filature, PenetrationTicket, User, utcnow


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
                selectinload(Filature.basins).selectinload(Basin.tickets),
            )
        )
        return result.scalars().first()

    async def get(self, basin_id: int) -> Basin | None:
        result = await self.session.execute(
            select(Basin)
            .options(selectinload(Basin.readings), selectinload(Basin.tickets))
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


class TicketRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, basin_id: int | None = None) -> list[PenetrationTicket]:
        stmt = select(PenetrationTicket).options(selectinload(PenetrationTicket.basin))
        if basin_id is not None:
            stmt = stmt.where(PenetrationTicket.basin_id == basin_id)
        stmt = stmt.order_by(
            PenetrationTicket.basin_id, PenetrationTicket.slip_no
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, ticket_id: int) -> PenetrationTicket | None:
        result = await self.session.execute(
            select(PenetrationTicket)
            .options(selectinload(PenetrationTicket.basin))
            .where(PenetrationTicket.id == ticket_id)
        )
        return result.scalar_one_or_none()

    async def suggested_slip_no(self, basin_id: int) -> int:
        """盆内单号从 1 起；建议值在历史最大号上递增，作废号也不回收。"""
        result = await self.session.execute(
            select(PenetrationTicket.slip_no)
            .where(PenetrationTicket.basin_id == basin_id)
            .order_by(PenetrationTicket.slip_no.desc())
            .limit(1)
        )
        top = result.scalar_one_or_none()
        return (top or 0) + 1

    async def create(
        self,
        basin: Basin,
        slip_no: int,
        vacuum: float,
        operator: str,
        penetrated_at: datetime | None = None,
    ) -> PenetrationTicket:
        row = PenetrationTicket(
            basin=basin,
            slip_no=slip_no,
            vacuum=vacuum,
            operator=operator,
            penetrated_at=penetrated_at or utcnow(),
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        await self.session.refresh(row.basin)
        return row

    async def void(self, ticket: PenetrationTicket, voided_at: datetime) -> None:
        ticket.voided_at = voided_at
        await self.session.commit()
