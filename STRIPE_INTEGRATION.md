# Stripe Integration Guide for 3D Printing Website

## Overview

This guide explains how the Stripe payment integration works in the 3D printing quote system. When a customer clicks "Proceed to Checkout," they are taken to Stripe's payment link, and after successful payment, they're redirected to a "Payment Success" page.

## Architecture

```
User Flow:
1. Upload STL model → 2. Configure options → 3. Review order + enter contact info → 
4. Click "Proceed to Checkout" → 5. Redirected to Stripe payment link →
6. Complete payment → 7. Redirected to Payment Success page
```

## Components

### Backend (Python/FastAPI)

#### 1. **quote.py** - Checkout Endpoint
New endpoint: `POST /api/checkout`

**Request Body:**
```json
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
```

**Response:**
```json
{
  "payment_url": "https://buy.stripe.com/...",
  "total_amount_cents": 5299
}
```

**What it does:**
1. Validates customer input
2. Recalculates the quote using the existing `quote()` function
3. Creates a temporary Customer object
4. Calls `stripe_service.get_or_create_stripe_customer()` to register in Stripe
5. Creates a temporary Booking object
6. Calls `stripe_service.create_payment_link_for_booking()` to generate the Stripe payment link
7. Returns the payment link URL to the frontend

#### 2. **stripe_service.py** - Existing Functions Used

**`get_or_create_stripe_customer(customer)`**
- Creates a Stripe customer record if it doesn't exist
- Stores customer metadata in Stripe for dashboard visibility
- Returns the Stripe customer ID

**`create_payment_link_for_booking(booking, db_session, customer)`**
- Creates a Stripe Payment Link (checkout session without session ID)
- Includes comprehensive metadata about the order
- Sets redirect URL to: `{PAYMENT_RETURN_URL}?booking_id={id}&customer_id={id}`
- Returns the payment link URL

#### 3. **quote.py** - Order Details Endpoint
New endpoint: `GET /api/order-details?booking_id=123&customer_id=456`

Returns order details for the payment success page (optional - can return minimal data).

### Frontend (React)

#### 1. **App.jsx** - Updated Components

**New State Fields:**
```javascript
selections: {
  email: '',      // NEW
  name: '',       // NEW
  phone: '',      // NEW
  material: '',
  quantity: 1,
  zip_code: '',
  rush_order: false
}
```

**New Function: `proceedToCheckout()`**
- Validates email and name are filled
- Calls `POST /api/checkout` with order details
- Receives `payment_url`
- Redirects user: `window.location.href = payment_url`

**Updated Step 3 (Review & Order)**
- Added customer contact information form (email, name, phone)
- "Proceed to Checkout" button now calls `proceedToCheckout()` instead of being static
- Button disabled until email and name are provided

#### 2. **PaymentSuccess.jsx** - New Component
Displays after Stripe payment completion.

**Features:**
- Success confirmation message
- Order details (if available via API)
- Next steps guide
- FAQ section
- Print receipt and return home buttons
- Contact support link

**Usage:**
```javascript
import PaymentSuccess from './PaymentSuccess';

// In routes or conditional rendering:
<PaymentSuccess bookingId={bookingId} customerId={customerId} />
```

## Integration Steps

### Step 1: Verify Environment Variables

Ensure these are set in your `.env` file:

```bash
STRIPE_ENABLED=true
STRIPE_API_KEY=sk_test_... or sk_live_...
CURRENCY=usd
PAYMENT_RETURN_URL=http://localhost:5000/payment-success  # or your domain
DEPOSIT_AMOUNT_CENTS=2500  # Default amount (can be overridden)
```

### Step 2: Update Frontend Routing

If using React Router, add a route for the payment success page:

```javascript
// In main routing file (e.g., index.jsx or router.jsx)
import App from './App';
import PaymentSuccess from './PaymentSuccess';

// Route when Stripe redirects back
const router = [
  { path: '/payment-success', element: <PaymentSuccess /> },
  { path: '/', element: <App /> }
];
```

Or use search params to detect when payment succeeded:

```javascript
// In App.jsx or wrapper component
useEffect(() => {
  const params = new URLSearchParams(window.location.search);
  if (params.get('booking_id') && params.get('customer_id')) {
    // Show payment success page
  }
}, []);
```

### Step 3: Test the Flow

1. **Start your development server:**
   ```bash
   npm run dev  # or vite
   ```

2. **Test checkout:**
   - Upload an STL file
   - Configure options
   - Enter email: `test@example.com`
   - Enter name: `Test Customer`
   - Enter phone: `(555) 123-4567`
   - Click "Proceed to Checkout"

3. **In Stripe test mode, use these test card numbers:**
   - Visa: `4242 4242 4242 4242`
   - Amex: `3782 822463 10005`
   - Mastercard: `5555 5555 5555 4444`
   - Use any future expiry date and any CVC

