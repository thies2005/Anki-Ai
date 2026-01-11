"""
Email Client for sending welcome and password reset emails.
Supports SMTP and a fallback "Dev Mode" (logging to console).
"""
import smtplib
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

class EmailClient:
    def __init__(self):
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.example.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.username = os.getenv("SMTP_USERNAME", "user@example.com")
        self.password = os.getenv("SMTP_PASSWORD", "password")
        self.use_tls = os.getenv("SMTP_USE_TLS", "True").lower() == "true"
        
        # Check if config is dummy/default
        self.is_dev_mode = (self.smtp_server == "smtp.example.com")

    def send_email(self, to_email, subject, body_html):
        """Sends an email using SMTP or logs it in Dev Mode."""
        if self.is_dev_mode:
            logger.info(f"[DEV MODE] Sending Email to {to_email} | Subject: {subject}")
            print(f"[DEV MODE] Body: {body_html}")
            return True, "Email simulated (Dev Mode)"

        try:
            msg = MIMEMultipart()
            msg['From'] = self.username
            msg['To'] = to_email
            msg['Subject'] = subject

            msg.attach(MIMEText(body_html, 'html'))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
            
            return True, "Email sent successfully"
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False, f"Failed to send email: {e}"

    def send_welcome_email(self, to_email):
        subject = "Welcome to Anki AI!"
        body = f"""
        <h1>Welcome to Anki AI! 🩺</h1>
        <p>Thank you for registering. We are excited to help you turn your medical PDFs into Anki cards.</p>
        <p>Get started by uploading a PDF in the Generator tab.</p>
        <br>
        <p>Happy Studying!</p>
        <p><i>The Anki AI Team</i></p>
        """
        return self.send_email(to_email, subject, body)

    def send_reset_email(self, to_email, code):
        subject = "Anki AI - Password Reset"
        body = f"""
        <h1>Password Reset Request</h1>
        <p>You requested to reset your password.</p>
        <p>Your verification code is:</p>
        <h2>{code}</h2>
        <p>If you did not request this, please ignore this email.</p>
        """
        return self.send_email(to_email, subject, body)
