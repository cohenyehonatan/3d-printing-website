"""
Database models for 3D Printing Service using SQLAlchemy
(Not Flask-SQLAlchemy for FastAPI compatibility)
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Float, ForeignKey, Numeric
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel
from pydantic.config import ConfigDict

Base = declarative_base()

# For backwards compatibility with Flask imports
db = None  # Will be set by Flask app if used


# ============================================================================
# DATABASE MODELS
# ============================================================================

class Customer(Base):
    """Customers who order 3D prints"""
    __tablename__ = 'customers'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    phone = Column(String(50))
    stripe_customer_id = Column(String(100))
    
    # Consent tracking
    gdpr_consent = Column(Boolean, default=False)
    gdpr_consent_date = Column(DateTime)
    marketing_opt_in = Column(Boolean, default=False)
    
    # Account management
    has_account = Column(Boolean, default=False)
    account_created_at = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    print_orders = relationship('PrintOrder', back_populates='customer', lazy=True)
    quotes = relationship('Quote', back_populates='customer', lazy=True)
    waiver_signatures = relationship('WaiverSignature', back_populates='customer', lazy=True)
    esign_consents = relationship('ESignConsent', back_populates='customer', lazy=True)


class Material(Base):
    """Available 3D printing materials/filaments"""
    __tablename__ = 'materials'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)  # e.g., "PLA Basic", "PETG HF"
    description = Column(Text)
    
    # Material properties
    density_g_per_cm3 = Column(Float, nullable=False)  # For weight calculation
    price_per_kg = Column(Numeric(10, 2), nullable=False)  # Cost per kg
    
    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    print_orders = relationship('PrintOrder', back_populates='material', lazy=True)


class Quote(Base):
    """Saved quotes for customers"""
    __tablename__ = 'quotes'
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=True)  # May be anonymous
    
    # Model details
    model_filename = Column(String(255))
    volume_cm3 = Column(Float)  # Model volume in cubic centimeters
    weight_g: Mapped[float] = mapped_column(Float)  # Model weight in grams
    
    # Material and options
    material_id = Column(Integer, ForeignKey('materials.id'))
    quantity = Column(Integer, default=1)
    rush_order = Column(Boolean, default=False)
    zip_code = Column(String(10))  # For tax calculation
    
    # Cost breakdown
    base_cost_cents = Column(Integer)  # Fixed setup cost
    material_cost_cents = Column(Integer)
    shipping_cost_cents = Column(Integer)
    rush_surcharge_cents = Column(Integer, default=0)
    subtotal_cents = Column(Integer)
    tax_cents = Column(Integer)
    total_cents = Column(Integer)
    tax_rate = Column(Numeric(5, 4))  # e.g., 0.0850
    
    # Quote status
    is_used = Column(Boolean, default=False)  # True if converted to an order
    expires_at = Column(DateTime)  # Quote expiration
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    customer = relationship('Customer', back_populates='quotes')
    material = relationship('Material')
    print_order = relationship('PrintOrder', back_populates='quote', uselist=False)


class PrintOrder(Base):
    """A customer's 3D print order"""
    __tablename__ = 'print_orders'
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False)
    material_id = Column(Integer, ForeignKey('materials.id'), nullable=False)
    quote_id = Column(Integer, ForeignKey('quotes.id'), nullable=True)
    
    # Order details
    order_number = Column(String(50), unique=True, nullable=False)  # e.g., "ORD-20260102-001"
    model_filename = Column(String(255), nullable=False)
    
    # Model specifications
    volume_cm3 = Column(Float, nullable=False)
    weight_g = Column(Float, nullable=False)
    quantity = Column(Integer, default=1)
    
    # Model dimensions (in mm) for packing optimization
    model_length_mm = Column(Float)  # X dimension
    model_width_mm = Column(Float)   # Y dimension
    model_height_mm = Column(Float)  # Z dimension
    
    # Options
    rush_order = Column(Boolean, default=False)
    
    # Delivery Address (for Click-N-Ship)
    delivery_zip_code = Column(String(10), nullable=False)
    delivery_address = Column(Text)
    delivery_first_name = Column(String(100))
    delivery_middle_initial = Column(String(2))
    delivery_last_name = Column(String(100))
    delivery_company = Column(String(100))
    delivery_street = Column(String(255))
    delivery_apt_suite = Column(String(100))
    delivery_city = Column(String(100))
    delivery_state = Column(String(2))
    delivery_country = Column(String(100), default='United States of America')
    delivery_email = Column(String(255))
    delivery_phone = Column(String(20))
    
    # Shipping Label Info
    ship_date = Column(DateTime)  # When label was/will be created
    reference_number_1 = Column(String(30))
    reference_number_2 = Column(String(30))
    shipping_cost_cents = Column(Integer)
    shipping_zone = Column(Integer)
    shipping_weight_g: Mapped[float | None] = mapped_column(Float)
    
    # Carrier scan tracking (immutable once set)
    first_carrier_scan_at = Column(DateTime, nullable=True)  # When UPS first scanned package - hard lock on regeneration
    
    # Content & Packaging
    packaging_type = Column(String(50))  # e.g., "USPS Small Priority Box", "Custom"
    contains_hazmat = Column(Boolean, default=False)
    contains_live_animals = Column(Boolean, default=False)
    contains_perishable = Column(Boolean, default=False)
    contains_cremated_remains = Column(Boolean, default=False)
    package_value_cents = Column(Integer)  # For insurance (defaults to order total)
    
    # Shipping/Billing Options
    selected_service = Column(String(100))  # e.g., "Priority Mail Express", "Ground Advantage"
    billing_option = Column(String(2), default='01')  # 01=BillShipper, 02=BillReceiver, 03=BillThirdParty, 04=ConsigneeBilled
    label_status = Column(String(50), default='pending')  # pending, created, printed, shipped
    usps_tracking_number = Column(String(100))
    ups_tracking_number = Column(String(100))
    ups_shipment_id = Column(String(100))
    ups_label_image = Column(Text)
    ups_label_image_format = Column(String(10))
    label_created_at = Column(DateTime)
    
    # Pricing
    subtotal_cents = Column(Integer)  # Before tax
    tax_cents = Column(Integer)
    total_cents = Column(Integer)  # After tax
    tax_rate = Column(Numeric(5, 4))
    
    # Payment
    payment_status = Column(String(50), default='unpaid')  # unpaid, pending, paid, refunded
    stripe_payment_intent_id = Column(String(100))
    stripe_payment_link = Column(String(500))
    stripe_session_id = Column(String(100))
    payment_link_url = Column(String(500))
    paid_at = Column(DateTime)
    
    # Order status
    order_status = Column(String(50), default='pending')  # pending, confirmed, printing, completed, cancelled
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    scheduled_print_date = Column(DateTime)
    estimated_completion_date = Column(DateTime)
    completed_at = Column(DateTime)
    
    # Additional notes
    special_instructions = Column(Text)
    
    # Relationships
    customer = relationship('Customer', back_populates='print_orders')
    material = relationship('Material', back_populates='print_orders')
    quote = relationship('Quote', back_populates='print_order')
    print_job = relationship('PrintJob', back_populates='print_order', uselist=False)
    invoice = relationship('Invoice', back_populates='print_order', uselist=False)


