"""Email notification service."""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.config import get_settings

settings = get_settings()


class EmailService:
    """Send emails via SMTP."""

    def __init__(self):
        self.smtp_host = settings.smtp_host
        self.smtp_port = settings.smtp_port
        self.smtp_user = settings.smtp_user
        self.smtp_password = settings.smtp_password
        self.from_email = settings.smtp_from_email or "noreply@savdogar.uz"

    async def send_booking_confirmation(
        self, to_email: str, user_name: str, tour_title: str, amount: float, booking_id: int
    ) -> bool:
        """Send booking confirmation email."""
        subject = f"Bron tasdiqlandi — {tour_title}"
        html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
                    <h2 style="color: #3525cd;">Bron Tasdiqlandi! ✓</h2>
                    <p>Salom {user_name},</p>
                    <p>Sizning bron-buyurtmangiz muvaffaqiyatli qabul qilindi.</p>

                    <div style="background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">{tour_title}</h3>
                        <p><strong>Jami summa:</strong> {amount:,.0f} so'm</p>
                        <p><strong>Bron ID:</strong> #{booking_id}</p>
                    </div>

                    <p>Bron statusini tekshirish uchun: <a href="https://savdogar-sable.vercel.app/my-bookings">Mening bronlarim</a></p>

                    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                    <p style="font-size: 12px; color: #999;">
                        © 2025 Savdogar. Agar savol bo'lsa, biz bilan bog'laning.
                    </p>
                </div>
            </body>
        </html>
        """
        return await self._send_email(to_email, subject, html)

    async def send_booking_status_update(
        self, to_email: str, user_name: str, tour_title: str, status: str, reason: Optional[str] = None
    ) -> bool:
        """Send booking status update email."""
        status_uz = {
            "confirmed": "Tasdiqlandi ✓",
            "cancelled": "Bekor qilindi ✗",
            "pending": "Kutilmoqda",
        }.get(status, status)

        subject = f"Bron yangilanishi — {tour_title}"
        html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
                    <h2 style="color: #3525cd;">Bron Statusingiz O'zgardi</h2>
                    <p>Salom {user_name},</p>

                    <div style="background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">{tour_title}</h3>
                        <p><strong>Yangi status:</strong> <span style="color: #3525cd; font-weight: bold;">{status_uz}</span></p>
                        {f'<p><strong>Sababi:</strong> {reason}</p>' if reason else ''}
                    </div>

                    <p>Batafsil ma'lumot: <a href="https://savdogar-sable.vercel.app/my-bookings">Mening bronlarim</a></p>

                    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                    <p style="font-size: 12px; color: #999;">
                        © 2025 Savdogar
                    </p>
                </div>
            </body>
        </html>
        """
        return await self._send_email(to_email, subject, html)

    async def _send_email(self, to_email: str, subject: str, html: str) -> bool:
        """Send email via SMTP."""
        if not self.smtp_host or not self.smtp_user:
            print(f"[EMAIL] SMTP not configured, skipping: {to_email}")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to_email

            part = MIMEText(html, "html")
            msg.attach(part)

            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=5) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, [to_email], msg.as_string())

            print(f"[EMAIL] Sent to {to_email}: {subject}")
            return True
        except Exception as e:
            print(f"[EMAIL] Error sending to {to_email}: {e}")
            return False
