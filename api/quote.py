import io
import json
import logging
import trimesh
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
import os
from .sales_tax_rates import sales_tax_rates
from .zip_to_state import get_state_from_zip
from . import stripe_service

logging.basicConfig(level=logging.DEBUG)

app = FastAPI(title="3D Print Quote API", max_body_size=100*1024*1024)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Increase max request body size to 100MB by updating Starlette's defaults
app.add_middleware = lambda middleware, **kwargs: None  # Placeholder, handled by Uvicorn config

MINIMUM_WEIGHT_G = 0.1  # Minimum weight in grams (adjust as needed)

base_cost = 20

# Maximum file size (16 MB)
MAX_FILE_SIZE = 16 * 1024 * 1024

# Updated filament prices for Bambu Lab
filament_prices = {
    "PLA Basic": 19.99,
    "PLA Matte": 19.99,
    "PETG HF": 19.99,
    "PETG Basic": 19.99,
    # Add more filaments as needed...
}

# Material densities in g/cm³ (approximate values)
material_densities = {
    "PLA Basic": 1.24,
    "PLA Matte": 1.24,
    "PETG HF": 1.27,
    # Add more filament types and their densities as needed
}

# Function to calculate total cost with sales tax
def calculate_total_with_tax(zip_code, total_cost, tax_rates, get_state_from_zip):
    # Get the state based on the ZIP code
    state = get_state_from_zip(zip_code)
    
    # Ensure we have a valid state
    if state:
        # Look up the sales tax rate for the state
        sales_tax_rate = tax_rates.get(state, 0)
        
        # Calculate sales tax
        sales_tax = sales_tax_rate * total_cost
        
        # Add sales tax to the total cost
        total_with_tax = total_cost + sales_tax
        return total_with_tax, sales_tax
    else:
        # If no state is found, return the original cost with no tax
        return total_cost, 0

# Function to calculate the total material weight
def calculate_weight(volume_cm3, density_g_per_cm3):
    return volume_cm3 * density_g_per_cm3  # Weight in grams

# Function to estimate packaging weight
def estimate_packaging_weight(model_weight):
    return model_weight * 0.15

# Function to calculate total weight for shipping
def calculate_total_weight(volume_cm3, density_g_per_cm3):
    model_weight = calculate_weight(volume_cm3, density_g_per_cm3)
    packaging_weight = estimate_packaging_weight(model_weight)
    return (model_weight + packaging_weight) / 1000  # Convert to kg

# Function to check the size of the model
def check_model_size(model_dimensions):
    standard_max = 250  # Max size for standard builds
    full_volume_max = 256  # Max size for full-volume builds
    x, y, z = model_dimensions
    if x > full_volume_max or y > full_volume_max or z > full_volume_max:
        return "too_large", {}
    if x > standard_max or y > standard_max or z > standard_max:
        return "full_volume", {}
    return "standard", {}

# USPS shipping calculation function (simplified)
def calculate_usps_shipping(zip_code, weight_kg, express=False, connect_local=False):
    weight_lbs = weight_kg * 2.20462  # Convert kg to lbs
    return 7.90  # Example rate


# Request models for type validation
class QuoteRequest(BaseModel):
    zip_code: str
    filament_type: str
    quantity: int = 1
    rush_order: bool = False
    use_usps_connect_local: bool = False
    volume: float = 0
    weight: float = 0


class QuoteResponse(BaseModel):
    total_cost_with_tax: str
    sales_tax: str
    base_cost: str
    material_cost: str
    shipping_cost: str
    rush_order_surcharge: str


class VerifyFileResponse(BaseModel):
    volume: float
    bounding_box: dict
    is_watertight: bool


class CheckoutRequest(BaseModel):
    """Request to create a payment link for a print order"""
    email: str
    name: str
    phone: str
    zip_code: str
    filament_type: str
    quantity: int = 1
    rush_order: bool = False
    use_usps_connect_local: bool = False
    volume: float = 0
    weight: float = 0


class CheckoutResponse(BaseModel):
    """Response with Stripe payment link"""
    payment_url: str
    total_amount_cents: int


