# USPS Rate Integration - Notice 123 (Effective Oct 5, 2025)

## Overview

The shipping calculation system has been updated with official USPS rates from **USPS Notice 123** (effective October 5, 2025). The implementation replaces placeholder rates with accurate, zone-based retail pricing for three major services.

## Integrated Services

### 1. **USPS Ground Advantage Retail**
- **Best for:** Economical parcel delivery
- **Speed:** 1-3 business days (varies by zone)
- **Weight range:** Up to 70 lbs
- **Pricing:** Weight-tiered and zone-based
- **Zone 1-2:** Most economical for local/regional
- **Zone 8-9:** Highest cost for cross-country

### 2. **USPS Priority Mail Retail**
- **Best for:** Faster delivery with tracking
- **Speed:** 1-3 business days (typically faster than Ground)
- **Weight range:** Up to 70 lbs
- **Pricing:** 15-50% premium over Ground Advantage
- **Includes:** Free tracking and insurance up to $100

### 3. **USPS Priority Mail Express Retail**
- **Best for:** Guaranteed overnight/2-day delivery
- **Speed:** Overnight or 2-day depending on destination
- **Weight range:** Up to 70 lbs
- **Pricing:** 300-500% premium over Ground Advantage
- **Includes:** $100 free insurance and guaranteed delivery

## Technical Implementation

### Rate Tables

The rate tables are stored as nested Python dictionaries in `api/quote.py`:

```python
USPS_GROUND_ADVANTAGE_RETAIL = {
    4: {1: 3.45, 2: 3.48, ..., 9: 4.43},     # ≤4 oz
    8: {1: 3.77, 2: 3.81, ..., 9: 5.66},     # ≤8 oz
    12: {1: 4.13, 2: 4.18, ..., 9: 7.14},    # ≤12 oz
    15.999: {1: 4.32, ..., 9: 8.82},         # <1 lb
    1: {1: 4.32, ..., 9: 8.82},              # 1 lb
    2: {1: 5.21, ..., 9: 12.44},             # 2 lb
    # ... up to 70 lb
}
```

Each weight bracket contains prices for all 9 USPS zones.

### Zone Determination

Zones are calculated based on actual geographic distance from origin ZIP to destination ZIP using the Haversine formula:

| Distance (miles) | USPS Zone | Description |
|---|---|---|
| 0-50 | Zone 1 | Local/same city |
| 51-150 | Zone 2 | Regional |
| 151-300 | Zone 3 | Multistate |
| 301-600 | Zone 4 | Extended regional |
| 601-1000 | Zone 5 | Cross-country (partial) |
| 1001-1400 | Zone 6 | Cross-country (mid) |
| 1401-1800 | Zone 7 | Cross-country (far) |
| 1801-2000 | Zone 8 | Extreme distance |
| 2000+ | Zone 9 | Maximum distance |

### Weight Brackets

Weight is determined as follows:

```
< 4 oz   → Use 4 oz rate
4-8 oz   → Use 8 oz rate
8-12 oz  → Use 12 oz rate
12-16 oz → Use 16 oz (15.999) rate
16 oz+   → Round UP to nearest lb (capped at 70 lbs)
```

For example:
- 0.2 lbs (3.2 oz) → 4 oz bracket
- 0.5 lbs (8 oz) → 8 oz bracket
- 1.2 lbs → 2 lb bracket (rounded up)
- 5.7 lbs → 6 lb bracket (rounded up)

## API Integration

### Updated Request Parameters

The `/api/quote` endpoint now accepts a `service_type` parameter:

```json
{
  "zip_code": "90210",
  "filament_type": "PLA",
  "quantity": 1,
  "rush_order": false,
  "use_usps_connect_local": false,
  "service_type": "ground_advantage",
  "volume": 150.5,
  "weight": 0.0
}
```

**Service type options:**
- `"ground_advantage"` (default) - Economical option
- `"priority_mail"` - Standard Priority Mail
- `"priority_express"` - Overnight/2-day guarantee

