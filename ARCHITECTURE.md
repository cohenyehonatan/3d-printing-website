# Stripe Integration - Architecture & Flow

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React)                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐   │
│  │  Step 1: Upload  │→ │ Step 2: Configure│→ │ Step 3:      │   │
│  │  STL Model       │  │ Material, Qty,   │  │ Review &     │   │
│  │                  │  │ Zip Code         │  │ Checkout    │   │
│  └──────────────────┘  └──────────────────┘  └──────────────┘   │
│                                                        │          │
│                                                        ↓          │
│                                            ┌─────────────────┐   │
│                                            │ Customer Form:  │   │
│                                            │ • Email*        │   │
│                                            │ • Name*         │   │
│                                            │ • Phone         │   │
│                                            └─────────────────┘   │
│                                                        │          │
│                                                        ↓          │
│                                            ┌──────────────────┐  │
│                                            │ "Proceed to      │  │
│                                            │ Checkout" Button │  │
│                                            └──────────────────┘  │
│                                                        │          │
└────────────────────────────────────────────────────────┼──────────┘
                                                         │
                                    API Call (POST /api/checkout)
                                                         │
┌────────────────────────────────────────────────────────┼──────────┐
│                    BACKEND (FastAPI/Python)           │          │
├────────────────────────────────────────────────────────┼──────────┤
│                                                        ↓          │
│    ┌─────────────────────────────────────────┐                  │
│    │ POST /api/checkout                      │                  │
│    │ ├─ Validate customer input              │                  │
│    │ ├─ Recalculate quote                    │                  │
│    │ ├─ Create temp Customer object          │                  │
│    │ ├─ Create temp Booking object           │                  │
│    │ └─ Return payment URL & amount          │                  │
│    └──────────────────┬──────────────────────┘                  │
│                       │                                          │
│                       ↓                                          │
│    ┌─────────────────────────────────────────┐                  │
│    │ stripe_service.py Functions             │                  │
│    │ ├─ get_or_create_stripe_customer()      │                  │
│    │ │  └─ Creates Stripe Customer with      │                  │
│    │ │     metadata (email, name, phone)    │                  │
│    │ │                                       │                  │
│    │ └─ create_payment_link_for_booking()    │                  │
│    │    └─ Creates Stripe Payment Link       │                  │
│    │       with order metadata               │                  │
│    └──────────────────┬──────────────────────┘                  │
│                       │                                          │
└───────────────────────┼──────────────────────────────────────────┘
                        │
                        │ Returns: {
                        │   payment_url: "https://buy.stripe.com/..."
                        │   total_amount_cents: 5299
                        │ }
                        │
┌───────────────────────┼──────────────────────────────────────────┐
│                 FRONTEND (React) - Redirect              │       │
├───────────────────────┼──────────────────────────────────────────┤
│                       ↓                                          │
│   window.location.href = checkoutData.payment_url               │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                        │
                        ↓
        ┌───────────────────────────────────┐
        │  STRIPE HOSTED CHECKOUT PAGE      │
        ├───────────────────────────────────┤
        │ • Display Order Summary            │
        │ • Card Input Fields                │
        │ • Billing Address                  │
        │ • Email Confirmation               │
        └───────────────────────────────────┘
                        │
                        ↓ (Customer enters card)
                        │
                  ┌──────────────┐
                  │ Process      │
                  │ Payment      │
                  └──────────────┘
                        │
                ┌───────┴──────────┐
                │                  │
          ┌─────▼────┐      ┌─────▼────┐
          │ SUCCESS  │      │ DECLINED │
          └─────┬────┘      └──────────┘
                │
                ↓ (Stripe redirects to PAYMENT_RETURN_URL)
                │
        ┌───────────────────────────────────┐
        │ /payment-success                  │
        │ ?booking_id=X&customer_id=Y       │
        └─────────────┬─────────────────────┘
                      │
                      ↓
          ┌───────────────────────────────┐
          │ PaymentSuccess Component      │
          │ ├─ Success message            │
          │ ├─ Order details              │
          │ ├─ Next steps guide           │
          │ ├─ FAQ                        │
          │ └─ Action buttons             │
          └───────────────────────────────┘
```

## Data Flow - Detailed

### 1. Checkout Initiation

```
Frontend State:
{
  selections: {
    email: "customer@example.com",
    name: "John Doe",
    phone: "(555) 123-4567",
    material: "PLA Basic",
    quantity: 1,
    zip_code: "12345",
    rush_order: false
  },
  modelStats: {
    volume: 125.5,
    weight: 155.2,
    ...
  }
}

