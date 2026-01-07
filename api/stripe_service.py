"""
Stripe service for FastAPI
Sync Stripe operations - called via thread pool executor
"""
from typing import Optional, cast, Any
import stripe
from .models import Customer, PrintOrder
import os
import traceback
from decimal import Decimal
from .models import Invoice


def get_or_create_stripe_customer(customer: Customer) -> Optional[str]:
    """Get or create Stripe customer ID with full customer data for cross-referencing.
    
    Syncs customer info to Stripe metadata for dashboard visibility and lifecycle management.
    """
    STRIPE_ENABLED = os.getenv('STRIPE_ENABLED', 'false').lower() in {'1', 'true', 'yes'}
    
    print(f"[Stripe] get_or_create_stripe_customer: STRIPE_ENABLED={STRIPE_ENABLED}")
    print(f"[Stripe] get_or_create_stripe_customer: stripe.api_key={stripe.api_key[:20] if stripe.api_key else 'None'}...")
    
    if not STRIPE_ENABLED:
        print("[Stripe] STRIPE_ENABLED is false, returning None")
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
    # Build metadata dictionary with all customer info for Stripe dashboard cross-referencing
    metadata = {
        'customer_id': str(customer.id),
        'name': name,
        'phone': phone,
        'gdpr_consent': str(bool(customer.gdpr_consent)),
        'marketing_opt_in': str(bool(customer.marketing_opt_in)),
        'created_at': customer.created_at.isoformat() if getattr(customer, "created_at", None) else '',
    }
    
    try:
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
    except Exception as e:
        print(f"[Stripe] ERROR creating customer: {str(e)}")
        print(f"[Stripe] Exception type: {type(e).__name__}")
        import traceback
        print(f"[Stripe] Traceback: {traceback.format_exc()}")
        return None


