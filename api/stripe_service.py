"""
Stripe service for FastAPI
Sync Stripe operations - called via thread pool executor
"""
from typing import Optional, cast, Any
import stripe
from models import Customer, Booking
import os
import traceback
from decimal import Decimal
from models import Invoice


def get_or_create_stripe_customer(customer: Customer) -> Optional[str]:
    """Get or create Stripe customer ID with full customer data for cross-referencing.
    
    Syncs customer info to Stripe metadata for dashboard visibility and lifecycle management.
    """
    STRIPE_ENABLED = os.getenv('STRIPE_ENABLED', 'false').lower() in {'1', 'true', 'yes'}
    
    if not STRIPE_ENABLED:
        return None
    
    if not stripe.api_key:
        print("[Stripe] Warning: Stripe API key not configured")
        return None
    
    if customer.stripe_customer_id is not None:
        return cast(Optional[str], customer.stripe_customer_id)
    
    # Create new Stripe customer with comprehensive metadata
    # Cast ORM Column attributes to str for the Stripe API call so the type checker accepts them.
    email = cast(str, customer.email)
    name = cast(str, customer.name)
    phone = cast(str, customer.phone or '')
    preferred_language = cast(str, customer.preferred_language or 'en')
    
    # Build metadata dictionary with all customer info for Stripe dashboard cross-referencing
    metadata = {
        'customer_id': str(customer.id),
        'name': name,
        'phone': phone,
        'language': preferred_language,
        'gdpr_consent': str(bool(customer.gdpr_consent)),
        'marketing_opt_in': str(bool(customer.marketing_opt_in)),
        'created_at': customer.created_at.isoformat() if getattr(customer, "created_at", None) else '',
    }
    
    stripe_customer = stripe.Customer.create(
        email=email,
        name=name,
        phone=phone,
        metadata=metadata,
        description=f"Customer: {name} ({email})"
    )
    
    # Use setattr to avoid static type-checker complaints about SQLAlchemy Column attributes.
    setattr(customer, "stripe_customer_id", stripe_customer.id)
    
    # Note: Caller must commit the session
    print(f"[Stripe] Created customer {stripe_customer.id} with metadata: {metadata}")
    return stripe_customer.id


