# Security Policy

## Reporting a Vulnerability

We take the security of this project seriously. If you discover a vulnerability or security flaw, please **do not report it through public GitHub issues or public channels**.

### Preferred Reporting Method

1. **GitHub Private Vulnerability Reporting (PVR)**:
   - Navigate to the repository's **Security** tab on GitHub.
   - Click **Report a vulnerability** under "Private vulnerability reporting".
   - Fill in the advisory form with detailed reproduction steps, impact, and proof of concept.

2. **Email Disclosure**:
   - Alternatively, email `security@brainstormity.com` with the subject `[SECURITY] Jev X Sentiment Analysis Vulnerability`.
   - Include:
     - Clear description of the vulnerability
     - Affected component(s)
     - Step-by-step reproduction instructions or PoC
     - Potential remediation suggestions

### Response Timeline

- **Initial Acknowledgment**: Within 48 hours.
- **Triage & Assessment**: Within 5 business days.
- **Fix & Advisory Release**: Coordinated with the reporter before public disclosure.

---

## Security Practices for Self-Hosting

1. **Network Binding**:
   - By default, bind the application to `127.0.0.1` (`HOST=127.0.0.1` in `.env`) when running locally.
   - If binding to `0.0.0.0`, configure a reverse proxy (e.g. Caddy, Nginx) with TLS and authentication.

2. **Settings Endpoint Protection**:
   - The `/api/v1/settings` endpoint is restricted to localhost requests by default.
   - If accessing the terminal remotely, set `ADMIN_TOKEN=<random-secret>` in `.env` and pass `X-Admin-Token: <random-secret>` in requests.

3. **CORS Restrictions**:
   - Specify your exact frontend domain(s) in `ALLOWED_ORIGINS` (comma-separated).
   - Never use wildcard `*` with authenticated credentials in production.