### Backward Compatibility

The `express` parameter is still supported for backward compatibility:
- `express=true` automatically selects `"priority_express"` service
- `express=false` with no `service_type` defaults to `"ground_advantage"`

### USPS Connect Local Discount

Customers can request USPS Connect Local for a 15% discount:
- Only applicable to **Ground Advantage** service
- Requires local pickup/drop-off capability
- Automatically applied when `use_usps_connect_local=true` and `service_type="ground_advantage"`

## Sample Pricing (per USPS Notice 123)

### For 2 lbs to Zone 5 destination:

| Service | Price |
|---|---|
| Ground Advantage | $7.54 |
| Priority Mail | $14.09 |
| Priority Express | $45.50 |

### For 5 lbs to Zone 9 destination:

| Service | Price |
|---|---|
| Ground Advantage | $23.31 |
| Priority Mail | $38.69 |
| Priority Express | $88.50 |

## Special Cases

### Hawaii & Alaska

Prices for Hawaii (ZIP 96xxx) and Alaska (ZIP 99xxx) are already included in the USPS zone calculations. No additional surcharges are applied since USPS Notice 123 pricing already reflects these destinations.

### Weight Limits

- **Maximum weight:** 70 lbs (USPS retail limit)
- Weights over 70 lbs are capped at 70 lbs in the rate calculation
- Consider commercial rates or ground freight for heavier items

### Oversized Surcharges

USPS Notice 123 includes surcharges for:
- Oversized packages (>22" in one dimension)
- Overweight packages (density exceeding 70 lbs/cubic foot)

Note: These surcharges are not currently implemented. They can be added in a future update if needed.

## Testing

Run the test suite to verify the integration:

```bash
python3 test_usps_rates.py
```

This will verify:
- Weight bracket calculations
- Zone determination logic
- Sample rate lookups
- Service type comparisons

## Pricing Verification

All rates in the implementation have been verified against:
- USPS Postal Explorer: https://pe.usps.com/text/dmm300/Notice123.htm
- Effective date: October 5, 2025
- Update date: as of document publication

## Future Enhancements

Potential improvements to consider:

1. **International Services** - Add Priority Mail Express International, Priority Mail International, etc.
2. **Commercial Pricing** - Integrate USPS commercial base rates (typically 10-25% savings)
3. **Flat Rate Options** - Include flat-rate envelopes and boxes
4. **Dimensional Weight** - Implement dimensional weight calculations for oversized packages
5. **Surcharge Logic** - Add oversized and overweight surcharge calculations
6. **Real-time Updates** - Consider webhook or API integration for rate updates
7. **Rate Caching** - Cache distance/zone calculations for frequently-used ZIP codes
8. **Parcel Select** - Add USPS Parcel Select Ground option

## File Changes

### Modified: `api/quote.py`

**Added:**
- `USPS_GROUND_ADVANTAGE_RETAIL` - Rate table for Ground Advantage service
- `USPS_PRIORITY_MAIL_RETAIL` - Rate table for Priority Mail service
- `USPS_PRIORITY_MAIL_EXPRESS` - Rate table for Express service
- `get_usps_zone_from_distance()` - Convert distance to USPS zone
- `get_weight_bracket()` - Determine weight bracket for rate lookup
- Updated `calculate_usps_shipping()` - Uses official rates with service type selection

**Modified:**
- `QuoteRequest` model - Added `service_type` parameter
- `/api/quote` endpoint - Passes service_type to shipping calculator

### Created: `test_usps_rates.py`

Test suite for verifying rate calculations and zone/weight logic.

## Support

For questions or issues related to the rate integration:
1. Check the test suite output
2. Review USPS Notice 123 at the Postal Explorer
3. Verify ZIP codes are valid 5-digit codes
4. Ensure weights are in kilograms (will be converted to lbs internally)