@app.post('/api/quote', response_model=QuoteResponse)
async def quote(request_data: QuoteRequest):
    """Calculate quote based on model specifications"""
    try:
        zip_code = request_data.zip_code
        filament_type = request_data.filament_type
        quantity = request_data.quantity
        rush_order = request_data.rush_order
        client_volume = request_data.volume
        client_weight = request_data.weight
        
        # Validate inputs
        if not zip_code or not filament_type:
            raise HTTPException(status_code=400, detail="Missing required fields")

        # Check if the filament type is valid
        if filament_type not in material_densities or filament_type not in filament_prices:
            raise HTTPException(status_code=400, detail="Invalid filament type")

        # Use client estimate or recalculate from density
        density = material_densities[filament_type]
        
        if client_weight > 0:
            total_weight_g = client_weight
        else:
            total_weight_g = max(client_volume * density, MINIMUM_WEIGHT_G)
        
        total_weight_kg = total_weight_g / 1000  # Convert to kg

        # Calculate material cost
        total_material_cost = total_weight_kg * filament_prices[filament_type] * quantity

        # Rush order surcharge
        rush_order_surcharge = 20 if rush_order else 0

        # Shipping cost based on weight
        shipping_weight = (total_weight_g + (total_weight_g * 0.15)) / 1000  # Add packaging
        shipping_cost = calculate_usps_shipping(zip_code, shipping_weight, express=rush_order, connect_local=request_data.use_usps_connect_local)

        # Total cost before tax
        total_cost_before_tax = (base_cost + total_material_cost) * quantity + shipping_cost + rush_order_surcharge

        # Calculate total cost with tax
        total_with_tax, sales_tax = calculate_total_with_tax(zip_code, total_cost_before_tax, sales_tax_rates, get_state_from_zip)

        # Prepare the response
        response_data = {
            'total_cost_with_tax': f"${total_with_tax:.2f}",
            'sales_tax': f"${sales_tax:.2f}",
            'base_cost': f"${base_cost:.2f}",
            'material_cost': f"${total_material_cost:.2f}",
            'shipping_cost': f"${shipping_cost:.2f}",
            'rush_order_surcharge': f"${rush_order_surcharge:.2f}"
        }

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error occurred: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/api/verify-file', response_model=VerifyFileResponse)
async def verify_file(file: UploadFile = File(...)):
    """Server-side verification of STL file using trimesh"""
    try:
        # Check file size
        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large. Maximum file size is 16MB.")
        
        # Read file into memory
        file_buffer = io.BytesIO(contents)
        
        # Load the 3D model using trimesh
        try:
            mesh = trimesh.load(file_buffer, file.filename)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to load 3D model: {str(e)}")
        
        # Calculate the volume and bounding box
        volume_cm3 = mesh.volume / 1000  # Convert from mm³ to cm³
        bounding_box = mesh.bounding_box.extents  # Dimensions (x, y, z)
        
        response_data = {
            'volume': volume_cm3,
            'bounding_box': {
                'x': bounding_box[0],
                'y': bounding_box[1],
                'z': bounding_box[2]
            },
            'is_watertight': bool(mesh.is_watertight)
        }
        
        return response_data
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error verifying file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/api/checkout', response_model=CheckoutResponse)
async def checkout(request_data: CheckoutRequest):
    """Create a Stripe payment link for a 3D print order"""
    try:
        # Validate inputs
        if not all([request_data.email, request_data.name, request_data.zip_code, request_data.filament_type]):
            raise HTTPException(status_code=400, detail="Missing required fields")

        # Calculate the quote to get total amount
        quote_request = QuoteRequest(
            zip_code=request_data.zip_code,
            filament_type=request_data.filament_type,
            quantity=request_data.quantity,
            rush_order=request_data.rush_order,
            use_usps_connect_local=request_data.use_usps_connect_local,
            volume=request_data.volume,
            weight=request_data.weight
        )
        
        quote_response = await quote(quote_request)
        
        # Extract total amount (remove $ and convert to cents)
        total_amount_str = quote_response.total_cost_with_tax.replace('$', '').replace(',', '')
        total_amount_float = float(total_amount_str)
        total_amount_cents = int(total_amount_float * 100)
        
        # Create a temporary customer object for Stripe
        # Note: In production, you'd save this to a database first
        from .models import Customer
        customer = Customer(
            name=request_data.name,
            email=request_data.email,
            phone=request_data.phone or '',
        )
        
        # Create Stripe customer
        stripe_customer_id = stripe_service.get_or_create_stripe_customer(customer)
        
        if not stripe_customer_id:
            raise HTTPException(status_code=500, detail="Failed to create payment link. Stripe may not be configured.")
        
        # Create a temporary booking-like object for payment link creation
        class TempBooking:
            def __init__(self):
                self.id = 0  # Temporary ID for quote
                self.customer_id = customer.id
                self.service_type = f"3D Print - {request_data.filament_type}"
                self.location_type = None
                self.service_address = ""
                self.deposit_amount = total_amount_cents
                self.preferred_date = None
                self.severity_score = None
                self.customer = customer
                self.vehicle = None
        
        booking = TempBooking()
        
        # Create payment link using stripe_service
        payment_url = stripe_service.create_payment_link_for_booking(booking, None, customer)
        
        if not payment_url:
            raise HTTPException(status_code=500, detail="Failed to create payment link")
        
        return CheckoutResponse(
            payment_url=payment_url,
            total_amount_cents=total_amount_cents
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error during checkout: {e}")
        import traceback
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Checkout error: {str(e)}")


@app.get('/api/order-details')
async def get_order_details(booking_id: int = None, customer_id: int = None):
    """Get order details after successful payment (optional - for payment success page)"""
    try:
        if not booking_id or not customer_id:
            # Return generic success response if IDs not provided
            return {
                "status": "success",
                "message": "Order confirmed"
            }
        
        # In a production system, you would:
        # 1. Query the database for booking and customer details
        # 2. Return order summary with delivery estimate
        # For now, return a generic response
        
        return {
            "booking_id": booking_id,
            "customer_id": customer_id,
            "status": "confirmed",
            "message": "Your order has been confirmed. Check your email for details.",
            "estimated_delivery": "3-5 business days"
        }
    
    except Exception as e:
        logging.error(f"Error fetching order details: {e}")
        # Don't throw error - payment was successful, just return minimal response
        return {
            "status": "success",
            "message": "Your payment was successful. Check your email for order details."
        }


# Mount static files (React app) - must be after API routes
app.mount("/", StaticFiles(directory="static", html=True), name="static")