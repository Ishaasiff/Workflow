import aiosmtplib
from email.message import EmailMessage

from app.config import settings


async def send_email(
    to_email: str,
    subject: str,
    html_body: str,
) -> None:
    msg = EmailMessage()
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.add_alternative(html_body, subtype="html")

    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
        start_tls=True,
    )


async def send_invite_email(
    to_email: str,
    org_name: str,
    inviter_name: str,
    invite_token: str,
) -> None:
    invite_url = f"{settings.frontend_url}/invite/{invite_token}"
    subject = f"You've been invited to join {org_name} on Workflow"
    html_body = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto; padding: 32px;">
        <h2 style="margin-bottom: 16px;">You're invited!</h2>
        <p style="margin-bottom: 16px;">
            <strong>{inviter_name}</strong> has invited you to join
            <strong>{org_name}</strong> on Workflow.
        </p>
        <p style="margin-bottom: 24px;">Click the button below to accept your invitation and create your account:</p>
        <a href="{invite_url}"
           style="display:inline-block; padding:12px 24px; background-color:#4f46e5; color:#fff;
                  text-decoration:none; border-radius:6px; font-weight:600;">
            Accept Invitation
        </a>
        <p style="margin-top:32px; font-size:13px; color:#888;">
            This link will expire in {settings.invite_token_expire_days} days. If you did not expect this
            invitation, you can safely ignore this email.
        </p>
    </div>
    """
    await send_email(to_email, subject, html_body)


async def send_password_reset_email(
    to_email: str,
    reset_token: str,
) -> None:
    reset_url = f"{settings.frontend_url}/reset-password/{reset_token}"
    subject = "Reset your Workflow password"
    html_body = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto; padding: 32px;">
        <h2 style="margin-bottom: 16px;">Reset your password</h2>
        <p style="margin-bottom: 24px;">
            We received a request to reset your Workflow password.
            Click the button below to choose a new password:
        </p>
        <a href="{reset_url}"
           style="display:inline-block; padding:12px 24px; background-color:#4f46e5; color:#fff;
                  text-decoration:none; border-radius:6px; font-weight:600;">
            Reset Password
        </a>
        <p style="margin-top:32px; font-size:13px; color:#888;">
            This link will expire in {settings.reset_token_expire_minutes} minutes.
            If you did not request this, you can safely ignore this email.
        </p>
    </div>
    """
    await send_email(to_email, subject, html_body)