def create_payment_link_for_booking(booking: Booking, db_session, customer: Optional[Customer] = None) -> Optional[str]:
    """Create a Stripe payment link for booking deposit with full metadata.
    
    Syncs booking metadata to payment link and payment intent so Stripe dashboard
    shows booking info, customer details, vehicle, service type, etc.
    """
    STRIPE_ENABLED = os.getenv('STRIPE_ENABLED', 'false').lower() in {'1', 'true', 'yes'}
    DEPOSIT_AMOUNT_CENTS = int(os.getenv('DEPOSIT_AMOUNT_CENTS', 2500))
    CURRENCY = os.getenv('CURRENCY', 'usd')
    PAYMENT_RETURN_URL = os.getenv('PAYMENT_RETURN_URL', 'http://localhost:5000/payment-success')
    
    if not STRIPE_ENABLED:
        return None
    
    if not stripe.api_key:
        print("[Stripe] Warning: Stripe API key not configured")
        return None

    try:
        # Get customer object if not provided
        if not customer and getattr(booking, "customer_id", None):
            customer = db_session.query(Customer).filter_by(id=booking.customer_id).first()
        
        # Get vehicle for service details
        vehicle = booking.vehicle if hasattr(booking, 'vehicle') else None
        
        # Ensure amount is an integer (in cents)
        unit_amount = int(booking.deposit_amount or DEPOSIT_AMOUNT_CENTS)
        
        # Build comprehensive product metadata
        product_metadata = {
            "booking_id": str(booking.id),
            "customer_id": str(booking.customer_id),
            "payment_type": "deposit",
            "service_type": booking.service_type or '',
            "location": booking.location_type or '',
            "vehicle_vin": vehicle.vin if vehicle else '',
        }
        
        if vehicle:
            product_metadata.update({
                "vehicle_make": vehicle.make or '',
                "vehicle_model": vehicle.model or '',
                "vehicle_year": str(vehicle.year) if vehicle.year else '',
            })
        
        if customer:
            product_metadata.update({
                "customer_name": customer.name or '',
                "customer_email": customer.email or '',
                "customer_phone": customer.phone or '',
            })
        
        # Create a Price with comprehensive product data
        # NOTE: product_data does not accept a "description" field in the typed Stripe params,
        # so include the human-readable description inside metadata instead for compatibility.
        product_data = {
            "name": f"Service Deposit - {booking.service_type or 'Service'}",
            "metadata": product_metadata
        }
        # Add a short description into metadata for Stripe dashboard visibility
        product_data["metadata"]["product_description"] = f"Booking #{booking.id} - {vehicle.make if vehicle else ''} {vehicle.model if vehicle else ''}".strip()

        price = stripe.Price.create(
            unit_amount=unit_amount,
            currency=CURRENCY,
            product_data={
                "name": product_data["name"],
                "metadata": product_data["metadata"]
            }
        )
        
        # Build payment link metadata
        link_metadata = {
            "booking_id": str(booking.id),
            "customer_id": str(booking.customer_id),
            "payment_type": "deposit",
            "service_type": booking.service_type or '',
            "amount_cents": str(unit_amount),
        }
        
        if customer:
            link_metadata["customer_stripe_id"] = customer.stripe_customer_id or ''
        
        # Build payment intent data with metadata that flows to the resulting PaymentIntent
        pd = getattr(booking, "preferred_date", None)
        severity = getattr(booking, "severity_score", None)
        payment_intent_data = cast(Any, {
            "metadata": {
                "booking_id": str(booking.id),
                "customer_id": str(booking.customer_id),
                "payment_type": "deposit",
                "service_type": booking.service_type or '',
                "service_address": booking.service_address or '',
                "preferred_date": pd.isoformat() if pd is not None else '',
                "severity_score": str(severity) if severity is not None else '',
            }
        })
        
        # Add customer reference if available
        if customer and getattr(customer, 'stripe_customer_id', None):
            payment_intent_data["customer"] = cast(str, customer.stripe_customer_id)
        
        # Build redirect URL
        redirect_url = f"{PAYMENT_RETURN_URL}?booking_id={booking.id}&customer_id={booking.customer_id}"

        link = stripe.PaymentLink.create(
            line_items=[{
                "price": price.id,
                "quantity": 1,
            }],
            metadata=link_metadata,
            payment_intent_data=payment_intent_data,
            after_completion={
                "type": "redirect",
                "redirect": {"url": redirect_url}
            },
        )
        
        print(f"[Stripe] Created payment link for booking {booking.id} with comprehensive metadata")
        return link.url
    except Exception as e:
        print(f"[Stripe] Failed to create payment link: {e}")
        return None


