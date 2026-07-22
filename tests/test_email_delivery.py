import smtplib
from unittest import TestCase
from unittest.mock import MagicMock, patch

from app.email_delivery import DeliveryUncertainError, EmailDeliveryConfig, SMTPEmailProvider


class EmailDeliveryTests(TestCase):
    def setUp(self):
        self.config = EmailDeliveryConfig(
            host="smtp.example.com",
            port=587,
            security="starttls",
            username="sender@example.com",
            password="app-password",
            from_email="sender@example.com",
            from_name="Example Agency",
            reply_to="privacy@example.com",
        )

    @patch("app.email_delivery.smtplib.SMTP")
    def test_starttls_login_and_send(self, smtp):
        client = MagicMock()
        client.__enter__.return_value = client
        smtp.return_value = client

        message_id = SMTPEmailProvider(self.config).send(
            "info@recipient.example",
            "A useful subject",
            "A short plain-text message.",
        )

        smtp.assert_called_once_with("smtp.example.com", 587, timeout=15)
        client.starttls.assert_called_once()
        client.login.assert_called_once_with("sender@example.com", "app-password")
        message = client.send_message.call_args.args[0]
        self.assertEqual(message["To"], "info@recipient.example")
        self.assertEqual(message["Reply-To"], "privacy@example.com")
        self.assertTrue(message_id.startswith("<"))

    def test_rejects_header_injection_and_missing_password(self):
        with self.assertRaisesRegex(ValueError, "Invalid subject"):
            SMTPEmailProvider(self.config).send(
                "info@recipient.example",
                "Hello\nBcc: victim@example.com",
                "Message",
            )
        invalid = EmailDeliveryConfig(**{**self.config.__dict__, "password": ""})
        with self.assertRaisesRegex(ValueError, "password"):
            invalid.validate()

    @patch("app.email_delivery.smtplib.SMTP")
    def test_delivery_errors_are_normalized(self, smtp):
        client = MagicMock()
        client.__enter__.return_value = client
        client.send_message.side_effect = smtplib.SMTPRecipientsRefused({})
        smtp.return_value = client

        with self.assertRaisesRegex(ValueError, "SMTP delivery failed"):
            SMTPEmailProvider(self.config).send("info@recipient.example", "Subject", "Message")

    @patch("app.email_delivery.smtplib.SMTP")
    def test_disconnect_during_send_is_quarantined_as_uncertain(self, smtp):
        client = MagicMock()
        client.__enter__.return_value = client
        client.send_message.side_effect = smtplib.SMTPServerDisconnected("response lost")
        smtp.return_value = client

        with self.assertRaisesRegex(DeliveryUncertainError, "reconcile Message-ID"):
            SMTPEmailProvider(self.config).send(
                "info@recipient.example", "Subject", "Message", "<stable@example.com>"
            )

    def test_plaintext_remote_authentication_is_rejected(self):
        insecure = EmailDeliveryConfig(**{**self.config.__dict__, "security": "none"})
        with self.assertRaisesRegex(ValueError, "require STARTTLS"):
            insecure.validate()