↓ proceedToCheckout() called
↓ Validation passes
↓ POST /api/checkout
```

### 2. Backend Processing

```
Input:
{
  "email": "customer@example.com",
  "name": "John Doe",
  "phone": "(555) 123-4567",
  "zip_code": "12345",
  "filament_type": "PLA Basic",
  "quantity": 1,
  "rush_order": false,
  "volume": 125.5,
  "weight": 155.2
}

↓ Recalculate quote using existing quote() function
↓ Get base cost, material cost, shipping, tax
↓ Total: $52.99

↓ Create temporary Customer object:
{
  name: "John Doe",
  email: "customer@example.com",
  phone: "(555) 123-4567"
}

↓ Call: stripe_service.get_or_create_stripe_customer(customer)
  Returns: cus_xxxxxxxxx

↓ Create temporary Booking object:
{
  id: 0,  // temporary
  customer_id: 0,  // temporary
  service_type: "3D Print - PLA Basic",
  deposit_amount: 5299  // in cents
}

↓ Call: stripe_service.create_payment_link_for_booking(booking, None, customer)
  Returns: https://buy.stripe.com/...

↓ Return response:
{
  "payment_url": "https://buy.stripe.com/...",
  "total_amount_cents": 5299
}
```

### 3. Stripe Customer Created in Stripe Dashboard

```
Stripe Customer Object:
{
  id: "cus_xxxxxxxxx",
  email: "customer@example.com",
  name: "John Doe",
  phone: "(555) 123-4567",
  metadata: {
    "customer_id": "0",
    "name": "John Doe",
    "phone": "(555) 123-4567",
    "language": "en",
    "gdpr_consent": "false",
    "marketing_opt_in": "false",
    "created_at": "2026-01-01T12:00:00"
  }
}
```

### 4. Stripe Payment Link Created

```
Stripe Payment Link Object:
{
  id: "plink_xxxxxxxxx",
  url: "https://buy.stripe.com/...",
  metadata: {
    "booking_id": "0",
    "customer_id": "0",
    "payment_type": "deposit",
    "service_type": "3D Print - PLA Basic",
    "amount_cents": "5299"
  },
  payment_intent_data: {
    metadata: {
      "booking_id": "0",
      "customer_id": "0",
      "payment_type": "deposit",
      "service_type": "3D Print - PLA Basic",
      "quantity": "1"
    },
    customer: "cus_xxxxxxxxx"
  },
  after_completion: {
    redirect: {
      url: "http://localhost:5000/payment-success?booking_id=0&customer_id=0"
    }
  }
}
```

### 5. Successful Payment

```
Customer on Stripe Page:
1. Enters card: 4242 4242 4242 4242
2. Enters exp date: 12/27
3. Enters CVC: 123
4. Enters email: customer@example.com
5. Clicks "Pay"

↓ Stripe processes payment

PaymentIntent Created:
{
  id: "pi_xxxxxxxxx",
  customer: "cus_xxxxxxxxx",
  amount: 5299,
  currency: "usd",
  status: "succeeded",
  metadata: {
    "booking_id": "0",
    "customer_id": "0",
    ...
  }
}

↓ Stripe redirects to:
http://localhost:5000/payment-success?booking_id=0&customer_id=0
```

## Component Communication

```
┌─────────────────────┐
│    App.jsx          │
├─────────────────────┤
│ State:              │
│ • modelFile         │
│ • modelStats        │
│ • selections{       │
│   - email*          │
│   - name*           │
│   - phone           │
│ }                   │
│ • quote             │
│ • loading, error    │
│                     │
│ Functions:          │
│ • handleFileUpload()│
│ • calculatePrice()  │
│ • proceedToChk()    │
│                     │
│ Renders:            │
│ • Step 1: Upload    │
│ • Step 2: Configure │
│ • Step 3: Review    │
└──────────┬──────────┘
           │
           ├─→ POST /api/quote
           │   Response: quote breakdown
           │
           └─→ POST /api/checkout
               Response: payment_url
               Action: Redirect to Stripe
```

## Error Handling Flow

```
proceedToCheckout()
    ↓
