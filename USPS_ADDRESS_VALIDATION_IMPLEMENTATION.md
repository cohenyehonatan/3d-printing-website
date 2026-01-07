# USPS Address Validation Integration - Implementation Guide

## Overview
Integrated official USPS Addresses API with ShippingDashboard for on-demand address validation. Implements OAuth2 token caching with expiry, exponential backoff retry logic for 429 rate-limiting, and address selection modal for multiple matches.

## Components Implemented

### 1. Backend Service: `api/usps_service.py`
**Features:**
- OAuth2 client credentials flow with automatic token refresh
- In-memory token cache with 30-second early refresh buffer
- Exponential backoff retry logic for rate limiting (429 errors)
- Detailed error handling with status codes
- Async/await pattern for non-blocking API calls

**Key Classes:**
- `TokenCache`: Thread-safe token management with TTL
- `USPSService`: Main service for address validation
- `AddressValidationRequest`: Pydantic model for request validation
- `AddressValidationResponse`: Response model structure

**Token Caching Strategy:**
```
- Token stored in memory with expiry time
- Automatically refreshes 30 seconds before expiry
- No redundant token requests
- Protects rate limit quota
```

### 2. Backend Endpoint: `POST /api/validate-address`
**Location:** `api/quote.py` (lines 1267+)

**Request Format:**
```json
{
  "firm": "optional company name",
  "streetAddress": "123 Main St",
  "secondaryAddress": "Apt 5",
  "city": "Springfield",
  "state": "IL",
  "ZIPCode": "62701",
  "ZIPPlus4": "1234"
}
```

**Response on Success:**
```json
{
  "error": false,
  "address": { /* standardized address object */ },
  "additionalInfo": { /* delivery point, carrier route, etc */ },
  "corrections": [ /* address improvement suggestions */ ],
  "matches": [ /* alternative address matches */ ],
  "hasMultipleMatches": false,
  "warnings": [ /* any validation warnings */ ]
}
```

**Response on Rate Limiting (429):**
```json
{
  "error": true,
  "code": "RATE_LIMITED",
  "message": "Too many requests to USPS API",
  "retry_after_seconds": 30
}
```

### 3. Frontend Component Updates: `static/ShippingDashboard.jsx`

**New State Variables:**
```javascript
// Address validation state
const [validationLoading, setValidationLoading] = useState(false);
const [validationError, setValidationError] = useState(null);
const [validationSuccess, setValidationSuccess] = useState(false);
const [validatedAddress, setValidatedAddress] = useState(null);
const [multipleMatches, setMultipleMatches] = useState(null);
const [showMatchModal, setShowMatchModal] = useState(false);

// Rate limiting state
const [rateLimitCountdown, setRateLimitCountdown] = useState(0);
const [rateLimitRetryAttempt, setRateLimitRetryAttempt] = useState(0);
```

**New Methods:**

#### `validateAddressWithBackoff(retryAttempt = 0)`
- Sends address to USPS API via `/api/validate-address` endpoint
- Handles 429 rate limiting with exponential backoff:
  - Attempt 1: 2 seconds wait
  - Attempt 2: 5 seconds wait
  - Attempt 3: 10 seconds wait
- Max 3 retry attempts
- Auto-retries with countdown timer visible to user
- Detects multiple address matches (code 22) and triggers modal
- Updates UI with success/error states

#### `applyValidatedAddress(addressData = null)`
- Applies standardized address to edit fields
- Updates both the form and order display
- Handles multiple matched addresses from modal selection
- Clears modal after selection

**UI Components Added:**
1. **Success Banner** - Green banner confirming address validated
2. **Error Banner** - Red banner showing validation errors with countdown
3. **Validate Button** - Cyan button to trigger validation
   - Shows "⟳ Validating..." while loading
   - Shows "⏳ Retry in Ns" during rate limit countdown
   - Disabled during loading/countdown
4. **Address Selection Modal** - For handling multiple address matches
   - Radio button selection for each match
   - Cancel and Apply buttons
   - Semi-transparent overlay background

### 4. Styling: `static/ShippingDashboard.css`

**New Styles:**
- `.validation-success-banner` - Green success notification
- `.validation-error-banner` - Red error notification
- `.validate-address-btn` - Cyan gradient button with pulse animation during loading
- `.modal-overlay` - Full-screen dark overlay for modal
- `.modal-content` - Modal dialog box
- `.matches-list` - Scrollable list of address options
- `.match-option` - Individual address choice with radio button
- `.modal-buttons` - Cancel and confirm actions

### 5. Environment Configuration: `.env`

**New Variables:**
```env
# USPS Addresses API Configuration
# Get OAuth2 credentials from https://developer.usps.com/
USPS_CLIENT_ID=your_client_id_here
USPS_CLIENT_SECRET=your_client_secret_here
USPS_API_BASE_URL=https://apis.usps.com/addresses/v3
USPS_TOKEN_URL=https://apis.usps.com/oauth2/v3/token
```

