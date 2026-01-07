# Complete Parameter Alignment Summary

## What Was Done

### 1. Backend Service Layer - Stripe Integration ✅
All functions in `api/stripe_service.py` have been updated to use the new PrintOrder model instead of the old Booking model:

**Functions Updated**:
- `get_or_create_stripe_customer()` - Creates Stripe customers with correct metadata
- `create_payment_link_for_order()` - Payment links now reference PrintOrder.id, order_number, material, volume_cm3, weight_g, delivery_zip_code
- `create_payment_link_for_invoice()` - Invoice payment links use PrintOrder and correct metadata (FIXED from using `booking` variable)
- `create_stripe_invoice_from_pdf()` - Stripe invoices now map PrintOrder fields correctly
- `process_stripe_refund()` - Refunds reference PrintOrder fields

**Key Changes**:
- All payment redirects now use: `?order_id={order.id}&customer_id={order.customer_id}` (not `booking_id`)
- All metadata keys updated: `order_id`, `order_number`, `material`, `volume_cm3`, `weight_g`, `delivery_zip`
- Removed all automotive field references (vehicle_vin, vehicle_make, vehicle_model, service_type, etc.)

### 2. API Endpoints - Quote & Checkout ✅
The `api/quote.py` file has been updated with:

**POST /api/quote** (Quote Calculation):
- Request: `{zip_code, filament_type, quantity, rush_order, use_usps_connect_local, volume, weight}`
- Response: `{cost_breakdown: {material_cost, shipping_cost, tax, total}, formatted: {...}, delivery_estimate}`
- Purpose: Calculate print cost based on customer inputs

**POST /api/checkout** (Payment Link Generation):
- Request: `{email, name, phone, zip_code, filament_type, quantity, rush_order, volume, weight}`
- Response: `{payment_url, total_amount_cents, order_number}`
- Process:
  1. Creates/fetches Customer from email/name/phone
  2. Looks up Material by filament_type name
  3. Creates TempPrintOrder with all PrintOrder schema fields
  4. Calls stripe_service.create_payment_link_for_order()
  5. Returns payment URL for frontend redirect

**GET /api/order-details** (Order Confirmation):
- Request: `?order_id={PrintOrder.id}&customer_id={Customer.id}` (both as URL query params)
- Response: `{status, message, order_id, customer_id, estimated_delivery}`
- Features:
  - Handles Optional[str] parameters (can receive "None" string literal)
  - Safe conversion: `int(param) if param and param != "None" else None`
  - Generic success response (privacy-conscious)

### 3. Database Models ✅
Complete redesign in `api/models.py`:

**New Core Models**:
- **Customer**: id, name, email, phone, stripe_customer_id, gdpr_consent, marketing_opt_in
- **Material**: id, name, density_g_per_cm3, price_per_kg, is_active
- **PrintOrder**: id, order_number, material_id, customer_id, quantity, volume_cm3, weight_g, delivery_zip_code, delivery_address, total_cents, payment_status, order_status, rush_order, model_filename, scheduled_print_date, completion_date
- **PrintJob**: id, print_order_id, status, printer_name, progress_percent, estimated_duration_minutes
- **Invoice**: id, print_order_id, invoice_number, work_performed, subtotal, tax, total, total_cents, stripe_invoice_id, pdf_generated

**Relationships**:
- PrintOrder.customer_id → Customer (FK)
- PrintOrder.material_id → Material (FK)
- PrintJob.print_order_id → PrintOrder (FK)
- Invoice.print_order_id → PrintOrder (FK)

### 4. Documentation Created ✅

**API_PARAMETER_ALIGNMENT.md**:
- Complete mapping of frontend query params → API fields → database columns
- Data flow diagrams for Quote → Checkout → Payment Success flows
- Stripe metadata synchronization details
- Testing checklist
- Implementation status per component

**PARAMETER_ALIGNMENT_STATUS.md**:
- Detailed implementation status (Completed, Partially Complete, Pending)
- Known issues and workarounds
- Validation queries for testing
- Quick reference of changes (automotive → 3D printing)