def create_payment_link_for_order(order: PrintOrder, db_session, customer: Optional[Customer] = None) -> Optional[str]:
    """Create a Stripe payment link for print order with full metadata.
    
    Syncs order metadata to payment link and payment intent so Stripe dashboard
    shows order info, customer details, material, pricing, etc.
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
        # Get customer object if not provided
        if not customer and getattr(order, "customer_id", None):
            customer = db_session.query(Customer).filter_by(id=order.customer_id).first()
        
        # Ensure amount is an integer (in cents)
        unit_amount = int(getattr(order, "total_cents", 0))
        
        # Get material name for display
        material = getattr(order, "material", None)
        material_name = getattr(material, "name", "Unknown Material") if material else 'Unknown Material'
        
        # Build comprehensive product metadata
        product_metadata = {
            "order_id": str(order.id),
            "order_number": str(order.order_number or ''),
            "customer_id": str(order.customer_id),
            "payment_type": "order_payment",
            "material": material_name,
            "quantity": str(order.quantity or 1),
            "rush_order": str(bool(order.rush_order)),
            "volume_cm3": str(order.volume_cm3 or ''),
            "weight_g": str(order.weight_g or ''),
        }
        
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
            "name": f"3D Print Order - {material_name}",
            "metadata": product_metadata
        }
        # Add a short description into metadata for Stripe dashboard visibility
        product_data["metadata"]["product_description"] = f"Order #{order.order_number} - {order.model_filename or 'Model'}".strip()

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
            "order_id": str(order.id),
            "order_number": str(order.order_number or ''),
            "customer_id": str(order.customer_id),
            "payment_type": "order_payment",
            "material": material_name,
            "amount_cents": str(unit_amount),
        }
        
        if customer:
            link_metadata["customer_stripe_id"] = customer.stripe_customer_id or ''
        
        # Build payment intent data with metadata that flows to the resulting PaymentIntent
        scheduled_date = getattr(order, "scheduled_print_date", None)
        payment_intent_data = cast(Any, {
            "metadata": {
                "order_id": str(order.id),
                "order_number": str(order.order_number or ''),
                "customer_id": str(order.customer_id),
                "payment_type": "order_payment",
                "material": material_name,
                "delivery_zip": order.delivery_zip_code or '',
                "scheduled_date": scheduled_date.isoformat() if scheduled_date is not None else '',
            }
        })
        
        # Build redirect URL
        redirect_url = f"{PAYMENT_RETURN_URL}?order_id={order.id}&customer_id={order.customer_id}"

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
        
        print(f"[Stripe] Created payment link for order {order.order_number} with comprehensive metadata")
        return link.url
    except Exception as e:
        print(f"[Stripe] Failed to create payment link: {e}")
        return None


def create_payment_link_for_invoice(order: PrintOrder, invoice: Invoice) -> Optional[str]:
    """Create a Stripe payment link for an invoice payment with comprehensive metadata.
    
    Amount = invoice.total (full invoice amount)
    
    Syncs invoice and print order data to Stripe for cross-referencing, lifecycle tracking,
    and order fulfillment.
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
        # Get customer and material for metadata
        customer = order.customer if hasattr(order, 'customer') else None
        material = order.material if hasattr(order, 'material') else None
        
        total_dec = Decimal(getattr(invoice, 'total', 0) or 0)
        total_cents = int(Decimal('100') * total_dec)

        # If total is zero, skip payment link
        if total_cents <= 0:
            print(f"[Stripe] Total is {total_cents} cents; skipping payment link creation")
            return None

        # Build comprehensive product metadata
        invoice_number = str(getattr(invoice, 'invoice_number', ''))
        work_performed = str(getattr(invoice, 'work_performed', 'Custom print order'))[:200]
        
        product_metadata = {
            "order_id": str(order.id),
            "order_number": order.order_number or str(order.id),
            "customer_id": str(order.customer_id),
            "invoice_id": str(getattr(invoice, 'id', '')),
            "invoice_number": invoice_number,
            "payment_type": "invoice",
            "material": material.name if material else 'Unknown',
            "volume_cm3": str(order.volume_cm3 or 0),
            "weight_g": str(order.weight_g or 0),
            "quantity": str(order.quantity or 1),
            "delivery_zip": order.delivery_zip_code or '',
            "subtotal": str(getattr(invoice, 'subtotal', 0)),
            "tax": str(getattr(invoice, 'tax', 0)),
            "total": str(total_dec),
        }
        
        if customer:
            product_metadata.update({
                "customer_name": customer.name or '',
                "customer_email": customer.email or '',
                "customer_phone": customer.phone or '',
            })
        
        # Create Price with detailed product data
        product_metadata["product_description"] = f"Order {order.order_number} - {work_performed}".strip()
        
        price = stripe.Price.create(
            unit_amount=total_cents,
            currency=CURRENCY,
            product_data={
                "name": f"Invoice #{invoice_number} - {material.name if material else 'Print Order'} Total",
                "metadata": product_metadata
            },
        )

        # Build payment link metadata
        link_metadata = {
            "order_id": str(order.id),
            "order_number": order.order_number or str(order.id),
            "invoice_id": str(getattr(invoice, 'id', '')),
            "invoice_number": invoice_number,
            "type": "invoice_payment",
            "customer_id": str(order.customer_id),
            "amount_cents": str(total_cents),
        }
        
        if customer and customer.stripe_customer_id:
            link_metadata["customer_stripe_id"] = customer.stripe_customer_id
        
        # Build payment intent data with full invoice/order context
        payment_intent_data = {
            "metadata": {
                "order_id": str(order.id),
                "order_number": order.order_number or str(order.id),
                "customer_id": str(order.customer_id),
                "invoice_id": str(getattr(invoice, 'id', '')),
                "invoice_number": invoice_number,
                "payment_type": "invoice",
                "material": material.name if material else 'Unknown',
                "delivery_address": order.delivery_address or '',
                "delivery_zip": order.delivery_zip_code or '',
                "quantity": str(order.quantity or 1),
                "total": str(total_dec),
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
        
        redirect_url = f"{PAYMENT_RETURN_URL}?order_id={order.id}&customer_id={order.customer_id}"
        
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


def create_stripe_invoice_from_pdf(order: PrintOrder, invoice: Invoice, pdf_bytes: bytes, db_session=None) -> Optional[str]:
    """Create a Stripe invoice from generated PDF.
    
    Creates an invoice in Stripe with comprehensive metadata and line items for tracking and disputes.
    
    The PDF is NOT uploaded to Stripe (no appropriate File API purpose for invoices).
    Instead, the PDF should be emailed to the customer by the caller along with a Payment Intent link.
    
    Args:
        order: The print order associated with the invoice
        invoice: The invoice object
        pdf_bytes: PDF file contents as bytes (for email delivery by caller)
        db_session: Database session (for future extensibility)
    
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
        customer = order.customer if hasattr(order, 'customer') else None
        if not customer or not customer.stripe_customer_id:
            print(f"[Stripe] No Stripe customer found for order {order.id} - skipping invoice creation")
            return None
        
        # Update Stripe customer with delivery address from order if available
        delivery_address = getattr(order, 'delivery_address', '')
        if delivery_address:
            print(f"[Stripe] Updating customer with delivery address: {delivery_address}")
            try:
                stripe.Customer.modify(
                    customer.stripe_customer_id,
                    address={
                        "line1": delivery_address[:100],  # Truncate to Stripe's limit
                        "postal_code": getattr(order, "delivery_zip_code", ''),
                        "country": "US"  # Default to US, can be made configurable
                    }
                )
                print(f"[Stripe] Updated customer address")
            except Exception as addr_err:
                print(f"[Stripe] Warning: Could not update customer address: {addr_err}")
        
        # Build invoice metadata for tracking
        invoice_number = str(getattr(invoice, 'invoice_number', ''))
        material = order.material if hasattr(order, 'material') else None
        material_name = material.name if material else 'Unknown'
        total_due_dec = Decimal(getattr(invoice, 'total_cents', 0) or 0) / 100
        
        invoice_metadata = {
            "order_id": str(order.id),
            "order_number": str(order.order_number or ''),
            "invoice_id": str(getattr(invoice, 'id', '')),
            "invoice_number": invoice_number,
            "model_filename": order.model_filename or '',
            "material": material_name,
            "quantity": str(order.quantity or 1),
            "volume_cm3": str(order.volume_cm3 or ''),
            "weight_g": str(order.weight_g or ''),
            "total_due": str(total_due_dec),
            "currency": CURRENCY,
        }
        
        print(f"[Stripe] Creating invoice for order {order.order_number}")
        print(f"[Stripe] Invoice number: {invoice_number}")
        print(f"[Stripe] Customer: {customer.stripe_customer_id}")
        print(f"[Stripe] Total due: {total_due_dec}")
        
        # Create Stripe invoice with auto_advance=False so we control when it's sent
        stripe_invoice = stripe.Invoice.create(
            customer=customer.stripe_customer_id,
            metadata=invoice_metadata,
            description=f"Print Order Invoice {invoice_number}",
            auto_advance=False  # Don't auto-finalize; we'll do it manually
        )
        print(f"[Stripe] Created invoice: {stripe_invoice.id}")
        
        # Add single line item with total amount
        total_due_cents = int(Decimal(str(getattr(invoice, 'total_cents', 0) or 0)))
        if total_due_cents > 0:
            print(f"[Stripe] Adding line item with total: {total_due_dec} USD ({total_due_cents} cents)")
            
            stripe.InvoiceItem.create(
                customer=customer.stripe_customer_id,
                amount=total_due_cents,
                currency=CURRENCY,
                description=f"3D Print - {getattr(order, 'model_filename', '')[:50] if getattr(order, 'model_filename', 'Model') else 'Model'}",
                invoice=stripe_invoice.id
            )
            print(f"[Stripe] Added invoice line item")
        
        
        # Store the Stripe invoice ID in our database for reference
        setattr(invoice, 'stripe_invoice_id', stripe_invoice.id)
        print(f"[Stripe] Successfully created Stripe invoice {stripe_invoice.id} for order {order.order_number}")
        
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


def process_stripe_refund(order: PrintOrder, amount_cents: int, reason: str) -> str:
    """
    Process a Stripe refund for a print order.
    
    Args:
        order: The print order associated with the payment
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
    
    # Check if order has a payment intent
    payment_intent_id = getattr(order, 'stripe_payment_intent_id', None)
    
    if not payment_intent_id:
        print(f"[Stripe] No payment intent found for order {order.order_number} - cannot refund")
        return "pending"
    
    try:
        # Create refund for the payment intent
        refund = stripe.Refund.create(
            payment_intent=payment_intent_id,
            amount=amount_cents,
            metadata={
                "order_id": str(order.id),
                "order_number": str(order.order_number or ''),
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