class PrintJob(Base):
    """Tracks the printing progress of an order"""
    __tablename__ = 'print_jobs'
    
    id = Column(Integer, primary_key=True)
    print_order_id = Column(Integer, ForeignKey('print_orders.id'), nullable=False)
    
    # Job status
    status = Column(String(50), default='queued')  # queued, printing, paused, completed, failed, cancelled
    
    # Printer assignment
    printer_name = Column(String(100))  # e.g., "Bambu Lab X1 #1"
    
    # Timing
    queued_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    paused_at = Column(DateTime)
    completed_at = Column(DateTime)
    estimated_duration_minutes = Column(Integer)  # Estimated print time
    
    # Progress tracking
    progress_percent = Column(Integer, default=0)  # 0-100
    
    # Quality/issues
    notes = Column(Text)  # Any issues or notes during printing
    failed_reason = Column(String(255))  # If status is 'failed'
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    print_order = relationship('PrintOrder', back_populates='print_job')


class Invoice(Base):
    """Invoice for a completed order"""
    __tablename__ = 'invoices'
    
    id = Column(Integer, primary_key=True)
    print_order_id = Column(Integer, ForeignKey('print_orders.id'), nullable=False)
    
    invoice_number = Column(String(100), unique=True, nullable=False)  # e.g., "INV-20260102-001"
    invoice_date = Column(DateTime, default=datetime.utcnow)
    
    # Order summary on invoice
    model_filename = Column(String(255))
    material_name = Column(String(100))
    quantity = Column(Integer)
    volume_cm3 = Column(Float)
    weight_g: Mapped[float] = mapped_column(Float)
    
    # Pricing breakdown
    subtotal_cents = Column(Integer)
    tax_cents = Column(Integer)
    total_cents = Column(Integer)
    tax_rate = Column(Numeric(5, 4))
    
    # Invoice metadata
    is_finalized = Column(Boolean, default=False)
    finalized_at = Column(DateTime)
    pdf_generated = Column(Boolean, default=False)
    pdf_path = Column(String(500))
    pdf_generated_at = Column(DateTime)
    
    # Stripe tracking
    stripe_invoice_id = Column(String(255))
    
    # Audit trail
    created_by = Column(String(100))
    last_modified_by = Column(String(100))
    last_modified_at = Column(DateTime, onupdate=datetime.utcnow)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    print_order = relationship('PrintOrder', back_populates='invoice')


