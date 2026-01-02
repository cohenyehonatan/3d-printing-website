"""
Database models using SQLAlchemy (not Flask-SQLAlchemy for FastAPI compatibility)
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Date, ForeignKey, JSON, Numeric, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime, date
from typing import Union, Optional, Literal
from pydantic import BaseModel
from pydantic.config import ConfigDict

Base = declarative_base()

# For backwards compatibility with Flask imports
db = None  # Will be set by Flask app if used

# Database Models
class Customer(Base):
    __tablename__ = 'customers'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    phone = Column(String(50))
    preferred_language = Column(String(5), default='en')  # 'en' or 'de'
    stripe_customer_id = Column(String(100))
    gdpr_consent = Column(Boolean, default=False)
    gdpr_consent_date = Column(DateTime)
    marketing_opt_in = Column(Boolean, default=False)
    has_account = Column(Boolean, default=False)  # True if customer has created a login account
    account_created_at = Column(DateTime)  # When customer opted into account
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    vehicles = relationship('Vehicle', back_populates='owner', lazy=True)
    bookings = relationship('Booking', back_populates='customer', lazy=True)


class Vehicle(Base):
    __tablename__ = 'vehicles'
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False)
    vin = Column(String(17), unique=True, nullable=False)
    year = Column(Integer)
    make = Column(String(100))
    model = Column(String(100))
    vehicle_data = Column(JSON)  # Store full Mercedes API response
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    owner = relationship('Customer', back_populates='vehicles')
    bookings = relationship('Booking', back_populates='vehicle', lazy=True)
    service_history = relationship('ServiceHistory', back_populates='vehicle', lazy=True)


class Booking(Base):
    __tablename__ = "bookings"
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    vehicle_id = Column(Integer, ForeignKey('vehicles.id'), nullable=False)
    service_type = Column(Text, nullable=False)  # Changed from String(255)
    service_description = Column(Text, nullable=True)  # Changed from String(255)
    location_type = Column(String(50))  # 'home' or 'work'
    service_address = Column(Text)
    license_plate = Column(String(50))
    preferred_date = Column(Date)
    scheduled_datetime = Column(DateTime)
    completion_date = Column(Date)
    status = Column(String(50), default='pending')  # pending, confirmed, paid, completed, cancelled
    payment_status = Column(String(50), default='unpaid')  # unpaid, pending, paid, refunded
    payment_method = Column(String(50))
    payment_link_url = Column(String(500))
    stripe_payment_intent_id = Column(String(100))
    visit_fee_amount = Column(Integer)  # in cents
    visit_fee_paid = Column(Boolean, default=False)
    visit_fee_stripe_link = Column(String(500))
    location_zone = Column(String(50))  # e.g. 'zone_1', 'zone_2'
    same_day_surcharge = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)  # Also change this if it's String(255)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    fdacs_registration_displayed = Column(Boolean, default=False)  # Track compliance
    current_odometer = Column(Integer)
    estimate_choice = Column(String(20))
    estimate_cost_limit = Column(Numeric(10, 2), nullable=True)
    pricing_method = Column(String(20))
    alternate_contact_name = Column(String(255), nullable=True)
    alternate_contact_phone = Column(String(50), nullable=True)
    parts_disposition = Column(String(20))
    # AI-derived booking severity (0-100) and short rationale/label
    severity_score = Column(Integer)  # nullable; computed via AI
    severity_summary = Column(Text, nullable=True)  # And this one

    # New fields for confirmation fee
    confirmation_fee_amount = Column(Integer, default=14400)  # cents
    confirmation_fee_paid = Column(Boolean, default=False)
    confirmation_fee_payment_id = Column(String(255))  # Stripe payment ID
    confirmation_fee_paid_date = Column(DateTime)

    # Relationships
    customer = relationship('Customer', back_populates='bookings')
    vehicle = relationship('Vehicle', back_populates='bookings')
    service_history = relationship('ServiceHistory', back_populates='booking', lazy=True, uselist=False)
    line_items = relationship('LineItem', back_populates='booking', lazy=True)
    invoices = relationship('Invoice', back_populates='booking', lazy=True)

    def __init__(
        self,
        customer_id: int,
        vehicle_id: int,
        service_type: str,
        service_description: str = "",
        location_type: Union[str, None] = None,
        service_address: str = "",
        preferred_date: Union[date, None] = None,
        status: str = "pending",
        payment_status: str = "unpaid",
        deposit_amount: Union[int, None] = None,
        visit_fee_amount: Union[int, None] = None,
        visit_fee_paid: bool = False,
        location_zone: Union[str, None] = None,
        same_day_surcharge: bool = False,
        notes: str = ""
    ) -> None:
        # Assign provided values to the model fields
        self.customer_id = customer_id
        self.vehicle_id = vehicle_id
        self.service_type = service_type
        self.service_description = service_description
        self.location_type = location_type
        self.service_address = service_address
        self.preferred_date = preferred_date
        self.status = status
        self.payment_status = payment_status
        self.deposit_amount = deposit_amount
        self.visit_fee_amount = visit_fee_amount
        self.visit_fee_paid = visit_fee_paid
        self.location_zone = location_zone
        self.same_day_surcharge = same_day_surcharge
        self.notes = notes


class ServiceHistory(Base):
    __tablename__ = 'service_history'
    
    id = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey('bookings.id'), nullable=False)
    vehicle_id = Column(Integer, ForeignKey('vehicles.id'), nullable=False)
    service_date = Column(DateTime)
    services_performed = Column(ARRAY(String))  # PostgreSQL array
    parts_used = Column(JSON)
    labor_hours = Column(Numeric(5, 2))
    total_cost = Column(Numeric(10, 2))
    technician_notes = Column(Text)
    customer_signature = Column(Text)  # base64 image
    dsb_updated = Column(Boolean, default=False)  # Digital Service Booklet
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    booking = relationship('Booking', back_populates='service_history')
    vehicle = relationship('Vehicle', back_populates='service_history')


class LineItem(Base):
    __tablename__ = 'line_items'

    id = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey('bookings.id'), nullable=False)
    description = Column(String(255), nullable=False)
    part_type = Column(String(50), nullable=True)
    quantity = Column(Numeric(10, 2), nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    total = Column(Numeric(12, 2), nullable=False)
    warranty_covered = Column(Boolean, default=False)
    reduced_cost = Column(Boolean, default=False)
    # NEW: item_category distinguishes customer-pay from warranty/recall/goodwill
    # Values: 'customer_pay', 'warranty', 'recall', 'goodwill'
    # These warranty/recall/goodwill items do NOT affect customer's subtotal/tax/deposit
    item_category = Column(String(20), default='customer_pay')

    booking = relationship('Booking', back_populates='line_items')


class Invoice(Base):
    __tablename__ = 'invoices'

    id = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey('bookings.id'), nullable=False)
    invoice_number = Column(String(100), unique=True, nullable=False)
    invoice_date = Column(DateTime, default=datetime.utcnow)
    current_odometer = Column(Integer)
    work_performed = Column(Text)
    subtotal = Column(Numeric(12, 2))
    tax_rate = Column(Numeric(5, 4))
    tax_amount = Column(Numeric(12, 2))
    total_due = Column(Numeric(12, 2))
    tire_fee_count = Column(Integer, default=0)
    battery_fee_count = Column(Integer, default=0)
    shop_supplies_charge = Column(Numeric(12, 2), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_finalized = Column(Boolean, default=False)
    finalized_at = Column(DateTime, nullable=True)
    pdf_generated = Column(Boolean, default=False)
    pdf_generated_at = Column(DateTime, nullable=True)
    # Generated plain-text work order / invoice for quick download or embedding
    work_order_text = Column(Text, nullable=True)
    # Stripe invoice tracking
    stripe_invoice_id = Column(String(255), nullable=True)
    
    # Audit trail
    created_by = Column(String(100))
    last_modified_by = Column(String(100))
    last_modified_at = Column(DateTime, onupdate=datetime.utcnow)

    booking = relationship('Booking', back_populates='invoices')


class InvoiceAuditLog(Base):
    """Track all invoice changes."""
    __tablename__ = 'invoice_audit_log'
    
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey('invoices.id'), nullable=False)
    changed_by = Column(String(100), nullable=False)
    change_type = Column(String(50))  # 'created', 'edited', 'finalized', 'voided'
    field_name = Column(String(100))
    old_value = Column(Text)
    new_value = Column(Text)
    changed_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text)


class CreditMemo(Base):
    """For refunds/adjustments instead of editing invoices."""
    __tablename__ = 'credit_memos'
    
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey('invoices.id'), nullable=False)
    credit_memo_number = Column(String(100), unique=True, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    reason = Column(Text, nullable=False)
    created_by = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class WaiverSignature(Base):
    __tablename__ = "waiver_signatures"

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    
    version = Column(String(50), nullable=False)            # e.g. "v1.0"
    document_html = Column(Text, nullable=False)            # full HTML snapshot
    document_pdf_path = Column(String(500))                 # optional: where PDF is stored
    
    signature_value = Column(Text, nullable=False)          # base64 or typed signature
    signature_method = Column(String(50))                   # typed/drawn/stored etc.
    
    signed_at = Column(DateTime, default=datetime.utcnow)
    ip_address = Column(String(100))
    user_agent = Column(Text)

    # Relationship
    customer = relationship("Customer", backref="waiver_signatures")


class WorkOrderSignature(Base):
    __tablename__ = "work_order_signatures"

    id = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)

    version = Column(String(50), nullable=False)
    document_html = Column(Text, nullable=False)
    document_pdf_path = Column(String(500))

    signature_value = Column(Text, nullable=False)
    signature_method = Column(String(50))

    signed_at = Column(DateTime, default=datetime.utcnow)
    ip_address = Column(String(100))
    user_agent = Column(Text)

    # Relations
    booking = relationship("Booking", backref="work_order_signature")
    customer = relationship("Customer")


class ESignConsent(Base):
    __tablename__ = "esign_consents"

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True)  # Optional context
    
    document_type = Column(String(50), nullable=False)  # 'agreement' or 'work-order'
    consent_version = Column(String(50), default='v1.0')
    
    consented_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ip_address = Column(String(100))
    user_agent = Column(Text)
    
    # Relations
    customer = relationship("Customer", backref="esign_consents")
    booking = relationship("Booking", backref="esign_consents")


class SignatureData(BaseModel):
    type: Literal["agreement", "work-order"]
    booking_id: Optional[int] = None
    job_id: Optional[int] = None
    customer_id: Optional[int] = None
    signature_value: str
    signature_method: str = "drawn"
    document_html: Optional[str] = None
    document_version: str = "v1.0"
    # Additional structured fields submitted from rich forms (e.g., work-order)
    form_data: Optional[dict] = None

    model_config = ConfigDict(extra="ignore")


class ZipLookupResponse(BaseModel):
    """Response model for ZIP code lookup."""
    success: bool
    city_states: Optional[list] = None
    zipcode: Optional[str] = None
    default_city: Optional[str] = None
    county: Optional[str] = None
    state: Optional[str] = None
    error: Optional[str] = None