Validate email & name
    ├─→ FAIL: Show alert "Please enter email and name"
    └─→ PASS
        ↓
    Call /api/checkout
        ├─→ Error 400: Missing fields
        │   Frontend: Show error message
        │
        ├─→ Error 500: Stripe not configured
        │   Frontend: Show "Stripe not configured" error
        │
        └─→ Success 200
            Response: { payment_url, total_amount_cents }
            ↓
        Redirect to payment_url
```

## State Management Timeline

```
Timeline: Customer fills out form

T0: User uploads file
    state.modelFile = File
    state.modelStats = {volume, weight, ...}
    step = 2

T1: User configures options
    state.selections.material = "PLA Basic"
    state.selections.quantity = 1
    state.selections.zip_code = "12345"
    state.selections.rush_order = false
    Click "Get Quote"

T2: Quote fetched
    state.quote = {breakdown}
    step = 3

T3: User enters contact info
    state.selections.email = "customer@example.com"
    state.selections.name = "John Doe"
    state.selections.phone = "(555) 123-4567"

T4: User clicks "Proceed to Checkout"
    state.loading = true
    POST /api/checkout with state.selections + state.modelStats

T5: Payment URL received
    window.location.href = payment_url

T6: User completes payment on Stripe
    Stripe redirects to /payment-success?booking_id=X&customer_id=Y

T7: PaymentSuccess component mounted
    Optionally fetch /api/order-details
    Display confirmation
```

## API Endpoints

### Frontend → Backend

```
1. POST /api/quote
   Input: {zip_code, filament_type, quantity, rush_order, volume, weight}
   Output: {total_cost_with_tax, sales_tax, base_cost, ...}
   Purpose: Calculate initial quote

2. POST /api/checkout
   Input: {email, name, phone, zip_code, filament_type, ...}
   Output: {payment_url, total_amount_cents}
   Purpose: Create Stripe payment link

3. GET /api/order-details?booking_id=X&customer_id=Y
   Input: Query params
   Output: {order details or success message}
   Purpose: Retrieve order info for confirmation page
```

### Backend → Stripe

```
1. stripe.Customer.create(email, name, phone, metadata)
   Returns: Customer ID (cus_...)

2. stripe.Customer.modify(id, address={...})
   Updates customer with address info

3. stripe.Price.create(unit_amount, currency, product_data)
   Returns: Price ID

4. stripe.PaymentLink.create(line_items, metadata, payment_intent_data, ...)
   Returns: Payment Link (full object with .url)

5. stripe.InvoiceItem.create(customer, amount, currency, description, invoice)
   Used for invoice payments (referenced in stripe_service.py)

6. stripe.Invoice.create(customer, metadata, description, auto_advance)
   Used for invoice payments (referenced in stripe_service.py)
```

## File Dependencies

```
stripe_service.py
    ├─ Models:
    │  ├─ Customer
    │  ├─ Booking
    │  └─ Invoice
    │
    └─ Functions:
       ├─ get_or_create_stripe_customer()
       ├─ create_payment_link_for_booking()  ←── USED IN CHECKOUT
       └─ create_stripe_invoice_from_pdf()

quote.py
    ├─ Imports:
    │  ├─ stripe_service
    │  ├─ sales_tax_rates
    │  └─ zip_to_state
    │
    ├─ Models:
    │  ├─ QuoteRequest
    │  ├─ QuoteResponse
    │  ├─ VerifyFileResponse
    │  ├─ CheckoutRequest  ←── NEW
    │  └─ CheckoutResponse ←── NEW
    │
    └─ Endpoints:
       ├─ POST /api/quote
       ├─ POST /api/verify-file
       ├─ POST /api/checkout     ←── NEW
       └─ GET /api/order-details ←── NEW

App.jsx
    ├─ Imports:
    │  ├─ STLParser
    │  └─ PaymentSuccess  ←── NEW
    │
    ├─ State:
    │  ├─ step, modelFile, modelStats, loading, error
    │  └─ selections {email, name, phone, ...}
    │
    └─ Functions:
       ├─ handleFileUpload()
       ├─ calculatePrice()
       └─ proceedToCheckout()  ←── NEW

PaymentSuccess.jsx ←── NEW
    ├─ Props: bookingId, customerId
    ├─ Fetches: /api/order-details
    └─ Displays: Success page with confirmation
```

This architecture ensures clean separation of concerns:
- **Frontend**: Handles UI, form validation, user interaction
- **Backend**: Handles business logic, quote calculation, Stripe integration
- **Stripe**: Handles payment processing, security, compliance
