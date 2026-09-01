# mobile_sms

Native **Kotlin** Android app for the operator side.

Responsibilities:
- Configure the allowed deposit-sender phone number(s)
- Authenticate to the API with a dedicated `api_token` (never the admin password)
- Read incoming deposit SMS and POST the raw text to the server
- Show connection status / last successful send

Built in **phase 10** (see `PROGRESS.md`).
