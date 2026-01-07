# UPS Rating API Implementation Guide

## Overview
The UPS Rating API has been integrated into your 3D printing website checkout flow to allow customers to select from multiple UPS shipping services with real-time pricing and delivery estimates.

## What Was Added

### 1. Backend: UPS Service (`api/ups_service.py`)
**New Method: `get_shipping_rates()`**
- Calls the UPS Rating API `/api/rating/v2409/Shop` endpoint
- Returns available UPS services with:
  - Service code (01=Next Day, 02=2nd Day, 03=Ground)
  - Service name (e.g., "UPS Ground", "UPS Next Day Air")
  - Cost in USD
  - Estimated delivery days
- Handles OAuth token caching and API errors gracefully

**Features:**
- Automatic token refresh
- Rate limiting handling
- Timeout protection (15 second timeout)
- Full error logging

### 2. API Endpoint (`api/quote.py`)
**New Endpoint: `POST /api/shipping-rates`**

**Request Body:**
```json
{
  "zip_code": "10001",
  "weight": 0.5,
  "length": 5.0,
  "width": 5.0,
  "height": 5.0
}
```

**Response:**
```json
{
  "error": false,
  "rates": [
    {
      "serviceCode": "03",
      "serviceName": "UPS Ground",
      "cost": 8.50,
      "currency": "USD",
      "estimatedDays": 5,
      "displayCost": "$8.50"
    },
    {
      "serviceCode": "02",
      "serviceName": "UPS 2nd Day Air",
      "cost": 15.99,
      "currency": "USD",
      "estimatedDays": 2,
      "displayCost": "$15.99"
    },
    {
      "serviceCode": "01",
      "serviceName": "UPS Next Day Air",
      "cost": 28.50,
      "currency": "USD",
      "estimatedDays": 1,
      "displayCost": "$28.50"
    }
  ],
  "weight": 0.5,
  "origin": "Timonium, MD 21093",
  "destination": "New York, NY 10001"
}
```

### 3. Frontend: Checkout Flow (`static/App.jsx`)
**New State Variables:**
- `shippingRates` - Array of available shipping options
- `selectedShippingService` - Currently selected shipping service
- `loadingRates` - Loading state for rates fetch

**New Functions:**
- `fetchShippingRates(weight)` - Called when moving to step 3 (Review & Order)
- Updated `proceedToCheckout()` - Now includes shipping service selection

**UI Changes:**
- Step 3 now displays a "Shipping Options" section
- Radio buttons for each available UPS service
- Shows service name, estimated delivery time, and cost
- Auto-selects the cheapest option by default
- Services sorted by cost (ascending)

## Workflow

### User Journey
1. **Step 1:** User uploads STL file
2. **Step 2:** User configures order (material, quantity, etc.) and enters delivery ZIP
3. **Step 3 (NEW):** 
   - Cost is calculated
   - Shipping rates are fetched based on ZIP code, weight, and dimensions
   - User sees available UPS services with prices and delivery times
   - User selects preferred shipping service
   - User completes checkout with selected service

### Technical Flow
```
User enters ZIP code in Step 2
    ↓
User clicks "Calculate Price"
    ↓
calculatePrice() is called
    ↓
POST /api/quote (gets material cost + base quote)
    ↓
fetchShippingRates() is called automatically
    ↓
POST /api/shipping-rates (gets UPS rates)
    ↓
setStep(3) - shows review with shipping options
    ↓
User selects shipping service (radio button)
    ↓
proceedToCheckout() is called
    ↓
shipping_service_code and shipping_service_name included in checkout request
    ↓
CREATE LABEL with selected service type
```

## Service Codes Reference

| Code | Service Name | Notes |
|------|-------------|-------|
| 01 | UPS Next Day Air | 1 business day delivery |
| 02 | UPS 2nd Day Air | 2 business day delivery |
| 03 | UPS Ground | 5-7 business day delivery |
| Other | Various international/special services | May appear for certain routes |

## Configuration

### Required Environment Variables
These must already be set:
- `UPS_CLIENT_ID` - OAuth client ID from UPS Developer Portal
- `UPS_CLIENT_SECRET` - OAuth client secret
- `UPS_ACCOUNT_NUMBER` - UPS account number for billing
- `UPS_ENVIRONMENT` - "cie" (test) or "production"

### Optional Environment Variables
- `SHIPPER_ZIP_CODE` - Origin ZIP code (defaults to "21093" if not set)

## Error Handling

### Graceful Degradation
If shipping rates fail to load:
- Quote calculation still completes
- No shipping options displayed
- Proceeds with default shipping method ("UPS Ground" / code "03")
- User can still complete checkout

### Error Messages
- **UNCONFIGURED** - UPS credentials not set
- **AUTH_ERROR** - OAuth token fetch failed
- **API_ERROR** - UPS Rating API error
- **RATE_LIMIT** - Hit UPS API rate limit (retry after short delay)
- **TIMEOUT** - Request took too long (15s timeout)
- **REQUEST_ERROR** - Network or parsing error

## Future Enhancements

1. **Price Adjustments** - Add shipping cost to total quote price
2. **Negotiated Rates** - Use negotiated rate pricing if available
3. **Insurance Options** - Show insurance costs per service
4. **Delivery Guarantees** - Display UPS guaranteed delivery information
5. **International Shipping** - Extend to non-US destinations
6. **Multi-Package Support** - Handle large orders split across multiple packages

## Testing

### Test Cases
1. **Valid ZIP Code** - Should display 2-3 service options
2. **Alaska/Hawaii** - May have limited or higher-cost options
3. **Invalid ZIP** - Should handle gracefully, skip rates
4. **No Selection** - Should pre-select cheapest option
5. **Network Failure** - Should allow checkout without rates

### Example Test Request
```bash
curl -X POST http://localhost:8003/api/shipping-rates \
  -H "Content-Type: application/json" \
  -d '{
    "zip_code": "90210",
    "weight": 1.5,
    "length": 6,
    "width": 4,
    "height": 3
  }'
```

## Files Modified
- `api/ups_service.py` - Added `get_shipping_rates()` method
- `api/quote.py` - Added `/api/shipping-rates` endpoint and models
- `static/App.jsx` - Added shipping selection UI and logic

## Notes
- Rates are fetched fresh each time the user reaches Step 3
- Rates are based on weight and package dimensions
- Actual rates may vary based on UPS negotiated contracts
- Delivery times are estimates; UPS doesn't guarantee dates without signature
