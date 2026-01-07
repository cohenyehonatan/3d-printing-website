# USPS Address Validation - Architecture Diagram

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      ShippingDashboard (React)                   │
│                                                                   │
│  Selected Order with Address Fields                              │
│  ├─ Street Address: "123 Main St"                                │
│  ├─ City: "Springfield"                                          │
│  ├─ State: "IL"                                                  │
│  └─ ZIP: "62701"                                                 │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ [✓ Validate Address] ← Button triggers validation       │    │
│  └─────────────────────────────────────────────────────────┘    │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ POST /api/validate-address
                         │ {streetAddress, city, state, zip}
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                FastAPI Backend (quote.py)                        │
│                                                                   │
│  @app.post('/api/validate-address')                              │
│  ├─ Validate request parameters                                  │
│  ├─ Create AddressValidationRequest                              │
│  └─ Call usps_service.validate_address()                         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ import usps_service
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              USPS Service (usps_service.py)                      │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ TokenCache (In-Memory)                                   │   │
│  │  ├─ token: str                                           │   │
│  │  └─ expires_at: float (timestamp)                        │   │
│  │                                                          │   │
│  │  get_token() → str | None                               │   │
│  │  ├─ If valid and not expired → return cached token      │   │
│  │  └─ If expired/missing → return None (force refresh)    │   │
│  │                                                          │   │
│  │  set_token(token, expires_in)                           │   │
│  │  └─ Cache with expiry = now + expires_in - 30s buffer   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ USPSService                                              │   │
│  │                                                          │   │
│  │ async _get_access_token()                               │   │
│  │  ├─ Check token cache (get_token)                       │   │
│  │  ├─ If valid → return cached token                      │   │
│  │  ├─ If invalid → POST to USPS OAuth2 endpoint           │   │
│  │  └─ Cache new token                                     │   │
│  │                                                          │   │
│  │ async validate_address(request)                         │   │
│  │  ├─ Get access token                                    │   │
│  │  ├─ Build query params from request                     │   │
│  │  ├─ GET https://apis.usps.com/addresses/v3/address      │   │
│  │  │    + Authorization: Bearer {token}                   │   │
│  │  │    + params: {streetAddress, city, state, zip...}    │   │
│  │  │                                                       │   │
│  │  ├─ Handle responses:                                   │   │
│  │  │  ├─ 200 OK → return {error: false, data: {...}}      │   │
│  │  │  ├─ 429 Rate Limited → return {error: true,          │   │
│  │  │  │   code: RATE_LIMITED, retry_after_seconds: N}     │   │
│  │  │  ├─ 400/404 → return {error: true, message: ...}     │   │
│  │  │  └─ Network error → return {error: true, ...}        │   │
│  │  └─                                                      │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 │ Response: {error: false, data: {...}}
                 │         OR {error: true, code: "RATE_LIMITED", retry_after: 30}
                 │         OR {error: true, message: "..."}
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│         Frontend Response Handling (ShippingDashboard)            │
│                                                                   │
│  if response.error && response.code === "RATE_LIMITED"           │
│  │                                                               │
│  │  ├─ setRateLimitCountdown(response.retry_after_seconds)      │
│  │  ├─ Show "⏳ Retry in 30s" on button                          │
│  │  ├─ setValidationError("Rate limited...")                    │
│  │  │                                                            │
│  │  └─ After countdown:                                         │
│  │      └─ validateAddressWithBackoff(attempt + 1)              │
│  │         ├─ Exponential backoff: 2s → 5s → 10s                │
│  │         └─ Max 3 attempts total                              │
│  │                                                               │
│  ├─ Else if response.error                                       │
│  │  └─ setValidationError(response.message)                     │
│  │     └─ Show red error banner                                 │
│  │                                                               │
│  └─ Else (success)                                               │
│      ├─ setValidatedAddress(response.data.address)              │
│      ├─ Check if hasMultipleMatches                             │
│      │                                                           │
│      ├─ If multiple matches (code 22):                          │
│      │  ├─ setMultipleMatches(response.matches)                 │
│      │  ├─ setShowMatchModal(true)                              │
│      │  └─ User selects address via modal                       │
│      │     └─ applyValidatedAddress(selected)                   │
│      │        ├─ Update editFields with standardized address    │
│      │        ├─ Update selectedOrder display                   │
│      │        └─ Close modal                                    │
│      │                                                           │
│      └─ Else single match:                                      │
│         ├─ applyValidatedAddress()                              │
│         ├─ Show green success banner                            │
│         └─ Address fields auto-updated                          │
│                                                                   │
│  User can now save with: [Save Shipping Details] button          │
│  └─ updateShippingDetails() → PATCH /api/dashboard/...          │
│     └─ Saves standardized address to database                   │
└─────────────────────────────────────────────────────────────────┘
```

## Token Caching Flow

```
User clicks "Validate Address"
        ↓
validateAddressWithBackoff()
        ↓
POST /api/validate-address
        ↓
USPSService.validate_address()
        ↓
_get_access_token()
        ↓
TokenCache.get_token()
        ↓
┌─────────────────────────────────┐
│ Is token cached and not expired?│
└────┬─────────────────────────┬──┘
     │ YES                     │ NO
     │                         │
     ▼                         ▼
Return cached        POST https://apis.usps.com/oauth2/v3/token
token (0 delay)              ↓
     │          ┌────────────────────────┐
     │          │ Parse response:        │
     │          │ {                      │
     │          │  "access_token": "...",│
     │          │  "expires_in": 3600    │
     │          │ }                      │
     │          └────────┬───────────────┘
     │                   │
     │          TokenCache.set_token()
     │          (expiry = now + 3600 - 30)
     │                   │
     └─────────┬─────────┘
               │
        Use token in:
        GET /address?
            streetAddress=...
            state=...
            Authorization: Bearer {token}
