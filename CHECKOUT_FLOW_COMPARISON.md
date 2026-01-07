# Checkout Flow: Before & After

## BEFORE Integration

```
Step 1: Upload STL
         ↓
Step 2: Configure (Material, Qty, ZIP)
         ↓
Step 3: Review
   ├─ Base Cost: $20
   ├─ Material: $50
   ├─ Shipping: $12 (FIXED - calculated from ZIP)
   └─ Tax: $8.26
         ↓
Step 4: Enter Address
         ↓
Step 5: Stripe Payment
```

**Problem:** Customers had no choice in shipping speed - always same cost/time

---

## AFTER Integration (NEW!)

```
Step 1: Upload STL
         ↓
Step 2: Configure (Material, Qty, ZIP)
         ↓
Step 3: Review + Shipping Options ⭐ NEW
   ├─ Base Cost: $20
   ├─ Material: $50
   ├─ Shipping Options:
   │  ├─ ○ UPS Ground          5 days   $8.50
   │  ├─ ● UPS 2nd Day Air    2 days   $15.99  ← Auto-selected
   │  └─ ○ UPS Next Day Air   1 day    $28.50
   ├─ Tax: $8.26 (varies with selection)
   └─ [SHIP SELECTION UPDATES TOTAL]
         ↓
Step 4: Enter Address
         ↓
Step 5: Stripe Payment (with selected service)
```

**Benefit:** Customers choose speed vs. cost - increases conversion!

---

## Data Flow

### 1. User Enters ZIP and Clicks "Calculate Price"

```
Frontend: calculatePrice()
  ↓
POST /api/quote
  ├─ zip_code: "90210"
  ├─ filament_type: "PLA Basic"
  ├─ quantity: 1
  ├─ volume: 15.2 cm³
  └─ weight: 18.8g
  ↓
Backend: Calculates material + base cost
  ↓
Response: {base, material, shipping (old fixed), tax}
  ↓
Frontend: setQuote(response)
  ↓
Frontend: ALSO calls fetchShippingRates()
  ↓
POST /api/shipping-rates
  ├─ zip_code: "90210"
  ├─ weight: 0.041 lbs (18.8g converted)
  ├─ length: 5
  ├─ width: 5
  └─ height: 5
  ↓
Backend: UPS Rating API call
  POST https://onlinetools.ups.com/api/rating/v2409/Shop
  ├─ Shipper: Timonium, MD 21093
  ├─ Recipient: Beverly Hills, CA 90210
  ├─ Weight: 0.041 lbs
  └─ Package: 5x5x5 inches
  ↓
UPS Returns: [
  {service: "03 Ground", cost: 8.50, days: 5},
  {service: "02 2Day", cost: 15.99, days: 2},
  {service: "01 Overnight", cost: 28.50, days: 1}
]
  ↓
Backend: Response with rates sorted by cost
  ↓
Frontend: setShippingRates([...])
           setSelectedShippingService(rates[0])  ← cheapest
  ↓
Move to Step 3 → User sees all options
```

### 2. User Selects Shipping Service

```
Frontend: User clicks radio button
  ↓
setSelectedShippingService(rateObject)
  ↓
UI updates immediately with new cost
```

### 3. User Clicks "Proceed to Checkout"

```
Frontend: proceedToCheckout()
  ↓
Validates:
  ✓ Email & name entered
  ✓ Address complete
  ✓ Shipping service selected
  ↓
POST /api/checkout
  ├─ Contact info (email, name, phone)
  ├─ Shipping address (street, city, state, zip)
  ├─ Order details (filament, quantity, weight, volume)
  ├─ shipping_service_code: "02"  ⭐ NEW
  └─ shipping_service_name: "UPS 2nd Day Air"  ⭐ NEW
  ↓
Backend: Create Stripe checkout session
         Store selected shipping service with order
  ↓
Response: {payment_url: "https://stripe.com/..."}
  ↓
Frontend: window.location.href = payment_url
  ↓
User → Stripe Payment Page
```

### 4. After Payment Success

```
User → Stripe redirect with order_id
  ↓
Frontend: Load PaymentSuccess component
  ↓
Backend: Order marked as paid
         Stored shipping service is ready for label creation
  ↓
User: Sees shipping dashboard with tracking
```

---

## Example: Complete Transaction

**Customer: Jane Smith, Beverly Hills CA 90210**
**Order: 1x PLA Basic model, 18.8g**

### Backend Processing

```
1. calculatePrice() called
   └─ Material cost: 18.8g × $19.99/kg = $0.38
   └─ Base cost: $20
   └─ Total before shipping: $20.38

2. fetchShippingRates() called
   └─ Query UPS for 0.041 lbs to 90210
   └─ UPS responds with 3 services

3. User selects: "UPS 2nd Day Air" ($15.99)

4. proceedToCheckout() with selection
   └─ Subtotal: $20.38
   └─ Shipping: $15.99
   └─ Subtotal: $36.37
   └─ CA Tax (7.25%): $2.64
   └─ TOTAL: $39.01 ← User pays this

5. Order created in database:
   {
     order_id: "ORD-2026-001234",
     customer_email: "jane@example.com",
     shipping_address: "123 Rodeo Dr, Beverly Hills CA 90210",
     shipping_service_code: "02",
     shipping_service_name: "UPS 2nd Day Air",
     weight: 18.8,
     total: 39.01,
     status: "paid"
   }

6. Dashboard → Create Label:
   └─ Use shipping_service_code "02" for label creation
   └─ Creates 2-day UPS shipment
   └─ Jane receives tracking #1Z123ABC...
```

---

## Impact on Customer Experience

### Without Shipping Selection
> "My order costs $39 and will arrive in 5-7 days. Nothing I can do about it."

### With Shipping Selection
> "My order is $36.37 with ground shipping (5-7 days) OR I can upgrade to 2-day delivery for $15.99 more. Perfect for my Friday event!"

**Result:** Higher conversion, happier customers, more revenue ✨

---

## Technical Summary

| Component | Purpose | Status |
|-----------|---------|--------|
| `ups_service.get_shipping_rates()` | Fetch rates from UPS | ✅ Done |
| `POST /api/shipping-rates` | Expose rates to frontend | ✅ Done |
| Step 3 Shipping UI | Show rate options | ✅ Done |
| Checkout integration | Pass selection to payment | ✅ Done |
| Label creation | Use selected service code | ✅ Ready |

---

## Next: Integrate with Label Creation

To complete the loop, when creating a UPS label:

```python
# In your label creation flow:
selected_service = order.shipping_service_code  # "02"

await ups_service.create_label(
    from_zip="21093",
    to_zip="90210",
    weight_lbs=0.041,
    service_type=selected_service,  # ⭐ Use this!
    ...
)
```

The service code (`01`, `02`, `03`) determines:
- Delivery speed
- Cost to UPS
- Tracking updates available
- Insurance options

---

**Your customers now have real shipping choices! 🎉**