def create_payment_link_for_invoice(booking: Booking, invoice: Invoice) -> Optional[str]:
    """Create a Stripe payment link for an invoice with comprehensive metadata.
    
    Amount = invoice.total_due (deposit is a separate transaction, not subtracted)
    
    Syncs invoice and booking data to Stripe for cross-referencing, lifecycle tracking,
    and dispute resolution.
    """
    STRIPE_ENABLED = os.getenv('STRIPE_ENABLED', 'false').lower() in {'1', 'true', 'yes'}
    CURRENCY = os.getenv('CURRENCY', 'usd')
    PAYMENT_RETURN_URL = os.getenv('PAYMENT_RETURN_URL', 'http://localhost:5000/payment-success')

    if not STRIPE_ENABLED:
        return None

    if not stripe.api_key:
        print("[Stripe] Warning: Stripe API key not configured")
        return None

    try:
        # Get customer and vehicle for metadata
        customer = booking.customer if hasattr(booking, 'customer') else None
        vehicle = booking.vehicle if hasattr(booking, 'vehicle') else None
        
        total_due_dec = Decimal(getattr(invoice, 'total_due', 0) or 0)
        total_due_cents = int(Decimal('100') * total_due_dec)

        # Deposit is a separate transaction - NOT subtracted from repair invoice
        # If total_due is zero, skip payment link (no charge for warranty-only work)
        if total_due_cents <= 0:
            print(f"[Stripe] Total due is {total_due_cents} cents; skipping payment link creation")
            return None

        # Build comprehensive product metadata
        invoice_number = str(getattr(invoice, 'invoice_number', ''))
        work_performed = str(getattr(invoice, 'work_performed', ''))[:200]  # Truncate for metadata
        
        product_metadata = {
            "booking_id": str(booking.id),
            "customer_id": str(booking.customer_id),
            "invoice_id": str(getattr(invoice, 'id', '')),
            "invoice_number": invoice_number,
            "payment_type": "invoice",
            "service_type": booking.service_type or '',
            "work_performed": work_performed,
            "subtotal": str(getattr(invoice, 'subtotal', 0)),
            "tax_amount": str(getattr(invoice, 'tax_amount', 0)),
            "total_due": str(total_due_dec),
            "note": "Deposit is a separate transaction",
        }
        
        if vehicle:
            product_metadata.update({
                "vehicle_vin": vehicle.vin or '',
                "vehicle_make": vehicle.make or '',
                "vehicle_model": vehicle.model or '',
                "vehicle_year": str(vehicle.year) if vehicle.year else '',
                "odometer": str(getattr(invoice, 'current_odometer', '')) or '',
            })
        
        if customer:
            product_metadata.update({
                "customer_name": customer.name or '',
                "customer_email": customer.email or '',
                "customer_phone": customer.phone or '',
            })
        
        # Create Price with detailed product data
        # NOTE: product_data does not accept a "description" field, so include it in metadata instead
        product_metadata["product_description"] = f"Booking {booking.id} - {work_performed}".strip()
        
        price = stripe.Price.create(
            unit_amount=total_due_cents,
            currency=CURRENCY,
            product_data={
                "name": f"Invoice #{invoice_number} - {booking.service_type or 'Service'} Total Due",
                "metadata": product_metadata
            },
        )

        # Build payment link metadata
        link_metadata = {
            "booking_id": str(booking.id),
            "invoice_id": str(getattr(invoice, 'id', '')),
            "invoice_number": invoice_number,
            "type": "invoice_payment",
            "customer_id": str(booking.customer_id),
            "amount_cents": str(total_due_cents),
        }
        
        if customer and customer.stripe_customer_id:
            link_metadata["customer_stripe_id"] = customer.stripe_customer_id
        
        # Build payment intent data with full invoice/booking context
        payment_intent_data = {
            "metadata": {
                "booking_id": str(booking.id),
                "customer_id": str(booking.customer_id),
                "invoice_id": str(getattr(invoice, 'id', '')),
                "invoice_number": invoice_number,
                "payment_type": "invoice",
                "service_type": booking.service_type or '',
                "service_address": booking.service_address or '',
                "work_performed": work_performed,
                "total_due": str(total_due_dec),
                "note": "Deposit is a separate transaction",
                "invoice_date": invoice.invoice_date.isoformat() if hasattr(invoice, 'invoice_date') else '',
            }
        }
        
        # Add customer reference if available for customer portal tracking (at top level, not nested)
        if customer and customer.stripe_customer_id:
            # Only add if it's a valid Stripe customer ID
            payment_intent_data = cast(Any, {
                "customer": customer.stripe_customer_id,
                "metadata": payment_intent_data["metadata"]
            })
        
        redirect_url = f"{PAYMENT_RETURN_URL}?booking_id={booking.id}&customer_id={booking.customer_id}"
        
        link = stripe.PaymentLink.create(
            line_items=[{
                "price": price.id,
                "quantity": 1,
            }],
            metadata=link_metadata,
            payment_intent_data=cast(Any, payment_intent_data),
            after_completion={
                "type": "redirect",
                "redirect": {"url": redirect_url},
            },
        )
        
        print(f"[Stripe] Created invoice payment link {invoice_number} with comprehensive metadata")
        return link.url
    except Exception as e:
        print(f"[Stripe] Failed to create invoice payment link: {e}")
        return None