class WaiverSignature(Base):
    """E-signature for waivers/terms"""
    __tablename__ = 'waiver_signatures'
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False)
    
    version = Column(String(50), nullable=False)  # e.g., "v1.0"
    document_html = Column(Text, nullable=False)  # HTML snapshot of document
    document_pdf_path = Column(String(500))  # Optional PDF storage path
    
    signature_value = Column(Text, nullable=False)  # base64 or typed signature
    signature_method = Column(String(50))  # typed, drawn, stored, etc.
    
    signed_at = Column(DateTime, default=datetime.utcnow)
    ip_address = Column(String(100))
    user_agent = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    customer = relationship('Customer', back_populates='waiver_signatures')




class ESignConsent(Base):
    """ESIGN compliance record"""
    __tablename__ = 'esign_consents'
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False)
    print_order_id = Column(Integer, ForeignKey('print_orders.id'), nullable=True)
    
    document_type = Column(String(50), nullable=False)  # e.g., 'agreement', 'work-order'
    consent_version = Column(String(50), default='v1.0')
    
    consented_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ip_address = Column(String(100))
    user_agent = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    customer = relationship('Customer', back_populates='esign_consents')


# ============================================================================
# PYDANTIC MODELS (for request/response validation)
# ============================================================================

class SignatureData(BaseModel):
    """Signature submission data"""
    type: Literal["agreement", "work-order"]
    print_order_id: Optional[int] = None
    customer_id: Optional[int] = None
    signature_value: str
    signature_method: str = "drawn"
    document_html: Optional[str] = None
    document_version: str = "v1.0"
    form_data: Optional[dict] = None

    model_config = ConfigDict(extra="ignore")


class MaterialResponse(BaseModel):
    """Material info response"""
    id: int
    name: str
    description: Optional[str]
    density_g_per_cm3: float
    price_per_kg: float
    is_active: bool


class QuoteResponse(BaseModel):
    """Quote response"""
    total_cost_with_tax: str
    sales_tax: str
    base_cost: str
    material_cost: str
    shipping_cost: str
    rush_order_surcharge: str


class PrintOrderResponse(BaseModel):
    """Print order response"""
    order_id: int
    order_number: str
    payment_url: Optional[str]
    total_amount_cents: int
    status: str


class PrintJobStatusResponse(BaseModel):
    """Print job status"""
    job_id: int
    order_number: str
    status: str
    progress_percent: int
    estimated_completion_date: Optional[str]
    estimated_duration_minutes: Optional[int]