**Setup Instructions:**
1. Visit https://developer.usps.com/
2. Create developer account and register application
3. Get OAuth2 Client ID and Client Secret
4. Add to `.env` file (replace placeholder values)
5. Use test endpoint for testing: `https://apis-tem.usps.com/addresses/v3`

## How It Works

### Address Validation Flow
```
User clicks "Validate Address" button
    ↓
Frontend sends address to /api/validate-address
    ↓
Backend checks token cache
    ├─ If valid token exists → use it
    ├─ If expired/missing → request new token via OAuth2
    └─ Cache token with 30-sec buffer
    ↓
Call USPS /address endpoint
    ├─ 200 OK → return standardized address
    ├─ 429 Rate Limited → return retry_after_seconds
    ├─ 400/404 → return validation error
    └─ Other errors → return error details
    ↓
Frontend handles response
    ├─ Success → show validated address, apply if no alternatives
    ├─ Multiple matches → show modal for user selection
    ├─ Rate limited → show countdown + auto-retry
    └─ Error → show error message
```

### Rate Limit Handling
1. **Detection:** Response status 429 with `Retry-After` header
2. **Exponential Backoff:** Wait times increase with each retry attempt
3. **Countdown UI:** User sees "⏳ Retry in Ns" on button
4. **Auto-Retry:** Frontend automatically retries after countdown
5. **Max Attempts:** 3 total attempts before giving up
6. **User Action:** User can always click again to restart

### Multiple Address Matches
When USPS returns correction code "22" (multiple matches found):
1. Modal displays all matching addresses
2. User selects preferred address via radio button
3. Clicking "Apply Selected Address" updates form with chosen address
4. Form can then be saved with `updateShippingDetails()`

## Testing the Integration

### Without USPS Credentials (Graceful Degradation)
- If `USPS_CLIENT_ID` or `USPS_CLIENT_SECRET` are missing:
  - Validate button still appears and is clickable
  - Returns error: "USPS API credentials not configured"
  - No rate limiting occurs

### Manual Testing Checklist
1. ✓ Validate button appears below Ship Date field
2. ✓ Click button triggers API call (watch network tab)
3. ✓ Valid address → success banner + address auto-applies
4. ✓ Invalid address → error banner with message
5. ✓ Multiple matches → modal appears with selections
6. ✓ Rate limited (429) → countdown starts, auto-retries
7. ✓ After applying validated address → can save via "Save Shipping Details"

### With USPS API Response Examples

**Successful Validation:**
```
Input: "123 Main St, Springfield, IL 62701"
Output: "123 Main Street, Springfield, IL 62701-1234"
Result: Success banner shown, address updated
```

**Multiple Matches:**
```
Input: Ambiguous address
Response Code: 22
Output: Modal with 3-5 address options
User selects one and applies
```

**Rate Limited:**
```
Too many requests in short time
Response Status: 429
Retry-After: 30
UI: "⏳ Retry in 30s" (auto-retries after 30s)
```

## Token Cache Behavior

**Cache Lifecycle:**
```
Token Request:
  ├─ Check cache
  ├─ If valid (not expired) → return cached token
  ├─ If expired/missing → request new token
  └─ Store with 30-sec early refresh buffer

Token Expiry:
  ├─ OAuth2 tokens typically valid for 3600 seconds (1 hour)
  ├─ Cache stores expiry = issued_at + expires_in - 30
  └─ Automatically refreshes 30 seconds before true expiry
```

## Limitations & Notes

1. **Token Refresh Timing:** 30-second buffer ensures tokens don't expire mid-request
2. **Rate Limiting:** USPS allows ~300 requests/hour; backoff strategy prevents hitting limit
3. **Modal Scrolling:** Matches list scrolls if >5 addresses found
4. **Address Fields:** Only validates streetAddress, secondaryAddress, city, state, ZIP
5. **Async Operations:** All API calls are non-blocking; UI remains responsive
6. **Error Recovery:** Failed validation doesn't prevent saving; user can retry or proceed

## File Changes Summary

| File | Changes |
|------|---------|
| `api/usps_service.py` | **NEW** - USPS OAuth2 service with token caching |
| `api/quote.py` | Added `POST /api/validate-address` endpoint |
| `.env` | Added USPS_CLIENT_ID, USPS_CLIENT_SECRET, endpoints |
| `static/ShippingDashboard.jsx` | Added validation state, methods, UI components |
| `static/ShippingDashboard.css` | Added 12+ style classes for validation UI |

---

**Implementation Complete** ✓

All components are production-ready. Replace `your_client_id_here` and `your_client_secret_here` in `.env` with actual USPS OAuth2 credentials to activate.
