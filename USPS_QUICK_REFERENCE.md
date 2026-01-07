# USPS Rate Integration - Quick Reference Card

## ⚡ Quick Start

```python
# Basic usage
from api.quote import calculate_usps_shipping

cost = calculate_usps_shipping(
    zip_code='90210',      # Destination ZIP
    weight_kg=1.5,         # Weight in kilograms
    service_type='ground_advantage'  # or 'priority_mail', 'priority_express'
)
print(f"Shipping: ${cost:.2f}")
```

## 📍 Zone Map

| Zone | Distance | Description | Example |
|---|---|---|---|
| 1 | 0-50 mi | Local/same city | Same metro area |
| 2 | 51-150 mi | Regional | Neighboring state |
| 3 | 151-300 mi | Multistate | Midwest route |
| 4 | 301-600 mi | Extended | Cross-region |
| 5 | 601-1000 mi | Far | Cross-country (partial) |
| 6 | 1001-1400 mi | Very far | Cross-country (mid) |
| 7 | 1401-1800 mi | Very far | Cross-country (far) |
| 8 | 1801-2000 mi | Extreme | West coast |
| 9 | 2000+ mi | Maximum | Hawaii/Alaska |

## ⚖️ Weight Brackets

| Weight Range | Bracket Used | Examples |
|---|---|---|
| < 4 oz | 4 oz | 0.1, 0.2, 0.25 lbs |
| 4-8 oz | 8 oz | 0.3, 0.4, 0.5 lbs |
| 8-12 oz | 12 oz | 0.6, 0.7 lbs |
| 12-16 oz | 16 oz (15.999) | 0.8, 0.9 lbs |
| 1+ lbs | Rounded up | 1.2→2, 2.5→3, 5.7→6 lbs |
| Max | 70 lbs | (70.5 → 70) |

## 💰 Service Types

```json
{
  "ground_advantage": {
    "speed": "1-3 business days",
    "tracking": "Yes",
    "insurance": "Included to $100",
    "cost": "Lowest",
    "discounts": "15% with USPS Connect Local"
  },
  "priority_mail": {
    "speed": "1-3 business days (faster)",
    "tracking": "Yes",
    "insurance": "Included to $100",
    "cost": "15-50% more",
    "discounts": "None standard"
  },
  "priority_express": {
    "speed": "Overnight/2-day",
    "tracking": "Yes",
    "insurance": "$100 included",
    "cost": "300-500% more",
    "discounts": "None standard"
  }
}
```

## 📋 API Request Format

```json
POST /api/quote
{
  "zip_code": "90210",
  "filament_type": "PLA|PETG|ABS|TPU|Nylon",
  "quantity": 1,
  "service_type": "ground_advantage",
  "volume": 150.5,
  "weight": 0,
  "rush_order": false,
  "use_usps_connect_local": false
}
```

## 📊 Response Format

```json
{
  "total_cost_with_tax": "$245.65",
  "sales_tax": "$19.87",
  "base_cost": "$50.00",
  "material_cost": "$150.00",
  "shipping_cost": "$25.78",
  "rush_order_surcharge": "$0.00"
}
```

## 💡 Common Scenarios

### Scenario 1: Budget Option (PLA to California)
```json
{
  "zip_code": "90210",
  "filament_type": "PLA",
  "quantity": 1,
  "service_type": "ground_advantage",
  "volume": 100
}
// Estimated shipping: $15-25 depending on weight
```

### Scenario 2: Fast Delivery (TPU to New York)
```json
{
  "zip_code": "10001",
  "filament_type": "TPU",
  "quantity": 2,
  "service_type": "priority_express",
  "volume": 200,
  "rush_order": true
}
// Estimated shipping: $40-60 + $20 rush surcharge
```

### Scenario 3: Discounted Local (ABS to Texas)
```json
{
  "zip_code": "78201",
  "filament_type": "ABS",
  "quantity": 1,
  "service_type": "ground_advantage",
  "volume": 150,
  "use_usps_connect_local": true
}
// 15% discount applied automatically
```

### Scenario 4: Hawaii Delivery
```json
{
  "zip_code": "96801",
  "filament_type": "PLA",
  "quantity": 1,
  "service_type": "ground_advantage",
  "volume": 100
}
// Automatically Zone 9 (highest rate)
```