def create_stripe_invoice_from_pdf(booking: Booking, invoice: Invoice, pdf_bytes: bytes, db_session=None) -> Optional[str]:
    """Create a Stripe invoice from generated PDF.
    
    Creates an invoice in Stripe with comprehensive metadata and line items for tracking and disputes.
    Breaks down the invoice into individual line items (parts, labor, taxes) for transparency.
    
    The PDF is NOT uploaded to Stripe (no appropriate File API purpose for invoices).
    Instead, the PDF should be emailed to the customer by the caller along with a Payment Intent link.
    
    Args:
        booking: The booking associated with the invoice
        invoice: The invoice object
        pdf_bytes: PDF file contents as bytes (for email delivery by caller)
        db_session: Database session to fetch line items
    
    Returns:
        Stripe invoice ID if successful, None otherwise
    """
    STRIPE_ENABLED = os.getenv('STRIPE_ENABLED', 'false').lower() in {'1', 'true', 'yes'}
    CURRENCY = os.getenv('CURRENCY', 'usd').lower()

    import traceback
    
    if not STRIPE_ENABLED:
        print("[Stripe] Invoice creation disabled - STRIPE_ENABLED is false")
        return None
    
    if not stripe.api_key:
        print("[Stripe] Warning: Stripe API key not configured")
        return None
    
    try:
        # Get customer for Stripe customer reference
        customer = booking.customer if hasattr(booking, 'customer') else None
        if not customer or not customer.stripe_customer_id:
            print(f"[Stripe] No Stripe customer found for booking {booking.id} - skipping invoice creation")
            return None
        
        # Update Stripe customer with service address from booking if available
        service_address = getattr(booking, 'service_address', '')
        if service_address:
            print(f"[Stripe] Updating customer with service address: {service_address}")
            try:
                stripe.Customer.modify(
                    customer.stripe_customer_id,
                    address={
                        "line1": service_address[:100],  # Truncate to Stripe's limit
                        "country": "US"  # Default to US, can be made configurable
                    }
                )
                print(f"[Stripe] Updated customer address")
            except Exception as addr_err:
                print(f"[Stripe] Warning: Could not update customer address: {addr_err}")
        
        # Build invoice metadata for tracking
        invoice_number = str(getattr(invoice, 'invoice_number', ''))
        vehicle = booking.vehicle if hasattr(booking, 'vehicle') else None
        work_performed = str(getattr(invoice, 'work_performed', ''))[:200]
        total_due_dec = Decimal(getattr(invoice, 'total_due', 0) or 0)
        
        invoice_metadata = {
            "booking_id": str(booking.id),
            "invoice_id": str(getattr(invoice, 'id', '')),
            "invoice_number": invoice_number,
            "work_performed": work_performed,
            "service_type": booking.service_type or '',
            "vehicle_vin": vehicle.vin if vehicle else '',
            "vehicle_make": vehicle.make if vehicle else '',
            "vehicle_model": vehicle.model if vehicle else '',
            "vehicle_year": str(vehicle.year) if vehicle and vehicle.year else '',
            "total_due": str(total_due_dec),
            "currency": CURRENCY,
        }
        
        print(f"[Stripe] Creating invoice for booking {booking.id}")
        print(f"[Stripe] Invoice number: {invoice_number}")
        print(f"[Stripe] Customer: {customer.stripe_customer_id}")
        print(f"[Stripe] Total due: {total_due_dec}")
        
        # Create Stripe invoice with auto_advance=False so we control when it's sent
        stripe_invoice = stripe.Invoice.create(
            customer=customer.stripe_customer_id,
            metadata=invoice_metadata,
            description=f"Service Invoice {invoice_number}",
            auto_advance=False  # Don't auto-finalize; we'll do it manually
        )
        print(f"[Stripe] Created invoice: {stripe_invoice.id}")
        
        # Add line items from database if available
        if db_session:
            from models import LineItem
            
            # Fetch all line items for this booking
            line_items = db_session.query(LineItem).filter_by(booking_id=booking.id).all()
            print(f"[Stripe] Found {len(line_items)} line items to add")
            
            # Log all items for debugging (including zero-amount items)
            for item in line_items:
                item_total = Decimal(str(getattr(item, 'total', 0) or 0))
                item_total_cents = int(Decimal('100') * item_total)
                item_category = getattr(item, 'item_category', 'unknown')
                print(f"[Stripe] Line item: {item.description} | Amount: {item_total} USD | Category: {item_category} | Warranty: {getattr(item, 'warranty_covered', False)}")
                
                if item_total_cents > 0:
                    description = f"{item.description}"
                    if item.part_type:
                        description += f" ({item.part_type})"
                    
                    stripe.InvoiceItem.create(
                        customer=customer.stripe_customer_id,
                        amount=item_total_cents,
                        currency=CURRENCY,
                        description=description,
                        invoice=stripe_invoice.id
                    )
                    print(f"[Stripe] Added line item: {description} - {item_total} USD")
                else:
                    print(f"[Stripe] Skipping line item (zero amount): {item.description}")
            
            # Add tax as a separate line item if present
            tax_amount_dec = Decimal(getattr(invoice, 'tax_amount', 0) or 0)
            if tax_amount_dec > 0:
                tax_cents = int(Decimal('100') * tax_amount_dec)
                stripe.InvoiceItem.create(
                    customer=customer.stripe_customer_id,
                    amount=tax_cents,
                    currency=CURRENCY,
                    description="Sales Tax",
                    invoice=stripe_invoice.id
                )
                print(f"[Stripe] Added tax line item: {tax_amount_dec} USD")
        else:
            # Fallback: add single line item with total amount
            total_due_cents = int(Decimal('100') * total_due_dec)
            print(f"[Stripe] No database session provided, adding single line item with total: {total_due_dec} USD ({total_due_cents} cents)")
            
            stripe.InvoiceItem.create(
                customer=customer.stripe_customer_id,
                amount=total_due_cents,
                currency=CURRENCY,
                description=f"Service: {work_performed[:100]}",
                invoice=stripe_invoice.id
            )
        
        
        # Store the Stripe invoice ID in our database for reference
        setattr(invoice, 'stripe_invoice_id', stripe_invoice.id)
        print(f"[Stripe] Successfully created Stripe invoice {stripe_invoice.id} for booking {booking.id}")
        
        # Return both the invoice ID and PDF bytes for email delivery
        # (The caller will handle emailing the PDF to the customer)
        setattr(invoice, 'pdf_bytes', pdf_bytes)
        
        return stripe_invoice.id
        
    except Exception as e:
        import traceback
        print(f"[Stripe] Error creating Stripe invoice: {str(e)}")
        print(f"[Stripe] Exception type: {type(e).__name__}")
        print(f"[Stripe] Traceback: {traceback.format_exc()}")
        return None