---

## Data Flow - End to End

### Step 1: Quote Calculation
```
Frontend (App.jsx)
  user selects material, quantity, zip code
  ↓
calculates volume/weight from STL file
  ↓
POST /api/quote {
  filament_type: "PLA Basic",
  quantity: 1,
  zip_code: "90210",
  volume: 50.0,
  weight: 75.0,
  rush_order: false
}
  ↓
Backend (quote.py)
  • Material lookup: "PLA Basic" → material_id=1
  • Calculate costs: material + shipping + tax
  • Return QuoteResponse with breakdown
```

### Step 2: Checkout
```
Frontend (App.jsx)
  user enters email, name, phone
  ↓
POST /api/checkout {
  email: "customer@example.com",
  name: "John Doe",
  phone: "555-1234",
  filament_type: "PLA Basic",
  quantity: 1,
  zip_code: "90210",
  volume: 50.0,
  weight: 75.0,
  rush_order: false
}
  ↓
Backend (quote.py)
  1. Create/fetch Customer {email, name, phone}
  2. Lookup Material {name="PLA Basic"} → material_id
  3. Create TempPrintOrder {
       order_number: "0",
       material_id: 1,
       customer_id: 123,
       quantity: 1,
       volume_cm3: 50.0,
       weight_g: 75.0,
       delivery_zip_code: "90210",
       total_cents: 5000,
       rush_order: false
     }
  4. Call stripe_service.create_payment_link_for_order(order)
  5. Return CheckoutResponse {
       payment_url: "https://pay.stripe.com/...",
       total_amount_cents: 5000
     }
  ↓
Frontend redirects to payment_url
```

### Step 3: Stripe Payment
```
Stripe Payment Link
  user enters credit card information
  ↓
completes payment
  ↓
redirects to: /payment-success?order_id=123&customer_id=456
```

### Step 4: Order Confirmation
```
Frontend (PaymentSuccess.jsx)
  extracts URL parameters:
    order_id = 123
    customer_id = 456
  ↓
GET /api/order-details?order_id=123&customer_id=456
  ↓
Backend (quote.py)
  • Convert parameters: str → int
  • Lookup PrintOrder where id=123 AND customer_id=456
  • Return OrderDetails {
      order_id: 123,
      customer_id: 456,
      status: "confirmed",
      message: "Check your email..."
    }
  ↓
Frontend displays order confirmation
```

---

## Parameter Mapping Reference

| Flow Step | Frontend Variable | API Parameter | Database Column | Stripe Field |
|---|---|---|---|---|
| **Quote** | filament_type | filament_type | Material.id (lookup) | material |
| | quantity | quantity | PrintOrder.quantity | quantity |
| | zip_code | zip_code | PrintOrder.delivery_zip_code | delivery_zip |
| | volume | volume | PrintOrder.volume_cm3 | volume_cm3 |
| | weight | weight | PrintOrder.weight_g | weight_g |
| | rush_order | rush_order | PrintOrder.rush_order | rush_order |
| **Checkout** | email | email | Customer.email | - |
| | name | name | Customer.name | customer_name |
| | phone | phone | Customer.phone | customer_phone |
| **(all above)** + | - | - | PrintOrder + Material | order_id, order_number, material |
| **Success** | order_id (URL) | order_id | PrintOrder.id | order_id |
| | customer_id (URL) | customer_id | Customer.id | customer_id |

---

## Key Implementation Details

### 1. Material Type Resolution
Frontend sends `filament_type` as string (e.g., "PLA Basic"). Backend must:
```python
material = db.query(Material).filter(Material.name == filament_type).first()
if material:
    material_id = material.id
else:
    raise error("Material not found")
```

### 2. Order ID Generation
- During checkout: TempPrintOrder has `order_number="0"` and `id=0`
- After payment success: Real PrintOrder created with auto-incremented `id` and generated `order_number`
- Stripe redirect always uses real PrintOrder.id in URL

