"""Tour packages API routes."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.middleware.role_guard import role_required
from app.models.user import User, UserRole
from app.schemas.tour import TourCreate, TourResponse, TourUpdate
from app.services.tour_service import TourService
from app.utils.images import save_image
from app.utils.pagination import PaginatedResponse

router = APIRouter(prefix="/api/tours", tags=["Tours"])
settings = get_settings()


@router.get("", response_model=PaginatedResponse[TourResponse], summary="Tur ro'yxati")
async def list_tours(
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=100),
    city: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    start_date: Optional[date] = None,
    min_slots: Optional[int] = None,
    search: Optional[str] = None,
    company_id: Optional[int] = None,
    sort: Optional[str] = Query(
        None,
        description="narx_arzon | narx_qimmat | sana | yangi (sukut)",
    ),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[TourResponse]:
    """Public tour catalog with filters."""
    service = TourService(db)
    return await service.list_tours(
        page=page,
        page_size=page_size,
        city=city,
        min_price=min_price,
        max_price=max_price,
        start_date=start_date,
        min_slots=min_slots,
        search=search,
        company_id=company_id,
        sort=sort,
    )


@router.get("/cities", summary="Yo'nalishlar ro'yxati")
async def list_cities(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Turlari BOR shaharlar, har birida nechta tur borligi bilan.

    Ro'yxat statik taksonomiyadan emas, haqiqiy turlardan olinadi. Sababi
    amaliy: taksonomiyada 42 ta kurort bor, lekin ularning ko'pida bugun
    birorta ham tur yo'q. Bunday joyni taklif qilish foydalanuvchini bo'sh
    natijaga olib borardi — qidiruvdagi eng asabiylashtiradigan holat.

    Bu endpoint `/{tour_id}` dan OLDIN turishi SHART: aks holda "cities"
    tur raqami deb o'qilib 422 qaytarardi.
    """
    from sqlalchemy import func, select

    from app.models.tour import Tour

    rows = (
        await db.execute(
            select(Tour.city, func.count(Tour.id).label("soni"))
            .where(Tour.is_active == True)  # noqa: E712
            .group_by(Tour.city)
            .order_by(func.count(Tour.id).desc())
        )
    ).all()
    return [{"city": r[0], "count": r[1]} for r in rows if r[0]]


@router.get("/top", response_model=list[TourResponse], summary="Eng yaxshi turlar")
async def get_top_tours(
    limit: int = Query(6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
) -> list[TourResponse]:
    """Get top rated tours."""
    from sqlalchemy import func, select
    from app.models.tour import Tour
    from app.models.review import Review

    # Get top tours by average rating
    subquery = select(
        Review.tour_id,
        func.avg(Review.rating).label("avg_rating"),
        func.count(Review.id).label("review_count"),
    ).group_by(Review.tour_id).subquery()

    result = await db.execute(
        select(Tour)
        .options(selectinload(Tour.company))
        .outerjoin(subquery, Tour.id == subquery.c.tour_id)
        .where(Tour.is_active == True)  # noqa: E712
        .order_by(subquery.c.avg_rating.desc().nulls_last())
        .limit(limit)
    )
    tours = result.scalars().all()
    service = TourService(db)
    return [service._to_response(t) for t in tours]


@router.get("/{tour_id}", response_model=TourResponse, summary="Tur tafsilotlari")
async def get_tour(
    tour_id: int,
    db: AsyncSession = Depends(get_db),
) -> TourResponse:
    """Get tour details."""
    service = TourService(db)
    return await service.get_tour(tour_id)


@router.post(
    "",
    response_model=TourResponse,
    summary="Tur yaratish",
    dependencies=[Depends(role_required(UserRole.ADMIN))],
)
async def create_tour(
    data: TourCreate,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> TourResponse:
    """Admin creates a new tour package."""
    service = TourService(db)
    return await service.create_tour(current_user, data)


@router.patch(
    "/{tour_id}",
    response_model=TourResponse,
    summary="Tur tahrirlash",
    dependencies=[Depends(role_required(UserRole.ADMIN))],
)
async def update_tour(
    tour_id: int,
    data: TourUpdate,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> TourResponse:
    """Admin updates tour package."""
    service = TourService(db)
    return await service.update_tour(current_user, tour_id, data)


@router.delete(
    "/{tour_id}",
    summary="Tur o'chirish",
    dependencies=[Depends(role_required(UserRole.ADMIN))],
)
async def delete_tour(
    tour_id: int,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Admin soft-deletes tour."""
    service = TourService(db)
    return await service.delete_tour(current_user, tour_id)


@router.post(
    "/{tour_id}/image",
    response_model=TourResponse,
    summary="Tur rasmi yuklash",
    dependencies=[Depends(role_required(UserRole.ADMIN))],
)
async def upload_tour_image(
    tour_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> TourResponse:
    """Upload tour cover image — validates type, size, and magic bytes."""
    # persistent_upload_dir — Railway volume'i. Ilgari bu yerda `upload_dir`
    # ishlatilgani uchun rasm vaqtinchalik diskka yozilar, `/uploads` esa
    # volume'dan tarqatilardi: deploy'dan keyin barcha rasmlar 404 bo'lardi.
    image_url = await save_image(
        file,
        settings.persistent_upload_dir,
        settings.max_upload_size_mb * 1024 * 1024,
    )
    service = TourService(db)
    return await service.upload_image(current_user, tour_id, image_url)
