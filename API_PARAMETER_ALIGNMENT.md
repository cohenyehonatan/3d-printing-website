# API Parameter Alignment Guide

## Overview
This document maps all frontend query parameters and request bodies to backend database schema to ensure seamless data flow from frontend → API → database → Stripe.

## Database Schema Reference

### Core Models
- **Customer**: id, name, email, phone, stripe_customer_id, gdpr_consent, marketing_opt_in
- **Material**: id, name, density_g_per_cm3, price_per_kg, is_active
- **PrintOrder**: id, order_number, material_id, customer_id, quantity, volume_cm3, weight_g, delivery_zip_code, delivery_address, total_cents, payment_status, order_status, rush_order, model_filename, scheduled_print_date, completion_date, special_instructions
- **PrintJob**: print_order_id, status (queued/printing/completed/failed), printer_name, progress_percent, estimated_duration_minutes
- **Invoice**: id, print_order_id, invoice_number, work_performed, subtotal, tax, total, total_cents, stripe_invoice_id, pdf_generated, invoice_date

---

## API Endpoints

### 1. POST /api/quote
**Purpose**: Calculate print quote based on customer inputs

**Frontend Request (App.jsx)**:
```javascript
const quoteData = {
  zip_code: selections.zip_code,
  filament_type: selections.material,  // Material name (e.g., "PLA Basic")
  quantity: selections.quantity,        // Quantity in units
  rush_order: selections.rush_order,    // Boolean for rush surcharge
  use_usps_connect_local: false,        // Shipping option
  volume: modelStats.volume,            // STL parser output in cm³
  weight: modelStats.weight             // Calculated from volume + material density
};
```

**Backend Handler** (`api/quote.py`):
```python
class QuoteRequest(BaseModel):
    zip_code: str
    filament_type: str              # Map to Material.name lookup
    quantity: int
    rush_order: bool
    use_usps_connect_local: bool
    volume: float                   # Will become PrintOrder.volume_cm3
    weight: float                   # Will become PrintOrder.weight_g
```

**Database Mapping**:
| Frontend Param | Request Field | Database Column (PrintOrder) | Notes |
|---|---|---|---|
| zip_code | zip_code | delivery_zip_code | For tax & shipping calculation |
| filament_type | filament_type | material_id | Lookup Material by name |
| quantity | quantity | quantity | Units to print |
| volume | volume | volume_cm3 | From STL parser |
| weight | weight | weight_g | Calculated or parsed |
| rush_order | rush_order | rush_order | Boolean flag |

**Response** (`QuoteResponse`):
```python
{
  "cost_breakdown": {
    "material_cost": float,
    "shipping_cost": float,
    "tax": float,
    "total": float
  },
  "formatted": {
    "material": "$X.XX",
    "shipping": "$X.XX",
    "tax": "$X.XX",
    "total": "$X.XX"
  },
  "delivery_estimate": "3-5 business days"
}
```

---

### 2. POST /api/checkout
**Purpose**: Process customer checkout and create Stripe payment link

**Frontend Request (App.jsx)**:
```javascript
const checkoutData = {
  email: selections.email,           // Customer.email
  name: selections.name,             // Customer.name
  phone: selections.phone,           // Customer.phone
  zip_code: selections.zip_code,     // PrintOrder.delivery_zip_code
  filament_type: selections.material, // Material lookup → material_id
  quantity: selections.quantity,     // PrintOrder.quantity
  rush_order: selections.rush_order, // PrintOrder.rush_order
  volume: modelStats.volume,         // PrintOrder.volume_cm3
  weight: modelStats.weight,         // PrintOrder.weight_g
  model_file: File object            // → PrintOrder.model_filename
};
```

**Backend Handler** (`api/quote.py`):
```python
class CheckoutRequest(BaseModel):
    email: str
    name: str
    phone: str
    zip_code: str
    filament_type: str
    quantity: int
    rush_order: bool
    volume: float
    weight: float
    model_file: Optional[str]  # Optional, can come from file upload
```

**Internal Processing**:
1. **Create/fetch Customer**:
   - lookup/create with: email, name, phone
   - generate/get stripe_customer_id
   
2. **Lookup Material**:
   - filament_type → Material.name
   - get material_id
   
3. **Create TempPrintOrder** (temporary object for Stripe):
   ```python
   TempPrintOrder(
       order_number="0",           # Will be generated on actual creation
       material_id=material_id,
       customer_id=customer.id,
       quantity=quantity,
       volume_cm3=volume,
       weight_g=weight,
       delivery_zip_code=zip_code,
       delivery_address="",        # Not provided in checkout
       total_cents=calculated_total,
       rush_order=rush_order,
       model_filename=extract_filename(model_file),
       payment_status="pending",
       order_status="draft"
   )
   ```

4. **Create Stripe Payment Link**:
   - Call `stripe_service.create_payment_link_for_order(temp_order, db_session, customer)`
   - Returns payment_url for frontend redirect
   
5. **Payment redirect** includes query parameters:
   ```
   /payment-success?order_id=X&customer_id=Y
   ```