4. **Verify redirect:**
   - After payment, you should be redirected to the return URL with booking_id and customer_id parameters

## Stripe Metadata Stored

The system stores comprehensive metadata in Stripe for tracking and support:

**On Stripe Customer:**
```
{
  "customer_id": "1",
  "name": "John Doe",
  "phone": "(555) 123-4567",
  "language": "en",
  "gdpr_consent": "false",
  "marketing_opt_in": "false",
  "created_at": "2026-01-01T12:00:00"
}
```

**On Payment Link:**
```
{
  "booking_id": "0",
  "customer_id": "1",
  "payment_type": "deposit",
  "service_type": "3D Print - PLA Basic",
  "amount_cents": "5299"
}
```

**On Payment Intent:**
```
{
  "booking_id": "0",
  "customer_id": "1",
  "payment_type": "deposit",
  "service_type": "3D Print - PLA Basic",
  "quantity": "1",
  "rush_order": "false"
}
```

## Production Deployment

### Important Changes for Production:

1. **Database Integration:**
   - Modify `/api/checkout` to save Customer and Booking to database
   - Use real database session instead of temporary objects
   - Update `stripe_service` to work with persisted objects

2. **Payment Return URL:**
   ```bash
   # Development
   PAYMENT_RETURN_URL=http://localhost:5000/payment-success
   
   # Production
   PAYMENT_RETURN_URL=https://yourdomain.com/payment-success
   ```

3. **Stripe Keys:**
   ```bash
   # Test mode (development)
   STRIPE_API_KEY=sk_test_...
   
   # Live mode (production) - change after testing complete
   STRIPE_API_KEY=sk_live_...
   ```

4. **Email Notifications:**
   - Consider adding automatic email confirmations after payment
   - Include order details and tracking information
   - Implement order status updates

5. **Webhook Handling:**
   - Add Stripe webhook endpoint to handle payment events
   - Validate webhook signatures
   - Update order status based on payment events

### Example Webhook Setup (optional):

```python
from fastapi import Request
import stripe

@app.post('/api/webhooks/stripe')
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError:
        return {"error": "Invalid payload"}
    except stripe.error.SignatureVerificationError:
        return {"error": "Invalid signature"}
    
    # Handle payment_intent.succeeded
    if event['type'] == 'payment_intent.succeeded':
        payment_intent = event['data']['object']
        booking_id = payment_intent['metadata'].get('booking_id')
        # Update your database
    
    return {"status": "success"}
```

## Troubleshooting

### Issue: "Failed to create payment link. Stripe may not be configured."

**Solution:**
1. Check `STRIPE_ENABLED=true` in environment
2. Verify `STRIPE_API_KEY` is set correctly
3. Check the server logs for specific error messages

### Issue: Payment redirects but return URL doesn't show payment info

**Solution:**
1. Verify `PAYMENT_RETURN_URL` is set correctly
2. Check browser console for JavaScript errors
3. Ensure PaymentSuccess component is mounted at the return path

### Issue: "Missing required fields" error

**Solution:**
1. Ensure customer entered email, name, and all required fields
2. Check browser console for validation errors
3. Verify zip code format is correct

### Issue: Customer created but no payment link generated

**Solution:**
1. Check Stripe dashboard for customer creation
2. Verify API key has `payment_link:write` permission
3. Check server logs for payment link creation error

## Files Modified

1. **[api/quote.py](api/quote.py)** - Added checkout endpoint and order details endpoint
2. **[static/App.jsx](static/App.jsx)** - Added customer form and Stripe integration
3. **[static/PaymentSuccess.jsx](static/PaymentSuccess.jsx)** - NEW - Payment success page

## Next Steps

1. ✅ Test the integration in development with test cards
2. ⚠️ Connect to database to persist customer and booking data
3. ⚠️ Add email notifications after successful payment
4. ⚠️ Implement Stripe webhooks for payment status updates
5. ⚠️ Switch to production Stripe keys when ready
6. ⚠️ Add error handling and logging throughout the flow

## API Reference

### POST /api/checkout
Creates a Stripe payment link for an order

**Required fields:**
- `email` - Customer email
- `name` - Customer full name
- `zip_code` - For tax calculation
- `filament_type` - Material type
- `volume` - Model volume in cm³
- `weight` - Model weight in grams

**Returns:**
- `payment_url` - Stripe payment link to redirect to
- `total_amount_cents` - Total in cents

### GET /api/order-details
Retrieves order details after payment (optional)

**Query params:**
- `booking_id` - Order ID
- `customer_id` - Customer ID

**Returns:**
- Order details or generic success response

## Support

For Stripe API issues: https://stripe.com/docs
For integration questions: Check the inline code comments in `stripe_service.py`
