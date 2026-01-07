# Quick Start: USPS Address Validation

## 1. Get USPS OAuth2 Credentials

1. Go to https://developer.usps.com/
2. Sign up for a developer account (if needed)
3. Create an OAuth Application
4. Copy your **Client ID** and **Client Secret**

## 2. Configure Environment Variables

Edit `.env` and replace the placeholder values:

```env
USPS_CLIENT_ID=your_actual_client_id_here
USPS_CLIENT_SECRET=your_actual_client_secret_here
```

Optional: For testing, use the test endpoint:
```env
USPS_API_BASE_URL=https://apis-tem.usps.com/addresses/v3
USPS_TOKEN_URL=https://apis-tem.usps.com/oauth2/v3/token
```

## 3. Install httpx (if not already installed)

```bash
pip install httpx
```

The `usps_service.py` requires `httpx` for async HTTP requests.

## 4. Start the Server

```bash
source venv/bin/activate
uvicorn api.quote:app --reload --port 8003
```

## 5. Test in ShippingDashboard

1. Open the Shipping Dashboard
2. Select an order
3. Click the **Validate Address** button
4. Watch the validation happen:
   - ✓ Valid → Green success banner, address standardized
   - ❌ Invalid → Red error banner with details
   - ? Multiple → Modal to select correct address
   - ⏳ Rate Limited → Countdown timer with auto-retry

## Key Features

| Feature | Behavior |
|---------|----------|
| **Token Caching** | OAuth2 tokens cached in memory, auto-refreshed 30s before expiry |
| **Rate Limiting (429)** | Auto-retry with exponential backoff (2s, 5s, 10s) |
| **Multiple Matches** | Modal selector for user to pick correct address |
| **Graceful Fallback** | Button still works if credentials missing (shows error) |
| **Countdown UI** | Visual timer shows when next retry will occur |

## Troubleshooting

### "USPS API credentials not configured"
- Check `.env` file has `USPS_CLIENT_ID` and `USPS_CLIENT_SECRET`
- Make sure `.env` was reloaded (restart server)

### "Address validation failed" with no details
- Check browser console for error details
- Verify client ID/secret are correct
- Try test endpoint: `apis-tem.usps.com`

### "Too many requests" / 429 errors
- Button will automatically retry with countdown
- Wait for countdown to complete, then try again
- Consider spacing out requests

### Token expires during request
- Should not happen; 30-second buffer handles this
- If it does, button will auto-retry

## Development vs Production

**Test Endpoint (Development):**
```env
USPS_API_BASE_URL=https://apis-tem.usps.com/addresses/v3
```

**Production Endpoint:**
```env
USPS_API_BASE_URL=https://apis.usps.com/addresses/v3
```

Change in `.env` to switch environments.

## Rate Limits

- USPS allows ~300 requests/hour per OAuth2 app
- Implementation includes exponential backoff to prevent hitting limit
- Each address validation = 1 request (OAuth token refresh doesn't count toward limit in most cases)

## API Response Codes

| Code | Meaning | UI Behavior |
|------|---------|------------|
| 31 | Exact match | ✓ Success - address standardized |
| 22 | Multiple matches | ? Show modal - user selects |
| 32 | Needs more info | ℹ️ Show suggestion |
| 429 | Rate limited | ⏳ Auto-retry with countdown |
| 400/404 | Invalid address | ❌ Show error message |

---

**Ready to validate!** Click the button and watch it work. 🚀