**Response** (`CheckoutResponse`):
```python
{
  "payment_url": "https://pay.stripe.com/...",
  "total_amount_cents": 5000,    # In cents for Stripe
  "order_number": "ORDER-001",   # Preview, actual generated on payment success
  "message": "Proceeding to payment"
}
```

---

### 3. GET /api/order-details
**Purpose**: Retrieve order confirmation after Stripe payment redirect

**Frontend Call** (PaymentSuccess.jsx):
```javascript
// Extract from URL parameters
const urlParams = new URLSearchParams(window.location.search);
const order_id = urlParams.get('order_id');      // PrintOrder.id
const customer_id = urlParams.get('customer_id'); // Customer.id

// Call endpoint
fetch(`/api/order-details?order_id=${order_id}&customer_id=${customer_id}`)
```

**Backend Handler** (`api/quote.py`):
```python
@app.get('/api/order-details')
async def get_order_details(
    order_id: Optional[str] = None,      # Can be "None" string from frontend
    customer_id: Optional[str] = None    # Can be "None" string from frontend
):
    # Safe conversion (handles "None" string literal)
    order_id = int(order_id) if order_id and order_id != "None" else None
    customer_id = int(customer_id) if customer_id and customer_id != "None" else None
    
    # Lookup or return generic success
    if order_id and customer_id:
        order = db.query(PrintOrder).filter(
            PrintOrder.id == order_id,
            PrintOrder.customer_id == customer_id
        ).first()
```

**Database Mapping**:
| URL Parameter | Database Column | Related Model | Purpose |
|---|---|---|---|
| order_id | PrintOrder.id | PrintOrder | Identify order |
| customer_id | Customer.id (FK) | Customer | Verify ownership |

**Response**:
```python
{
  "status": "success",
  "message": "Your order has been confirmed. Check your email for details.",
  "order_id": 123,
  "customer_id": 456,
  "estimated_delivery": "3-5 business days",
  "order_number": "ORDER-001"  # Optional if available
}
```

---

### 4. POST /api/verify-file (Server-side STL validation)

**Frontend Request** (App.jsx):
```javascript
const formData = new FormData();
formData.append('file', modelFile);  // STL file object

fetch('/api/verify-file', {
  method: 'POST',
  body: formData
})
```

**Backend Handler** (`api/quote.py`):
```python
@app.post('/api/verify-file')
async def verify_file(file: UploadFile = File(...)):
    # Validates STL structure
    # Returns volume_cm3, weight_g based on trimesh parsing
```

**Response** (`VerifyFileResponse`):
```python
{
  "valid": bool,
  "volume_cm3": float,
  "weight_g": float,
  "error": Optional[str]
}
```

---

## Stripe Metadata Flow

### Payment Link Metadata (create_payment_link_for_order)
All metadata synchronized to Stripe for dashboard visibility:

```python
product_metadata = {
    "order_id": PrintOrder.id,
    "order_number": PrintOrder.order_number,
    "customer_id": Customer.id,
    "payment_type": "order_payment",
    "material": Material.name,
    "quantity": PrintOrder.quantity,
    "rush_order": PrintOrder.rush_order,
    "volume_cm3": PrintOrder.volume_cm3,
    "weight_g": PrintOrder.weight_g,
    "customer_name": Customer.name,
    "customer_email": Customer.email,
    "customer_phone": Customer.phone,
}

link_metadata = {
    "order_id": PrintOrder.id,
    "order_number": PrintOrder.order_number,
    "customer_id": Customer.id,
    "payment_type": "order_payment",
    "material": Material.name,
    "amount_cents": PrintOrder.total_cents,
}

payment_intent_data = {
    "metadata": {
        "order_id": PrintOrder.id,
        "order_number": PrintOrder.order_number,
        "customer_id": Customer.id,
        "payment_type": "order_payment",
        "material": Material.name,
        "delivery_zip": PrintOrder.delivery_zip_code,
        "scheduled_date": PrintOrder.scheduled_print_date,
    }
}
```

### Redirect URL Parameters
After payment completes, Stripe redirects to:
```
/payment-success?order_id={PrintOrder.id}&customer_id={Customer.id}
```

These parameters are:
- Passed to `/api/order-details` endpoint
- Used to fetch order confirmation
- Displayed in PaymentSuccess component

---

## Parameter Name Standardization

### Key Naming Conventions

| Purpose | Frontend Var | API Param | Database Column | Stripe Metadata |
|---|---|---|---|---|
| Print Order | order_number* | order_id | PrintOrder.id | order_id |
| Customer ID | (implicit) | customer_id | Customer.id | customer_id |
| Material | filament_type | filament_type | Material.name (lookup) | material |
| Quantity | quantity | quantity | PrintOrder.quantity | quantity |
| Weight | weight | weight | PrintOrder.weight_g | weight_g |
| Volume | volume | volume | PrintOrder.volume_cm3 | volume_cm3 |
| Zip Code | zip_code | zip_code | PrintOrder.delivery_zip_code | delivery_zip |
| Rush Order | rush_order | rush_order | PrintOrder.rush_order | rush_order |

