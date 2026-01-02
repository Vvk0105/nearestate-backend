import ssl
from django.core.mail.backends.smtp import EmailBackend as SMTPBackend

class UnverifiedSSLEmailBackend(SMTPBackend):
    """
    ⚠️ DEV-ONLY SMTP backend that disables SSL verification.
    """
    def open(self):
        if self.connection is None:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            self.ssl_context = ssl_context
            try:
                return super().open()
            finally:
                del self.ssl_context
        return False
