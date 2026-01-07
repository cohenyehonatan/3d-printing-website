# Quick Reference: UPS Rating API Integration

## Files Changed

```
api/
  ├── ups_service.py         [MODIFIED] Added get_shipping_rates() method
  └── quote.py               [MODIFIED] Added /api/shipping-rates endpoint
static/
  └── App.jsx                [MODIFIED] Added shipping options UI to Step 3
RATING_API_SUMMARY.md        [NEW] Executive summary
RATING_API_IMPLEMENTATION.md [NEW] Detailed technical docs
```

## What Customers See

**Before:** Fixed shipping cost in quote
**After:** Choice of 3 UPS services with different costs and delivery times

```
Shipping Options
───────────────────────────────────────
○ UPS Ground          5 business days  $8.50
● UPS 2nd Day Air    2 business days  $15.99  ← Auto-selected
○ UPS Next Day Air   1 business day   $28.50
```

## Key Code Changes

### Backend: `api/ups_service.py`
```python
# New method in UPSService class
async def get_shipping_rates(
    self,
    from_zip: str,
    from_city: str,
    from_state: str,
    to_zip: str,
    to_city: str,
    to_state: str,
    weight_lbs: float,
    length_in: float = 5,
    width_in: float = 5,
    height_in: float = 5,
    get_all_services: bool = True
) -> Dict[str, Any]
```

### API: `api/quote.py`
```python
# New endpoint
@app.post('/api/shipping-rates', response_model=ShippingRatesResponse)
async def get_shipping_rates(request_data: ShippingRatesRequest)

# New models
class ShippingRatesRequest
class ShippingRateOption
class ShippingRatesResponse
```

### Frontend: `static/App.jsx`
```javascript
// New state
const [shippingRates, setShippingRates] = useState([])
const [selectedShippingService, setSelectedShippingService] = useState(null)
const [loadingRates, setLoadingRates] = useState(false)

// New function
const fetchShippingRates = async (weight) => { ... }

// Updated function
const proceedToCheckout = async () => {
  // Now includes shipping_service_code and shipping_service_name
}

// New UI section in Step 3
<div className="bg-blue-50 p-4 rounded-lg border-2 border-blue-300">
  <h3 className="font-semibold mb-3 text-gray-700">Shipping Options</h3>
  {/* Radio buttons for each rate option */}
</div>
```

## API Endpoints

### New: POST `/api/shipping-rates`
Get available UPS services for a ZIP code and weight

**Request:**
```json
{
  "zip_code": "10001",
  "weight": 0.5,
  "length": 5,
  "width": 5,
  "height": 5
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
    }
    // ... more rates
  ],
  "weight": 0.5,
  "origin": "Timonium, MD 21093",
  "destination": "New York, NY 10001"
}
```

## Integration Points

1. **Quote Calculation** → Auto-fetch rates when moving to Step 3
2. **Checkout Data** → Include selected service in payment request
3. **Label Creation** → Use selected service code (01/02/03) for label

## Testing

```bash
# Test the endpoint directly
curl -X POST http://localhost:8003/api/shipping-rates \
  -H "Content-Type: application/json" \
  -d '{
    "zip_code": "10001",
    "weight": 1.0,
    "length": 5,
    "width": 5,
    "height": 5
  }'
```

## Service Codes

- `01` = UPS Next Day Air (1 day)
- `02` = UPS 2nd Day Air (2 days)
- `03` = UPS Ground (5-7 days)

## Error Cases

| Case | Behavior |
|------|----------|
| Invalid ZIP | Return error, skip rates |
| Network down | Proceed with default shipping |
| Rate limit hit | Retry automatically |
| Auth failure | Log error, use fallback |

## Configuration

Uses existing UPS env vars. No new setup required!

```
UPS_CLIENT_ID          ← Already configured
UPS_CLIENT_SECRET      ← Already configured
UPS_ACCOUNT_NUMBER     ← Already configured
UPS_ENVIRONMENT        ← Already configured
SHIPPER_ZIP_CODE       ← Optional, defaults to 21093
```

## Performance

- **Rates fetched:** When entering Step 3 checkout
- **Cache:** OAuth token cached with auto-refresh
- **Timeout:** 15 seconds per request
- **Fallback:** Works without rates if API fails

## Approved APIs Used

✅ Rating API - Get shipping rates
✅ Address Validation - Validate addresses
✅ Tracking - Track shipments
✅ Shipping - Create labels
✅ OAuth Authorization - Token management

**Not used:** USPS APIs (kept as backup)

---

**See `RATING_API_IMPLEMENTATION.md` for full technical details**