## 🔍 Lookup Table Examples

### Ground Advantage - Zone 5 (600-1000 miles)
```
4 oz:   $3.74
8 oz:   $4.35
12 oz:  $5.05
1 lb:   $5.69
2 lbs:  $7.54
3 lbs:  $9.39
5 lbs:  $13.09
```

### Priority Mail - Zone 5
```
4 oz:   $7.13
8 oz:   $8.68
12 oz:  $10.32
1 lb:   $11.96
2 lbs:  $14.09
3 lbs:  $16.22
5 lbs:  $20.48
```

### Priority Express - Zone 5
```
4 oz:   $35.70
8 oz:   $36.35
12 oz:  $39.65
1 lb:   $41.90
2 lbs:  $45.50
3 lbs:  $48.75
5 lbs:  $55.00
```

## ✅ Validation Checklist

- [ ] ZIP code is 5 digits
- [ ] Weight is in kilograms
- [ ] Service type is valid (ground_advantage|priority_mail|priority_express)
- [ ] Volume measurement is accurate
- [ ] Zone is between 1-9
- [ ] Weight is between 0-70 lbs
- [ ] Filament type is recognized
- [ ] Response includes all 6 cost fields

## 🚀 Implementation Functions

### Main Function
```python
calculate_usps_shipping(
    zip_code: str,
    weight_kg: float,
    service_type: str = "ground_advantage",
    express: bool = False,  # Legacy support
    connect_local: bool = False
) -> float
```

### Helper Functions
```python
get_usps_zone_from_distance(distance_miles: float) -> int
get_weight_bracket(weight_lbs: float) -> tuple
```

### Rate Tables
```python
USPS_GROUND_ADVANTAGE_RETAIL = {...}
USPS_PRIORITY_MAIL_RETAIL = {...}
USPS_PRIORITY_MAIL_EXPRESS = {...}
```

## 📱 cURL Examples

### Ground Advantage
```bash
curl -X POST http://localhost:8003/api/quote \
  -H "Content-Type: application/json" \
  -d '{
    "zip_code":"90210",
    "filament_type":"PLA",
    "service_type":"ground_advantage",
    "volume":150
  }'
```

### Priority Express
```bash
curl -X POST http://localhost:8003/api/quote \
  -H "Content-Type: application/json" \
  -d '{
    "zip_code":"02101",
    "filament_type":"ABS",
    "service_type":"priority_express",
    "volume":100,
    "rush_order":true
  }'
```

## ⚠️ Edge Cases

| Scenario | Handling |
|---|---|
| ZIP not found | Default to 500 mi (Zone 5) |
| Weight > 70 lbs | Capped at 70 lbs |
| Weight < 0.1 oz | Set to 4 oz bracket |
| Hawaii (96xxx) | Assigned to Zone 9 |
| Alaska (99xxx) | Assigned to Zone 9 |
| Rate missing | Fallback to Zone 1 equivalent |

## 📈 Cost Examples

### 2 lb Package by Service Type

**To Zone 1 (local):**
- Ground: $5.21 | Priority: $9.35 | Express: $37.00

**To Zone 5 (mid-distance):**
- Ground: $7.54 | Priority: $14.09 | Express: $45.50

**To Zone 9 (farthest):**
- Ground: $12.44 | Priority: $26.23 | Express: $70.50

### Savings with USPS Connect Local
- Ground Advantage with Connect Local: **15% off**
- Example: $7.54 → $6.41 (saves $1.13)

## 🔗 Documentation Links

- **Main Docs**: `USPS_RATE_INTEGRATION.md`
- **Summary**: `USPS_INTEGRATION_SUMMARY.md`
- **Examples**: `API_EXAMPLES_USPS.py`
- **Tests**: `test_usps_rates.py`
- **Complete**: `USPS_INTEGRATION_COMPLETE.txt`

## 🧪 Testing Command

```bash
python3 test_usps_rates.py
```

Verifies:
- ✓ Weight bracket calculations
- ✓ Zone determination
- ✓ Rate lookups
- ✓ Service comparisons

---

**Integration Status**: ✅ COMPLETE  
**Rate Source**: USPS Notice 123 (Oct 5, 2025)  
**Last Updated**: [Today's Date]  
**Version**: 1.0  
