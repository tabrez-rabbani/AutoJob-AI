"""
AutoJob AI — Email Sender Service
Sends tailored cover letters + resume attachments via SMTP.
Enforces daily email limits to prevent spam.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger("autojob.services.email_sender")

# Safety limit
MAX_EMAILS_PER_DAY = 10


class EmailSender:
    """Send professional application emails via SMTP."""

    def __init__(
        self,
        smtp_email: str,
        smtp_password: str,
        smtp_host: str = "smtp.gmail.com",
        smtp_port: int = 587,
    ):
        self.smtp_email = smtp_email
        self.smtp_password = smtp_password
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port

    async def send_application_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        resume_path: str | None = None,
        sender_name: str = "",
    ) -> dict:
        """
        Send a single application email with optional resume attachment.

        Args:
            to_email: Recruiter/HR email address
            subject: Email subject line
            body: Email body text
            resume_path: Path to resume PDF to attach
            sender_name: Sender's display name

        Returns:
            {"status": "sent"|"failed", "message": "..."}
        """
        try:
            # Build the email
            msg = MIMEMultipart()
            msg["From"] = f"{sender_name} <{self.smtp_email}>" if sender_name else self.smtp_email
            msg["To"] = to_email
            msg["Subject"] = subject

            # Email body
            msg.attach(MIMEText(body, "plain", "utf-8"))

            # Attach resume if provided
            if resume_path:
                resume_file = Path(resume_path)
                if resume_file.exists():
                    with open(resume_file, "rb") as f:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(f.read())
                        encoders.encode_base64(part)

                        # Clean filename for attachment
                        filename = resume_file.name
                        if sender_name:
                            ext = resume_file.suffix
                            filename = f"{sender_name.replace(' ', '_')}_Resume{ext}"

                        part.add_header(
                            "Content-Disposition",
                            f"attachment; filename={filename}",
                        )
                        msg.attach(part)
                    logger.info(f"  📎 Resume attached: {filename}")
                else:
                    logger.warning(f"  Resume file not found: {resume_path}")

            # Send via SMTP
            logger.info(f"  📧 Sending email to {to_email}...")

            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self.smtp_email, self.smtp_password)
                server.send_message(msg)

            logger.info(f"  ✅ Email sent to {to_email}")
            return {"status": "sent", "message": f"Email sent to {to_email}"}

        except smtplib.SMTPAuthenticationError:
            logger.error("  ❌ SMTP authentication failed — check email/password")
            return {"status": "failed", "message": "SMTP authentication failed. Check your email and app password."}
        except smtplib.SMTPException as e:
            logger.error(f"  ❌ SMTP error: {e}")
            return {"status": "failed", "message": f"SMTP error: {str(e)}"}
        except Exception as e:
            logger.error(f"  ❌ Email send failed: {e}")
            return {"status": "failed", "message": str(e)}

    @staticmethod
    async def check_daily_limit(db_session, user_id: str) -> int:
        """
        Check how many emails have been sent today.

        Returns:
            Number of remaining emails allowed today.
        """
        from sqlalchemy import select, func
        from app.models.application import Application

        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        result = await db_session.execute(
            select(func.count(Application.id))
            .where(Application.user_id == user_id)
            .where(Application.apply_method == "email")
            .where(Application.created_at >= today_start)
        )
        sent_today = result.scalar() or 0
        remaining = max(0, MAX_EMAILS_PER_DAY - sent_today)

        logger.info(f"  📊 Emails today: {sent_today}/{MAX_EMAILS_PER_DAY} | Remaining: {remaining}")
        return remaining

    @staticmethod
    async def test_connection(
        smtp_email: str,
        smtp_password: str,
        smtp_host: str = "smtp.gmail.com",
        smtp_port: int = 587,
    ) -> dict:
        """Test SMTP connection without sending an email."""
        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(smtp_email, smtp_password)
            return {"status": "success", "message": "SMTP connection successful!"}
        except smtplib.SMTPAuthenticationError:
            return {"status": "failed", "message": "Authentication failed. Check your email and app password."}
        except Exception as e:
            return {"status": "failed", "message": str(e)}