def process_stripe_refund(booking: Booking, amount_cents: int, reason: str) -> str:
    """
    Process a Stripe refund for a credit memo.
    
    Args:
        booking: The booking associated with the invoice
        amount_cents: Refund amount in cents
        reason: Reason for refund
    
    Returns:
        Status string: 'succeeded', 'pending', 'disabled', or 'error'
    """
    STRIPE_ENABLED = os.getenv('STRIPE_ENABLED', 'false').lower() in {'1', 'true', 'yes'}
    
    if not STRIPE_ENABLED:
        print("[Stripe] Refunds disabled - STRIPE_ENABLED is false")
        return "disabled"
    
    if not stripe.api_key:
        print("[Stripe] Warning: Stripe API key not configured")
        return "disabled"
    
    # Check if booking has a payment intent
    payment_intent_id = getattr(booking, 'stripe_payment_intent_id', None)
    
    if not payment_intent_id:
        print(f"[Stripe] No payment intent found for booking {booking.id} - cannot refund")
        return "pending"
    
    try:
        # Create refund for the payment intent
        refund = stripe.Refund.create(
            payment_intent=payment_intent_id,
            amount=amount_cents,
            metadata={
                "booking_id": str(booking.id),
                "reason": reason
            }
        )
        
        refund_status = refund.status  # 'succeeded' or 'pending'
        print(f"[Stripe] Refund created: {refund.id} - Status: {refund_status}")
        return str(refund_status)
        
    except Exception as e:
        # Generic error handling for all Stripe exceptions
        print(f"[Stripe] Error during refund: {str(e)}")
        return "error"