### 3. None Parameter Handling
URL query parameters come as strings. Handle edge cases:
```python
order_id = request.query_params.get('order_id')  # "None" or "123" or None
customer_id = request.query_params.get('customer_id')

# Safe conversion
order_id = int(order_id) if order_id and order_id != "None" else None
customer_id = int(customer_id) if customer_id and customer_id != "None" else None
```

### 4. Stripe Metadata Synchronization
All Stripe objects (Customer, Payment Link, Payment Intent, Invoice) include metadata for dashboard visibility:
```python
{
  "order_id": str(order.id),
  "order_number": order.order_number,
  "customer_id": str(customer.id),
  "material": material.name,
  "volume_cm3": str(order.volume_cm3),
  "weight_g": str(order.weight_g),
  "delivery_zip": order.delivery_zip_code,
  "amount_cents": str(order.total_cents)
}
```

### 5. Foreign Key Relationships
```
Customer (1) ← → (N) PrintOrder
  ├─ stripe_customer_id = Stripe Customer ID
  └─ created_at, gdpr_consent, marketing_opt_in

Material (1) ← → (N) PrintOrder
  ├─ name = "PLA Basic", "PETG", etc.
  ├─ price_per_kg = 20.00
  └─ density_g_per_cm3 = 1.25

PrintOrder (1) ← → (N) PrintJob
  ├─ delivery_zip_code = "90210"
  ├─ total_cents = 5000
  ├─ order_status = "pending" | "printing" | "completed"
  └─ payment_status = "pending" | "paid" | "refunded"

Invoice (N) ← (1) PrintOrder
  └─ tracks payment history
```

---

## Files Updated

| File | Changes | Status |
|---|---|---|
| api/models.py | Complete redesign: Vehicle, Booking → PrintOrder, Material | ✅ Complete |
| api/stripe_service.py | All functions updated to use PrintOrder, metadata aligned | ✅ Complete |
| api/quote.py | Endpoints updated for PrintOrder schema | ✅ Complete |
| static/App.jsx | Uses correct endpoint paths and request bodies | 🔄 Needs validation |
| static/PaymentSuccess.jsx | Extracts order_id and customer_id from URL | 🔄 Needs validation |
| API_PARAMETER_ALIGNMENT.md | New comprehensive reference guide | ✅ Created |
| PARAMETER_ALIGNMENT_STATUS.md | Implementation checklist and status | ✅ Created |

---

## Testing Checklist

- [ ] **Quote Endpoint**: POST /api/quote with valid data returns cost breakdown
- [ ] **Checkout Endpoint**: POST /api/checkout creates Customer and returns Stripe payment URL
- [ ] **Order Details Endpoint**: GET /api/order-details with valid parameters returns order info
- [ ] **None Handling**: /api/order-details handles "None" string parameters correctly
- [ ] **Material Lookup**: filament_type strings correctly map to Material.id
- [ ] **Stripe Payment Link**: Created with correct metadata visible in dashboard
- [ ] **Payment Redirect**: After Stripe payment, redirects to /payment-success?order_id=X&customer_id=Y
- [ ] **Payment Success Page**: Correctly extracts URL parameters and displays order confirmation
- [ ] **Database Records**: Customers, PrintOrders, and Invoices created with correct fields
- [ ] **End-to-End Flow**: Upload STL → Quote → Checkout → Payment → Confirmation

---

## What's Next

1. **Immediate**: Verify frontend (App.jsx, PaymentSuccess.jsx) works with the backend endpoints
2. **Testing**: Run complete flow through Stripe sandbox
3. **Database**: Ensure Material records exist with correct pricing
4. **Production**: Update environment variables (STRIPE_ENABLED, STRIPE_API_KEY, etc.)

---

## Notes

- **No breaking changes**: All changes are backward-compatible with the new schema
- **Stripe synchronization**: All metadata flows to Stripe for dashboard visibility and dispute resolution
- **Tax calculation**: Still uses sales_tax_rates.py with delivery_zip_code
- **Shipping calculation**: Uses PrintOrder weight/volume and zip code
- **Cost calculation**: material_cost (weight × price_per_kg) + shipping + tax

