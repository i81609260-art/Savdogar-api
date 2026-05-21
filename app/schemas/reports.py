"""Reports and dashboard schemas."""

from typing import Dict, List

from pydantic import BaseModel


class SalesDataPoint(BaseModel):
    """Single period sales data."""

    period: str
    revenue: float
    bookings_count: int


class TopTourItem(BaseModel):
    """Top selling tour."""

    tour_id: int
    tour_title: str
    bookings_count: int
    revenue: float


class StatusDistribution(BaseModel):
    """Booking status chart data."""

    pending: int
    confirmed: int
    cancelled: int


class DashboardStats(BaseModel):
    """Admin dashboard KPIs."""

    today_bookings: int
    today_revenue: float
    active_tours: int
    total_customers: int
    pending_bookings: int


class ReportsResponse(BaseModel):
    """Full reports payload."""

    sales: List[SalesDataPoint]
    top_tours: List[TopTourItem]
    status_distribution: StatusDistribution
    dashboard: DashboardStats


class SuperAdminStats(BaseModel):
    """Platform-wide statistics."""

    total_companies: int
    pending_companies: int
    approved_companies: int
    total_users: int
    total_tours: int
    total_bookings: int
    total_revenue: float