```

## Rate Limiting Retry Flow

```
GET /address returns 429
            ↓
response.status_code === 429
            ↓
Extract Retry-After header (e.g., "30")
            ↓
Calculate wait: max(30, backoff[attempt])
Backoff array: [2000ms, 5000ms, 10000ms]
            ↓
┌─────────────────────────────────────────┐
│ Show UI: "⏳ Retry in 30s" (countdown)  │
│ Disable button during countdown         │
│ Update state: rateLimitCountdown = 30   │
└──────────────┬──────────────────────────┘
               │
               │ Timer ticks every 1 second
               │ setRateLimitCountdown(n-1)
               │
               │ After 30 seconds...
               │
               ▼
               │
         rateLimitCountdown === 0
               │
               ▼
        Auto-retry:
    validateAddressWithBackoff(attempt + 1)
               │
         ┌─────┴─────┐
         │           │
    Attempt 1   Attempt 2   Attempt 3   Attempt 4
    wait 2s     wait 5s     wait 10s    (GIVE UP)
         │           │           │           │
         ├───────────┼───────────┤           │
         │ All use same backoff logic        │
         │ (exponential delay increases)     │
         │                                   │
         └─────────────────────────────────┬─┘
                                           │
                                If all fail:
                           Show error message
                           Button returns to normal
                           User can click again
```

## Multiple Address Matches Modal

```
USPS returns address with corrections: [{code: "22", ...}]
Meaning: Multiple addresses found
            ↓
response.hasMultipleMatches = true
response.matches = [
  {address: {streetAddress: "...", city: "...", ...}, ...},
  {address: {streetAddress: "...", city: "...", ...}, ...},
  {address: {streetAddress: "...", city: "...", ...}, ...}
]
            ↓
setMultipleMatches(response.matches)
setShowMatchModal(true)
            ↓
┌────────────────────────────────────────────┐
│ Modal appears (overlay background)         │
│                                            │
│ Multiple Address Matches Found             │
│ Select the correct one:                    │
│                                            │
│ ◯ 123 Main Street, Springfield, IL 62701  │
│ ◯ 123 Main St, Springfield, IL 62701-1234 │
│ ◯ 123 Main Avenue, Springfield, IL 62701  │
│                                            │
│ [Cancel]  [Apply Selected Address]        │
└────────────────────────────────────────────┘
            │
    User selects radio button
            │
    User clicks "Apply Selected Address"
            │
            ▼
    applyValidatedAddress(selectedMatch)
            │
            ├─ Update editFields:
            │  ├─ street_address: selectedMatch.streetAddress
            │  ├─ apt_suite: selectedMatch.secondaryAddress
            │  ├─ city: selectedMatch.city
            │  ├─ state: selectedMatch.state
            │  └─ zip_code: selectedMatch.ZIPCode
            │
            ├─ Update selectedOrder display
            │
            ├─ setShowMatchModal(false)
            │
            └─ setValidationSuccess(true)
                    │
                    ▼
            Green success banner:
            "✓ Address validated and standardized"
                    │
                    ▼
            User can now click:
            [Save Shipping Details]
```

## State Management

```
ShippingDashboard Component State:

Existing State:
├─ orders: PrintOrder[]
├─ selectedOrder: PrintOrder | null
├─ editFields: { ship_date, reference_number_1, ... }
└─ ...other fields...

NEW Address Validation State:
├─ validationLoading: boolean
│  └─ True while POST /api/validate-address is pending
├─ validationError: string | null
│  └─ Error message from API or user-facing error
├─ validationSuccess: boolean
│  └─ True if validation completed without error
├─ validatedAddress: object | null
│  └─ Standardized address from USPS
├─ multipleMatches: object[] | null
│  └─ Array of address matches if code 22 returned
├─ showMatchModal: boolean
│  └─ True when modal should be displayed
├─ rateLimitCountdown: number
│  └─ Seconds remaining until retry (0 = not rate limited)
└─ rateLimitRetryAttempt: number
   └─ Current retry attempt number (0-2)

Effects:
├─ fetchOrders() on mount
├─ Clear validation state when selectedOrder changes
└─ Countdown timer when rateLimitCountdown > 0
```

## API Response Examples

### Success with Single Match (Code 31)
```json
{
  "error": false,
  "address": {
    "streetAddress": "123 Main Street",
    "secondaryAddress": "",
    "city": "Springfield",
    "state": "IL",
    "ZIPCode": "62701",
    "ZIPPlus4": "1234"
  },
  "additionalInfo": {
    "deliveryPoint": "00",
    "carrierRoute": "C001",
    "DPVConfirmation": "Y"
  },
  "corrections": [{
    "code": "31",
    "text": "Single Response - exact match"
  }],
  "matches": [],
  "hasMultipleMatches": false
}
```

### Multiple Matches Found (Code 22)
```json
{
  "error": false,
  "address": { /* primary address */ },
  "corrections": [{
    "code": "22",
    "text": "Multiple addresses were found"
  }],
  "matches": [
    { "address": { /* option 1 */ } },
    { "address": { /* option 2 */ } },
    { "address": { /* option 3 */ } }
  ],
  "hasMultipleMatches": true
}
```

### Rate Limited (429)
```json
{
  "error": true,
  "code": "RATE_LIMITED",
  "message": "Too many requests to USPS API",
  "retry_after_seconds": 30
}
```

### Configuration Error
```json
{
  "error": true,
  "code": "UNCONFIGURED",
  "message": "USPS API credentials not configured"
}
```

---

**This architecture ensures reliable, rate-limit-safe address validation with excellent UX!** ✓
