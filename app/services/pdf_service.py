"""PDF voucher generation using fpdf2."""

from io import BytesIO

from fpdf import FPDF

from app.models.booking import Booking


class VoucherPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 16)
        self.set_fill_color(79, 70, 229)  # indigo-600
        self.rect(0, 0, 210, 20, "F")
        self.set_text_color(255, 255, 255)
        self.cell(0, 12, "SAVDOGAR - Bron Voucheri", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, "savdogar.uz  |  Barcha huquqlar himoyalangan", align="C")


def _row(pdf: FPDF, label: str, value: str) -> None:
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(245, 245, 250)
    pdf.cell(55, 9, label, border=0, fill=True, new_x="RIGHT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 9, value, border=0, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)


def generate_voucher(booking: Booking) -> bytes:
    """Return PDF bytes for a booking voucher."""
    pdf = VoucherPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Booking ID badge
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(79, 70, 229)
    pdf.cell(0, 12, f"Bron #{booking.id}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    # Divider
    pdf.set_draw_color(220, 220, 230)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)

    tour_title = booking.tour.title if booking.tour else str(booking.tour_id)
    user_name = booking.user.full_name if booking.user else str(booking.user_id)
    user_email = booking.user.email if booking.user else ""
    company_name = booking.tour.company.name if (booking.tour and booking.tour.company) else ""
    start = booking.tour.start_date.strftime("%d.%m.%Y") if booking.tour else ""
    end = booking.tour.end_date.strftime("%d.%m.%Y") if booking.tour else ""
    city = booking.tour.city if booking.tour else ""

    _row(pdf, "Mijoz:", user_name)
    _row(pdf, "Email:", user_email)
    _row(pdf, "Tur:", tour_title)
    _row(pdf, "Shahar:", city)
    _row(pdf, "Sana:", f"{start} - {end}")
    _row(pdf, "Mehmonlar:", str(booking.guests_count))
    _row(pdf, "Narx:", f"{booking.total_price:,.0f} so'm")
    _row(pdf, "Kompaniya:", company_name)

    # Status badge
    pdf.ln(4)
    status_colors = {
        "confirmed": (34, 197, 94),
        "pending": (234, 179, 8),
        "cancelled": (239, 68, 68),
    }
    status_labels = {"confirmed": "TASDIQLANGAN", "pending": "KUTILMOQDA", "cancelled": "BEKOR QILINDI"}
    r, g, b = status_colors.get(booking.status.value, (100, 100, 100))
    pdf.set_fill_color(r, g, b)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 10, status_labels.get(booking.status.value, booking.status.value), align="C", fill=True)
    pdf.set_text_color(0, 0, 0)

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()