*Note: Frontend uses `order_number` for display; backend uses `order_id` (database PK) and `order_number` (human-readable reference)

---

## Data Flow Diagrams

### Quote Flow
```
App.jsx (step 2)
  ↓
  calculatePrice()
  ↓
POST /api/quote {filament_type, quantity, zip_code, volume, weight, ...}
  ↓
quote.py (calculate_price)
  • Material lookup: filament_type → Material.name
  • Create QuoteRequest with all fields
  • Calculate costs (material, shipping, tax)
  ↓
QuoteResponse {cost_breakdown, formatted, delivery_estimate}
  ↓
App.jsx (display quote, move to step 3)
```

### Checkout Flow
```
App.jsx (step 3)
  ↓
  proceedToCheckout()
  ↓
POST /api/checkout {email, name, phone, filament_type, quantity, zip_code, volume, weight, ...}
  ↓
quote.py (checkout_handler)
  • Create/fetch Customer {email, name, phone}
  • Material lookup: filament_type → Material.id
  • Create TempPrintOrder {material_id, customer_id, quantity, volume_cm3, weight_g, delivery_zip_code, rush_order, ...}
  • Call stripe_service.create_payment_link_for_order(temp_order)
  ↓
Stripe API (create Payment Link)
  • Sync metadata: {order_id, order_number, material, quantity, volume_cm3, weight_g, ...}
  ↓
CheckoutResponse {payment_url, total_amount_cents}
  ↓
App.jsx
  window.location.href = payment_url (redirect to Stripe)
```

### Payment Success Flow
```
Stripe Payment Link (after payment)
  ↓
  Redirect: /payment-success?order_id=X&customer_id=Y
  ↓
PaymentSuccess.jsx
  • Extract order_id and customer_id from URL
  ↓
GET /api/order-details?order_id=X&customer_id=Y
  ↓
quote.py (get_order_details)
  • Convert "None" strings to None
  • Lookup PrintOrder {id=X, customer_id=Y}
  • Fetch related data
  ↓
OrderDetails {status, message, order_id, customer_id, estimated_delivery, ...}
  ↓
PaymentSuccess.jsx (display confirmation)
```

---

## Implementation Checklist

### Frontend (App.jsx, PaymentSuccess.jsx)
- [x] Use correct parameter names in POST /api/quote
- [x] Use correct parameter names in POST /api/checkout
- [x] Extract order_id and customer_id from URL in PaymentSuccess.jsx
- [x] Call /api/order-details with correct query parameters
- [x] Map filament_type correctly to Material lookup

### Backend (api/quote.py)
- [x] QuoteRequest validates all incoming parameters
- [x] CheckoutRequest validates all incoming parameters
- [x] /api/checkout creates Customer and TempPrintOrder correctly
- [x] /api/order-details handles Optional[str] parameters safely
- [x] All responses use consistent field names

### Stripe Integration (api/stripe_service.py)
- [x] create_payment_link_for_order uses PrintOrder fields
- [x] create_payment_link_for_invoice uses PrintOrder fields
- [x] create_stripe_invoice_from_pdf uses PrintOrder fields
- [x] process_stripe_refund uses PrintOrder fields
- [x] All metadata keys use new names (order_id, material, volume_cm3, etc.)
- [x] Redirect URLs use order_id not booking_id

### Database (api/models.py)
- [x] PrintOrder schema has all required fields
- [x] Material schema complete
- [x] Customer schema includes stripe_customer_id
- [x] Invoice schema references PrintOrder correctly

---

## Testing Checklist

1. **Quote calculation**:
   - POST /api/quote with valid parameters
   - Verify cost breakdown is correct
   - Test with different materials, quantities, zip codes

2. **Checkout flow**:
   - POST /api/checkout creates Stripe Payment Link
   - Verify metadata in Stripe dashboard
   - Verify redirect URL has order_id and customer_id

3. **Order confirmation**:
   - GET /api/order-details with valid order_id and customer_id
   - Verify returns correct order information
   - Test with missing/invalid IDs

4. **End-to-end**:
   - Upload STL file
   - Calculate quote
   - Proceed to checkout
   - Complete Stripe payment
   - Verify payment success page shows correct order details
   - Verify database has PrintOrder and Customer records

---

## Migration Notes

If migrating from old Booking system:
1. Create Customer records from existing customers
2. Create PrintOrder records from Booking records
3. Map service_type → Material.name
4. Map service_address → delivery_address
5. Extract zip code from service_address → delivery_zip_code
6. Create Material records if needed
7. Update any stored Stripe Payment Intent references

---

## Notes

- **order_id**: Always refers to `PrintOrder.id` (database primary key)
- **order_number**: Human-readable order reference (`PrintOrder.order_number`)
- **customer_id**: Refers to `Customer.id` (database primary key)
- **filament_type**: Frontend name for material; backend must lookup `Material.name` to get `material_id`
- **None handling**: /api/order-details must handle URL parameters that come as string "None" literal
- **Stripe customer**: Created automatically when Customer is created; stored in `Customer.stripe_customer_id`
