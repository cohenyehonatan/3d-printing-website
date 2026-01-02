# Quick Start: Stripe Integration

## What Changed

### Before Integration
- Quote displayed with static "Proceed to Checkout" button
- No payment functionality
- No customer contact capture

### After Integration
- ✅ Customer contact form (email, name, phone)
- ✅ "Proceed to Checkout" button creates Stripe payment link
- ✅ Redirects to Stripe hosted payment page
- ✅ After payment, redirects to success page
- ✅ Success page shows order confirmation

## Implementation Summary

### 3 Files Modified/Created

#### 1. Backend: `api/quote.py`
**Added:**
- `CheckoutRequest` model - validates customer input
- `CheckoutResponse` model - returns payment URL
- `POST /api/checkout` endpoint - creates Stripe payment link
- `GET /api/order-details` endpoint - returns order info

**Key code:**
```python
@app.post('/api/checkout', response_model=CheckoutResponse)
async def checkout(request_data: CheckoutRequest):
    # Calculate quote
    quote_response = await quote(quote_request)
    
    # Create Stripe customer
    stripe_customer_id = stripe_service.get_or_create_stripe_customer(customer)
    
    # Create payment link
    payment_url = stripe_service.create_payment_link_for_booking(booking, None, customer)
    
    return CheckoutResponse(payment_url=payment_url, ...)
```

#### 2. Frontend: `static/App.jsx`
**Added:**
- Customer info fields: `email`, `name`, `phone` in state
- `proceedToCheckout()` function - calls API and redirects to Stripe
- Customer contact form in Step 3 review page
- Form validation before checkout

**Key code:**
```javascript
const proceedToCheckout = async () => {
  // Fetch /api/checkout with order details
  const checkoutData = await fetch('/api/checkout', { ... });
  
  // Redirect to Stripe payment link
  window.location.href = checkoutData.payment_url;
};
```

#### 3. Frontend: `static/PaymentSuccess.jsx` (NEW)
**Features:**
- Success confirmation message
- Order details display
- Next steps guide (email, printing, tracking, delivery)
- FAQ section
- Print receipt button
- Return home button
- Contact support link

## How It Works

```
STEP 1: UPLOAD MODEL
  User uploads STL file
  ↓
STEP 2: CONFIGURE
  User selects material, quantity, zip code, rush order
  ↓
STEP 3: REVIEW & CHECKOUT
  Quote displayed
  User enters: Email*, Name*, Phone
  Clicks "Proceed to Checkout"
  ↓
CHECKOUT PROCESS
  Frontend: POST /api/checkout
    └─ Backend: Calculates quote
    └─ Backend: Creates Stripe customer
    └─ Backend: Creates payment link
    └─ Backend: Returns payment URL
  Frontend: Redirect to payment URL
  ↓
STRIPE PAYMENT PAGE
  User enters card details
  User completes payment
  Stripe redirects to: {PAYMENT_RETURN_URL}?booking_id={id}&customer_id={id}
  ↓
PAYMENT SUCCESS PAGE
  Shows confirmation
  Shows order details
  Shows next steps
```

## Testing Checklist

- [ ] Stripe API key is set in environment (`STRIPE_ENABLED=true`, `STRIPE_API_KEY=sk_test_...`)
- [ ] Payment return URL is configured (`PAYMENT_RETURN_URL=http://localhost:5000/payment-success`)
- [ ] Upload STL file
- [ ] Select material, zip code, options
- [ ] Enter email and name (required)
- [ ] Click "Proceed to Checkout"
- [ ] Use Stripe test card: `4242 4242 4242 4242`
- [ ] Verify payment succeeds and redirects to success page
- [ ] Verify success page displays correctly

## Stripe Test Cards

Use these in development/test mode:

| Card Type | Number | Exp Date | CVC |
|-----------|--------|----------|-----|
| Visa | 4242 4242 4242 4242 | Any future | Any |
| Visa (decline) | 4000 0000 0000 0002 | Any future | Any |
| Amex | 3782 822463 10005 | Any future | Any |
| Mastercard | 5555 5555 5555 4444 | Any future | Any |

## Key Features

### ✅ Customer Data Collection
- Email (required)
- Name (required)  
- Phone (optional)
- All stored in Stripe for CRM purposes

### ✅ Metadata Tracking
Order details stored in Stripe:
- Booking ID
- Customer ID
- Material type
- Quantity
- Order amount
- All searchable in Stripe dashboard

### ✅ Secure Payment
- Uses Stripe hosted payment page
- PCI compliance handled by Stripe
- No credit card data touches your server

### ✅ Flexible Return URL
Configured via environment variable:
```bash
PAYMENT_RETURN_URL=https://yourdomain.com/payment-success
```

## Environment Setup

Add to your `.env` file:

```bash
# Stripe Configuration
STRIPE_ENABLED=true
STRIPE_API_KEY=sk_test_...  # Get from Stripe dashboard
CURRENCY=usd
PAYMENT_RETURN_URL=http://localhost:5000/payment-success

# Optional
DEPOSIT_AMOUNT_CENTS=2500  # Default fallback amount
```

## Next: Database Integration (Optional)

For production, modify `/api/checkout` to:

```python
@app.post('/api/checkout')
async def checkout(request_data: CheckoutRequest, db_session: Session = Depends(get_db)):
    # ... same quote calculation ...
    
    # Save customer to database
    customer = Customer(
        name=request_data.name,
        email=request_data.email,
        phone=request_data.phone
    )
    db_session.add(customer)
    db_session.commit()
    
    # Save booking to database
    booking = Booking(
        customer_id=customer.id,
        service_type=f"3D Print - {request_data.filament_type}",
        # ... other fields ...
    )
    db_session.add(booking)
    db_session.commit()
    
    # ... rest of checkout logic ...
```

## Production Checklist

- [ ] Database integration implemented
- [ ] Email notifications added
- [ ] Stripe webhooks configured
- [ ] Production Stripe API key obtained (`sk_live_...`)
- [ ] Production payment return URL set
- [ ] Error handling tested
- [ ] Load testing done
- [ ] Security review completed
- [ ] Stripe's PCI compliance checklist reviewed

## Code Files

**Modified:**
- `api/quote.py` - Backend endpoints
- `static/App.jsx` - Frontend checkout flow

**Created:**
- `static/PaymentSuccess.jsx` - Success page component
- `STRIPE_INTEGRATION.md` - Full documentation
