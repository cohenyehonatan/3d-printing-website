import io
import json
import logging
import trimesh
import csv
import math
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from typing import Optional, List
import os
from pathlib import Path
from datetime import datetime

# Load .env file FIRST before anything else
env_path = Path(__file__).parent.parent / '.env'
print(f"[DEBUG] Loading .env from: {env_path}")
print(f"[DEBUG] .env exists: {env_path.exists()}")

try:
    from dotenv import load_dotenv
    load_dotenv(env_path, override=True)
    print(f"[DEBUG] .env loaded successfully")
except Exception as e:
    print(f"[DEBUG] Failed to load .env: {e}")

# Now import stripe after env is loaded
import stripe

from .sales_tax_rates import sales_tax_rates
from .zip_to_state import get_state_from_zip
from .zip_to_city import get_city_from_zip
from . import stripe_service

logging.basicConfig(level=logging.DEBUG)

app = FastAPI(title="3D Print Quote API", max_body_size=100*1024*1024)

# Initialize Stripe API key on app startup
@app.on_event("startup")
async def startup_event():
    # Initialize database
    from .database import init_db
    init_db()
    
    # Debug: Print what env vars are actually available
    print(f"[Startup] STRIPE_ENABLED: {os.getenv('STRIPE_ENABLED')}")
    print(f"[Startup] STRIPE_SECRET_KEY: {os.getenv('STRIPE_SECRET_KEY')[:20] if os.getenv('STRIPE_SECRET_KEY') else 'NOT SET'}...") # pyright: ignore[reportOptionalSubscript]
    print(f"[Startup] STRIPE_API_KEY: {os.getenv('STRIPE_API_KEY')[:20] if os.getenv('STRIPE_API_KEY') else 'NOT SET'}...")  # pyright: ignore[reportOptionalSubscript]
    
    stripe.api_key = os.getenv('STRIPE_SECRET_KEY') or os.getenv('STRIPE_API_KEY')
    if stripe.api_key:
        print(f"[Stripe] Initialized with key: {stripe.api_key[:20]}...")
    else:
        print("[Stripe] WARNING: No API key configured")
    
    UPS_CLIENT_ID = os.getenv("UPS_CLIENT_ID")
    print(f"[Startup] UPS_CLIENT_ID: {UPS_CLIENT_ID[:20] if UPS_CLIENT_ID else 'NOT SET'}...")
    UPS_CLIENT_SECRET = os.getenv("UPS_CLIENT_SECRET")
    print(f"[Startup] UPS_CLIENT_SECRET: {UPS_CLIENT_SECRET[:20] if UPS_CLIENT_SECRET else 'NOT SET'}...")
    UPS_ACCOUNT_NUMBER = os.getenv("UPS_ACCOUNT_NUMBER")
    print(f"[Startup] UPS_ACCOUNT_NUMBER: {UPS_ACCOUNT_NUMBER[:20] if UPS_ACCOUNT_NUMBER else 'NOT SET'}...")

    if UPS_CLIENT_ID and UPS_CLIENT_SECRET and UPS_ACCOUNT_NUMBER:
        print("[UPS] All required UPS credentials are set, environment " + os.getenv("UPS_ENVIRONMENT", "not set") + ".")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MINIMUM_WEIGHT_G = 0.1  # Minimum weight in grams (adjust as needed)

GRAMS_PER_LB = 453.59237

base_cost = 20

# Maximum file size (16 MB)
MAX_FILE_SIZE = 16 * 1024 * 1024

# Load ZIP code data once at startup for efficient lookups
_zip_cache = {}

def load_zip_data():
    """Load ZIP code coordinates from CSV once at startup"""
    global _zip_cache
    csv_path = Path(__file__).parent.parent / 'uszips.csv'
    
    if not csv_path.exists():
        print(f"[WARNING] uszips.csv not found at {csv_path}")
        return
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                zip_code = row['zip'].strip('"')
                try:
                    _zip_cache[zip_code] = {
                        'lat': float(row['lat'].strip('"')),
                        'lng': float(row['lng'].strip('"'))
                    }
                except (ValueError, KeyError):
                    continue
        print(f"[DEBUG] Loaded {len(_zip_cache)} ZIP codes from uszips.csv")
    except Exception as e:
        print(f"[ERROR] Failed to load uszips.csv: {e}")

# Load ZIP data at module import time
load_zip_data()

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

# ============================================================================
# USPS Official Rate Tables (Notice 123, effective October 5, 2025)
# ============================================================================

# USPS Ground Advantage Retail - Weight-based pricing by zone
USPS_GROUND_ADVANTAGE_RETAIL = {
    # Format: weight_limit_oz: {zone: price}
    "4_oz": {1: 7.20, 2: 7.25, 3: 7.35, 4: 7.50, 5: 7.80, 6: 7.90, 7: 8.10, 8: 8.40, 9: 8.40},
    "8_oz": {1: 7.50, 2: 7.70, 3: 7.85, 4: 8.00, 5: 8.35, 6: 8.55, 7: 8.80, 8: 9.25, 9: 9.25},
    "12_oz": {1: 8.55, 2: 8.85, 3: 9.05, 4: 9.30, 5: 9.75, 6: 10.00, 7: 10.45, 8: 11.10, 9: 11.10},
    "15_999_oz": {1: 9.10, 2: 9.45, 3: 9.75, 4: 10.10, 5: 10.65, 6: 11.00, 7: 11.55, 8: 12.45, 9: 12.45},
    # Lbs pricing (up to 70 lbs)
    1: {1: 9.10, 2: 9.45, 3: 9.75, 4: 10.10, 5: 10.65, 6: 11.00, 7: 11.55, 8: 12.45, 9: 12.45},
    2: {1: 9.85, 2: 10.45, 3: 11.05, 4: 11.80, 5: 12.80, 6: 13.70, 7: 14.90, 8: 17.15, 9: 17.15},
    3: {1: 10.25, 2: 10.90, 3: 11.45, 4: 12.40, 5: 13.60, 6: 14.90, 7: 17.05, 8: 20.10, 9: 20.10},
    4: {1: 11.30, 2: 11.75, 3: 12.55, 4: 13.60, 5: 15.35, 6: 17.00, 7: 19.25, 8: 22.20, 9: 22.20},
    5: {1: 11.95, 2: 12.45, 3: 13.30, 4: 14.45, 5: 16.25, 6: 18.15, 7: 20.60, 8: 23.75, 9: 23.75},
    6: {1: 12.40, 2: 12.75, 3: 13.60, 4: 14.90, 5: 17.10, 6: 19.40, 7: 22.30, 8: 25.80, 9: 25.80},
    7: {1: 12.85, 2: 13.20, 3: 14.05, 4: 15.55, 5: 18.00, 6: 20.75, 7: 23.95, 8: 27.75, 9: 27.75},
    8: {1: 13.35, 2: 13.60, 3: 14.45, 4: 16.05, 5: 18.85, 6: 22.05, 7: 25.90, 8: 30.00, 9: 30.00},
    9: {1: 13.80, 2: 14.05, 3: 14.80, 4: 16.60, 5: 19.70, 6: 23.35, 7: 27.85, 8: 32.20, 9: 32.20},
    10: {1: 14.55, 2: 14.85, 3: 15.65, 4: 17.55, 5: 20.95, 6: 25.05, 7: 30.15, 8: 35.50, 9: 35.50},
    11: {1: 15.60, 2: 16.05, 3: 16.80, 4: 18.80, 5: 23.15, 6: 27.75, 7: 33.45, 8: 39.85, 9: 39.85},
    12: {1: 16.20, 2: 16.60, 3: 17.25, 4: 19.55, 5: 24.20, 6: 29.35, 7: 35.80, 8: 42.65, 9: 42.65},
    13: {1: 16.85, 2: 17.15, 3: 17.70, 4: 20.00, 5: 25.10, 6: 30.95, 7: 38.45, 8: 46.55, 9: 46.55},
    14: {1: 17.50, 2: 17.60, 3: 18.15, 4: 20.70, 5: 26.30, 6: 32.85, 7: 41.20, 8: 50.00, 9: 50.00},
    15: {1: 18.15, 2: 18.25, 3: 18.80, 4: 21.25, 5: 27.30, 6: 34.15, 7: 42.80, 8: 52.15, 9: 52.15},
    16: {1: 18.80, 2: 18.95, 3: 19.50, 4: 22.20, 5: 28.40, 6: 35.45, 7: 44.40, 8: 54.35, 9: 54.35},
    17: {1: 19.45, 2: 19.65, 3: 20.10, 4: 23.15, 5: 29.50, 6: 36.95, 7: 46.45, 8: 56.95, 9: 56.95},
    18: {1: 20.05, 2: 20.25, 3: 20.75, 4: 23.65, 5: 30.65, 6: 38.50, 7: 48.45, 8: 59.55, 9: 59.55},
    19: {1: 20.45, 2: 20.70, 3: 21.60, 4: 24.05, 5: 31.55, 6: 39.45, 7: 49.30, 8: 61.45, 9: 61.45},
    20: {1: 20.85, 2: 21.00, 3: 22.35, 4: 24.85, 5: 32.75, 6: 40.65, 7: 50.55, 8: 62.65, 9: 62.65},
    21: {1: 23.90, 2: 25.00, 3: 26.95, 4: 31.60, 5: 39.90, 6: 48.80, 7: 58.80, 8: 70.65, 9: 70.65},
    22: {1: 25.95, 2: 27.70, 3: 30.40, 4: 36.50, 5: 45.10, 6: 54.55, 7: 64.55, 8: 75.95, 9: 75.95},
    23: {1: 27.25, 2: 29.30, 3: 32.30, 4: 39.15, 5: 48.20, 6: 58.05, 7: 68.35, 8: 79.85, 9: 79.85},
    24: {1: 28.25, 2: 30.35, 3: 33.65, 4: 40.90, 5: 50.45, 6: 60.75, 7: 71.30, 8: 83.10, 9: 83.10},
    25: {1: 29.30, 2: 31.50, 3: 34.95, 4: 42.75, 5: 52.60, 6: 63.30, 7: 74.20, 8: 86.25, 9: 86.25},
    26: {1: 32.30, 2: 34.70, 3: 38.35, 4: 46.60, 5: 58.50, 6: 69.65, 7: 80.85, 8: 93.20, 9: 93.20},
    27: {1: 33.30, 2: 35.80, 3: 39.70, 4: 48.50, 5: 60.75, 6: 72.30, 7: 83.70, 8: 96.35, 9: 96.35},
    28: {1: 34.05, 2: 36.70, 3: 40.75, 4: 49.80, 5: 62.50, 6: 74.40, 7: 86.10, 8: 99.15, 9: 99.15},
    29: {1: 34.85, 2: 37.55, 3: 41.70, 4: 51.20, 5: 64.25, 6: 76.40, 7: 88.45, 8: 101.80, 9: 101.80},
    30: {1: 35.60, 2: 38.45, 3: 42.70, 4: 52.45, 5: 65.90, 6: 78.45, 7: 90.85, 8: 104.40, 9: 104.40},
    31: {1: 36.45, 2: 39.25, 3: 43.65, 4: 53.70, 5: 67.55, 6: 80.45, 7: 93.05, 8: 107.00, 9: 107.00},
    32: {1: 37.10, 2: 40.10, 3: 44.60, 4: 55.00, 5: 69.20, 6: 82.45, 7: 95.35, 8: 109.55, 9: 109.55},
    33: {1: 37.85, 2: 40.90, 3: 45.55, 4: 56.25, 5: 70.85, 6: 84.35, 7: 97.50, 8: 112.05, 9: 112.05},
    34: {1: 38.60, 2: 41.70, 3: 46.45, 4: 57.40, 5: 72.35, 6: 86.25, 7: 99.70, 8: 114.45, 9: 114.45},
    35: {1: 39.35, 2: 42.50, 3: 47.35, 4: 58.65, 5: 74.00, 6: 88.20, 7: 101.95, 8: 116.95, 9: 116.95},
    36: {1: 40.00, 2: 43.25, 3: 48.20, 4: 59.75, 5: 75.50, 6: 90.00, 7: 104.00, 8: 119.25, 9: 119.25},
    37: {1: 40.75, 2: 44.00, 3: 49.10, 4: 61.00, 5: 77.05, 6: 91.80, 7: 106.10, 8: 121.70, 9: 121.70},
    38: {1: 41.45, 2: 44.75, 3: 49.85, 4: 62.10, 5: 78.55, 6: 93.65, 7: 108.20, 8: 124.00, 9: 124.00},
    39: {1: 42.15, 2: 45.50, 3: 50.75, 4: 63.25, 5: 80.10, 6: 95.45, 7: 110.25, 8: 126.25, 9: 126.25},
    40: {1: 42.80, 2: 46.30, 3: 51.55, 4: 64.40, 5: 81.55, 6: 97.25, 7: 112.25, 8: 128.50, 9: 128.50},
    41: {1: 43.50, 2: 47.00, 3: 52.40, 4: 65.50, 5: 83.10, 6: 99.05, 7: 114.25, 8: 130.75, 9: 130.75},
    42: {1: 44.20, 2: 47.65, 3: 53.15, 4: 66.55, 5: 84.50, 6: 100.70, 7: 116.15, 8: 132.90, 9: 132.90},
    43: {1: 44.80, 2: 48.40, 3: 53.95, 4: 67.60, 5: 85.95, 6: 102.40, 7: 118.10, 8: 135.05, 9: 135.05},
    44: {1: 45.50, 2: 49.10, 3: 54.65, 4: 68.65, 5: 87.35, 6: 104.15, 7: 120.00, 8: 137.10, 9: 137.10},
    45: {1: 46.10, 2: 49.75, 3: 55.45, 4: 69.70, 5: 88.75, 6: 105.70, 7: 121.90, 8: 139.20, 9: 139.20},
    46: {1: 46.75, 2: 50.45, 3: 56.15, 4: 70.70, 5: 90.10, 6: 107.40, 7: 123.65, 8: 141.20, 9: 141.20},
    47: {1: 47.35, 2: 51.15, 3: 56.90, 4: 71.70, 5: 91.45, 6: 108.90, 7: 125.50, 8: 143.20, 9: 143.20},
    48: {1: 47.95, 2: 51.75, 3: 57.55, 4: 72.65, 5: 92.80, 6: 110.55, 7: 127.30, 8: 145.10, 9: 145.10},
    49: {1: 48.55, 2: 52.35, 3: 58.30, 4: 73.60, 5: 94.15, 6: 112.05, 7: 129.00, 8: 147.05, 9: 147.05},
    50: {1: 49.15, 2: 53.00, 3: 58.95, 4: 74.55, 5: 95.40, 6: 113.60, 7: 130.70, 8: 148.90, 9: 148.90},
    51: {1: 49.75, 2: 53.60, 3: 59.55, 4: 75.45, 5: 96.70, 6: 115.15, 7: 132.40, 8: 150.65, 9: 150.65},
    52: {1: 50.35, 2: 54.20, 3: 60.20, 4: 76.35, 5: 97.95, 6: 116.55, 7: 134.00, 8: 152.45, 9: 152.45},
    53: {1: 50.90, 2: 54.75, 3: 60.75, 4: 77.25, 5: 99.15, 6: 118.00, 7: 135.60, 8: 154.20, 9: 154.20},
    54: {1: 51.45, 2: 55.35, 3: 61.40, 4: 78.05, 5: 100.35, 6: 119.40, 7: 137.25, 8: 155.95, 9: 155.95},
    55: {1: 51.95, 2: 55.90, 3: 62.00, 4: 78.95, 5: 101.55, 6: 120.75, 7: 138.70, 8: 157.60, 9: 157.60},
    56: {1: 52.55, 2: 56.45, 3: 62.55, 4: 79.80, 5: 102.75, 6: 122.15, 7: 140.30, 8: 159.20, 9: 159.20},
    57: {1: 53.05, 2: 57.00, 3: 63.10, 4: 80.50, 5: 103.90, 6: 123.50, 7: 141.70, 8: 160.80, 9: 160.80},
    58: {1: 53.55, 2: 57.45, 3: 63.60, 4: 81.35, 5: 105.05, 6: 124.80, 7: 143.20, 8: 162.35, 9: 162.35},
    59: {1: 54.10, 2: 58.05, 3: 64.20, 4: 82.05, 5: 106.15, 6: 126.10, 7: 144.60, 8: 163.80, 9: 163.80},
    60: {1: 54.55, 2: 58.50, 3: 64.65, 4: 82.85, 5: 107.20, 6: 127.35, 7: 146.05, 8: 165.35, 9: 165.35},
    61: {1: 55.05, 2: 59.00, 3: 65.15, 4: 83.55, 5: 108.30, 6: 128.60, 7: 147.35, 8: 166.70, 9: 166.70},
    62: {1: 55.55, 2: 59.45, 3: 65.60, 4: 84.25, 5: 109.35, 6: 129.80, 7: 148.65, 8: 168.15, 9: 168.15},
    63: {1: 56.05, 2: 59.95, 3: 66.05, 4: 85.00, 5: 110.30, 6: 130.95, 7: 149.95, 8: 169.45, 9: 169.45},
    64: {1: 56.45, 2: 60.35, 3: 66.45, 4: 85.60, 5: 111.35, 6: 132.10, 7: 151.20, 8: 170.80, 9: 170.80},
    65: {1: 56.90, 2: 60.85, 3: 66.95, 4: 86.25, 5: 112.35, 6: 133.25, 7: 152.40, 8: 172.05, 9: 172.05},
    66: {1: 57.35, 2: 61.25, 3: 67.30, 4: 86.90, 5: 113.30, 6: 134.40, 7: 153.60, 8: 173.35, 9: 173.35},
    67: {1: 57.75, 2: 61.65, 3: 67.70, 4: 87.45, 5: 114.25, 6: 135.45, 7: 154.75, 8: 174.50, 9: 174.50},
    68: {1: 58.25, 2: 62.05, 3: 68.05, 4: 88.10, 5: 115.20, 6: 136.50, 7: 155.90, 8: 175.60, 9: 175.60},
    69: {1: 58.60, 2: 62.45, 3: 68.45, 4: 88.60, 5: 116.10, 6: 137.50, 7: 156.95, 8: 176.70, 9: 176.70},
    70: {1: 59.05, 2: 62.85, 3: 68.75, 4: 89.20, 5: 117.00, 6: 138.50, 7: 158.00, 8: 177.80, 9: 177.80},
}

# USPS Priority Mail Retail - Weight-based pricing by zone
USPS_PRIORITY_MAIL_RETAIL = {
    "4_oz": {1: 10.45, 2: 10.90, 3: 11.10, 4: 11.30, 5: 13.00, 6: 14.20, 7: 15.35, 8: 16.60, 9: 32.60},
    "8_oz": {1: 10.45, 2: 10.90, 3: 11.10, 4: 11.30, 5: 13.00, 6: 14.20, 7: 15.35, 8: 16.60, 9: 32.60},
    "12_oz": {1: 10.45, 2: 10.90, 3: 11.10, 4: 11.30, 5: 13.00, 6: 14.20, 7: 15.35, 8: 16.60, 9: 32.60},
    "15_999_oz": {1: 10.45, 2: 10.90, 3: 11.10, 4: 11.30, 5: 13.00, 6: 14.20, 7: 15.35, 8: 16.60, 9: 32.60},
    1: {1: 10.45, 2: 10.90, 3: 11.10, 4: 11.30, 5: 13.00, 6: 14.20, 7: 15.35, 8: 16.60, 9: 32.60},
    2: {1: 10.90, 2: 11.50, 3: 12.20, 4: 13.05, 5: 15.75, 6: 16.90, 7: 18.05, 8: 19.85, 9: 39.15},
    3: {1: 11.35, 2: 12.10, 3: 12.70, 4: 13.75, 5: 16.85, 6: 19.45, 7: 22.00, 8: 24.85, 9: 49.25},
    4: {1: 12.40, 2: 12.95, 3: 13.85, 4: 15.00, 5: 19.80, 6: 23.95, 7: 26.65, 8: 29.70, 9: 58.50},
    5: {1: 13.20, 2: 13.75, 3: 14.70, 4: 16.00, 5: 21.00, 6: 25.45, 7: 30.60, 8: 34.25, 9: 67.70},
    6: {1: 13.70, 2: 14.10, 3: 15.10, 4: 16.60, 5: 22.05, 6: 27.80, 7: 34.45, 8: 38.75, 9: 76.80},
    7: {1: 14.30, 2: 14.70, 3: 15.65, 4: 17.35, 5: 23.70, 6: 30.20, 7: 38.20, 8: 43.15, 9: 85.65},
    8: {1: 14.90, 2: 15.15, 3: 16.10, 4: 17.95, 5: 24.85, 6: 32.70, 7: 42.00, 8: 47.60, 9: 94.65},
    9: {1: 15.40, 2: 15.70, 3: 16.50, 4: 18.95, 5: 25.75, 6: 35.05, 7: 45.65, 8: 51.85, 9: 103.25},
    10: {1: 16.30, 2: 16.65, 3: 17.50, 4: 19.75, 5: 26.80, 6: 37.65, 7: 49.35, 8: 56.15, 9: 111.95},
    11: {1: 17.40, 2: 17.90, 3: 18.80, 4: 21.10, 5: 29.75, 6: 42.15, 7: 54.95, 8: 62.35, 9: 122.60},
    12: {1: 18.10, 2: 18.55, 3: 19.35, 4: 21.90, 5: 30.75, 6: 44.75, 7: 58.85, 8: 66.85, 9: 131.70},
    13: {1: 18.85, 2: 19.20, 3: 19.85, 4: 22.45, 5: 32.00, 6: 47.30, 7: 62.80, 8: 71.50, 9: 141.10},
    14: {1: 19.60, 2: 19.75, 3: 20.40, 4: 23.25, 5: 33.30, 6: 50.05, 7: 66.90, 8: 76.15, 9: 150.50},
    15: {1: 20.30, 2: 20.50, 3: 21.15, 4: 24.05, 5: 34.75, 6: 52.30, 7: 70.10, 8: 79.90, 9: 158.05},
    16: {1: 21.10, 2: 21.30, 3: 21.90, 4: 25.00, 5: 36.45, 6: 54.85, 7: 73.80, 8: 84.25, 9: 166.85},
    17: {1: 21.85, 2: 22.10, 3: 22.60, 4: 26.05, 5: 38.35, 6: 57.65, 7: 77.50, 8: 88.55, 9: 175.55},
    18: {1: 22.55, 2: 22.80, 3: 23.35, 4: 27.15, 5: 40.45, 6: 60.60, 7: 81.20, 8: 92.90, 9: 184.30},
    19: {1: 23.00, 2: 23.30, 3: 24.30, 4: 27.65, 5: 42.35, 6: 63.40, 7: 84.40, 8: 96.65, 9: 191.90},
    20: {1: 23.45, 2: 23.65, 3: 25.20, 4: 28.35, 5: 44.90, 6: 66.45, 7: 87.95, 8: 100.95, 9: 200.55},
    21: {1: 26.90, 2: 28.25, 3: 30.40, 4: 35.65, 5: 50.10, 6: 70.40, 7: 90.65, 8: 104.50, 9: 207.75},
    22: {1: 29.20, 2: 31.25, 3: 34.30, 4: 41.20, 5: 56.60, 6: 75.00, 7: 93.40, 8: 108.00, 9: 214.80},
    23: {1: 30.75, 2: 33.10, 3: 36.50, 4: 44.25, 5: 60.45, 6: 78.30, 7: 96.10, 8: 111.55, 9: 222.00},
    24: {1: 31.85, 2: 34.30, 3: 38.00, 4: 46.25, 5: 63.20, 6: 81.05, 7: 98.85, 8: 115.15, 9: 229.25},
    25: {1: 33.05, 2: 35.60, 3: 39.50, 4: 48.35, 5: 65.85, 6: 83.75, 7: 101.65, 8: 118.75, 9: 236.50},
    26: {1: 36.20, 2: 38.95, 3: 43.10, 4: 52.45, 5: 72.30, 6: 90.45, 7: 108.60, 8: 126.20, 9: 247.75},
    27: {1: 37.30, 2: 40.25, 3: 44.60, 4: 54.55, 5: 75.05, 6: 92.85, 7: 110.60, 8: 128.90, 9: 253.20},
    28: {1: 38.20, 2: 41.20, 3: 45.80, 4: 56.05, 5: 77.20, 6: 94.90, 7: 112.55, 8: 131.70, 9: 258.85},
    29: {1: 39.05, 2: 42.20, 3: 46.90, 4: 57.60, 5: 79.35, 6: 96.95, 7: 114.55, 8: 134.20, 9: 263.90},
    30: {1: 39.95, 2: 43.20, 3: 48.00, 4: 59.05, 5: 81.40, 6: 98.95, 7: 116.50, 8: 136.55, 9: 268.65},
    31: {1: 40.85, 2: 44.15, 3: 49.10, 4: 60.50, 5: 83.45, 6: 100.95, 7: 118.50, 8: 138.90, 9: 273.40},
    32: {1: 41.65, 2: 45.15, 3: 50.25, 4: 62.00, 5: 85.50, 6: 103.00, 7: 120.50, 8: 141.15, 9: 277.95},
    33: {1: 42.50, 2: 46.00, 3: 51.30, 4: 63.40, 5: 87.55, 6: 105.00, 7: 122.40, 8: 143.40, 9: 282.50},
    34: {1: 43.40, 2: 46.95, 3: 52.35, 4: 64.75, 5: 89.45, 6: 106.95, 7: 124.40, 8: 145.70, 9: 287.15},
    35: {1: 44.20, 2: 47.90, 3: 53.35, 4: 66.15, 5: 91.45, 6: 108.90, 7: 126.35, 8: 147.90, 9: 291.55},
    36: {1: 45.05, 2: 48.75, 3: 54.40, 4: 67.45, 5: 93.40, 6: 110.80, 7: 128.15, 8: 150.15, 9: 296.10},
    37: {1: 45.85, 2: 49.65, 3: 55.40, 4: 68.85, 5: 95.30, 6: 112.60, 7: 129.90, 8: 152.35, 9: 300.55},
    38: {1: 46.65, 2: 50.45, 3: 56.25, 4: 70.15, 5: 97.15, 6: 114.40, 7: 131.60, 8: 154.60, 9: 305.10},
    39: {1: 47.45, 2: 51.35, 3: 57.25, 4: 71.40, 5: 99.10, 6: 116.45, 7: 133.80, 8: 156.80, 9: 309.55},
    40: {1: 48.20, 2: 52.25, 3: 58.20, 4: 72.70, 5: 100.85, 6: 118.40, 7: 135.90, 8: 159.00, 9: 314.00},
    41: {1: 48.95, 2: 53.05, 3: 59.15, 4: 73.95, 5: 102.75, 6: 120.35, 7: 137.95, 8: 161.15, 9: 318.35},
    42: {1: 49.75, 2: 53.80, 3: 60.00, 4: 75.15, 5: 104.45, 6: 122.10, 7: 139.75, 8: 163.30, 9: 322.70},
    43: {1: 50.45, 2: 54.65, 3: 60.90, 4: 76.35, 5: 106.25, 6: 123.95, 7: 141.60, 8: 165.40, 9: 326.90},
    44: {1: 51.25, 2: 55.45, 3: 61.70, 4: 77.50, 5: 108.00, 6: 125.70, 7: 143.35, 8: 167.55, 9: 331.25},
    45: {1: 51.95, 2: 56.15, 3: 62.60, 4: 78.70, 5: 109.70, 6: 127.40, 7: 145.10, 8: 169.65, 9: 335.50},
    46: {1: 52.65, 2: 56.95, 3: 63.40, 4: 79.85, 5: 111.35, 6: 129.10, 7: 146.85, 8: 171.80, 9: 339.85},
    47: {1: 53.35, 2: 57.75, 3: 64.20, 4: 80.95, 5: 113.05, 6: 130.85, 7: 148.65, 8: 173.90, 9: 344.10},
    48: {1: 54.00, 2: 58.45, 3: 65.00, 4: 82.00, 5: 114.70, 6: 132.55, 7: 150.35, 8: 176.00, 9: 348.35},
    49: {1: 54.70, 2: 59.15, 3: 65.80, 4: 83.15, 5: 116.30, 6: 134.20, 7: 152.10, 8: 178.05, 9: 352.45},
    50: {1: 55.40, 2: 59.85, 3: 66.55, 4: 84.20, 5: 117.85, 6: 135.90, 7: 153.95, 8: 180.10, 9: 356.60},
    51: {1: 56.05, 2: 60.55, 3: 67.20, 4: 85.20, 5: 119.45, 6: 137.65, 7: 155.85, 8: 182.15, 9: 360.75},
    52: {1: 56.75, 2: 61.25, 3: 67.95, 4: 86.25, 5: 121.00, 6: 139.40, 7: 157.75, 8: 184.25, 9: 365.00},
    53: {1: 57.30, 2: 61.80, 3: 68.60, 4: 87.25, 5: 122.45, 6: 141.10, 7: 159.75, 8: 186.50, 9: 369.55},
    54: {1: 57.95, 2: 62.55, 3: 69.30, 4: 88.15, 5: 123.90, 6: 142.80, 7: 161.70, 8: 188.75, 9: 374.10},
    55: {1: 58.55, 2: 63.15, 3: 70.00, 4: 89.15, 5: 125.40, 6: 144.55, 7: 163.70, 8: 191.00, 9: 378.60},
    56: {1: 59.20, 2: 63.75, 3: 70.60, 4: 90.10, 5: 126.85, 6: 146.25, 7: 165.60, 8: 193.05, 9: 382.75},
    57: {1: 59.80, 2: 64.40, 3: 71.25, 4: 90.90, 5: 128.30, 6: 147.95, 7: 167.60, 8: 195.05, 9: 386.80},
    58: {1: 60.35, 2: 64.95, 3: 71.85, 4: 91.85, 5: 129.70, 6: 149.65, 7: 169.55, 8: 197.05, 9: 390.85},
    59: {1: 60.95, 2: 65.55, 3: 72.50, 4: 92.65, 5: 131.05, 6: 151.10, 7: 171.15, 8: 199.05, 9: 394.90},
    60: {1: 61.45, 2: 66.10, 3: 73.00, 4: 93.55, 5: 132.30, 6: 152.55, 7: 172.75, 8: 200.95, 9: 398.70},
    61: {1: 62.05, 2: 66.70, 3: 73.60, 4: 94.30, 5: 133.65, 6: 154.05, 7: 174.40, 8: 203.25, 9: 403.35},
    62: {1: 62.60, 2: 67.15, 3: 74.05, 4: 95.15, 5: 134.95, 6: 155.45, 7: 175.95, 8: 205.65, 9: 408.20},
    63: {1: 63.15, 2: 67.75, 3: 74.60, 4: 95.95, 5: 136.15, 6: 156.80, 7: 177.50, 8: 208.10, 9: 413.15},
    64: {1: 63.65, 2: 68.20, 3: 75.05, 4: 96.65, 5: 137.45, 6: 158.30, 7: 179.10, 8: 210.45, 9: 417.90},
    65: {1: 64.10, 2: 68.75, 3: 75.60, 4: 97.35, 5: 138.65, 6: 159.65, 7: 180.65, 8: 212.90, 9: 422.85},
    66: {1: 64.65, 2: 69.20, 3: 76.00, 4: 98.10, 5: 139.80, 6: 161.00, 7: 182.20, 8: 215.25, 9: 427.60},
    67: {1: 65.10, 2: 69.65, 3: 76.45, 4: 98.75, 5: 140.95, 6: 162.35, 7: 183.75, 8: 217.60, 9: 432.35},
    68: {1: 65.65, 2: 70.15, 3: 76.85, 4: 99.45, 5: 142.10, 6: 163.70, 7: 185.30, 8: 219.80, 9: 436.80},
    69: {1: 66.05, 2: 70.55, 3: 77.30, 4: 100.05, 5: 143.20, 6: 165.00, 7: 186.75, 8: 222.00, 9: 441.25},
    70: {1: 66.55, 2: 71.00, 3: 77.65, 4: 100.70, 5: 144.35, 6: 166.30, 7: 188.30, 8: 224.05, 9: 445.35},
}

# USPS Priority Mail Express - Weight-based pricing by zone
USPS_PRIORITY_MAIL_EXPRESS = {
    "4_oz": {1: 32.50, 2: 32.75, 3: 32.85, 4: 35.20, 5: 40.80, 6: 43.70, 7: 46.50, 8: 49.80, 9: 65.55},
    "8_oz": {1: 32.50, 2: 32.75, 3: 32.85, 4: 35.20, 5: 40.80, 6: 43.70, 7: 46.50, 8: 49.80, 9: 65.55},
    "12_oz": {1: 33.05, 2: 33.80, 3: 35.55, 4: 40.20, 5: 48.35, 6: 52.15, 7: 55.30, 8: 58.50, 9: 77.30},
    "15_999_oz": {1: 33.05, 2: 33.80, 3: 35.55, 4: 40.20, 5: 48.35, 6: 52.15, 7: 55.30, 8: 58.50, 9: 77.30},
    1: {1: 33.05, 2: 33.80, 3: 35.55, 4: 40.20, 5: 48.35, 6: 52.15, 7: 55.30, 8: 58.50, 9: 77.30},
    2: {1: 33.55, 2: 34.85, 3: 38.35, 4: 45.25, 5: 55.85, 6: 60.60, 7: 64.05, 8: 67.20, 9: 89.00},
    3: {1: 34.05, 2: 35.95, 3: 41.10, 4: 50.25, 5: 63.45, 6: 69.15, 7: 72.90, 8: 75.90, 9: 100.65},
    4: {1: 35.50, 2: 37.85, 3: 44.80, 4: 56.25, 5: 73.85, 6: 80.45, 7: 84.50, 8: 87.45, 9: 115.20},
    5: {1: 36.00, 2: 38.95, 3: 47.50, 4: 61.25, 5: 81.35, 6: 88.90, 7: 93.35, 8: 96.20, 9: 126.95},
    6: {1: 39.40, 2: 42.65, 3: 52.00, 4: 67.75, 5: 88.85, 6: 96.65, 7: 101.70, 8: 104.80, 9: 138.50},
    7: {1: 42.85, 2: 46.30, 3: 56.45, 4: 74.25, 5: 96.35, 6: 104.40, 7: 110.05, 8: 113.35, 9: 150.10},
    8: {1: 46.25, 2: 50.05, 3: 60.95, 4: 80.75, 5: 103.80, 6: 112.15, 7: 118.40, 8: 122.00, 9: 161.65},
    9: {1: 49.75, 2: 53.70, 3: 65.35, 4: 87.25, 5: 111.30, 6: 119.85, 7: 126.80, 8: 130.55, 9: 173.25},
    10: {1: 53.15, 2: 57.40, 3: 69.85, 4: 93.75, 5: 118.80, 6: 127.60, 7: 135.15, 8: 139.15, 9: 184.85},
    11: {1: 57.50, 2: 62.40, 3: 76.80, 4: 100.80, 5: 128.00, 6: 136.60, 7: 144.35, 8: 148.65, 9: 196.20},
    12: {1: 59.95, 2: 65.50, 3: 81.85, 4: 105.95, 5: 133.05, 6: 141.40, 7: 149.45, 8: 154.00, 9: 203.40},
    13: {1: 62.40, 2: 68.65, 3: 87.00, 4: 111.05, 5: 138.10, 6: 146.25, 7: 154.50, 8: 159.30, 9: 210.55},
    14: {1: 64.90, 2: 71.75, 3: 92.05, 4: 116.25, 5: 143.15, 6: 151.05, 7: 159.55, 8: 164.70, 9: 217.75},
    15: {1: 67.30, 2: 74.85, 3: 97.10, 4: 121.40, 5: 148.25, 6: 155.90, 7: 164.65, 8: 170.00, 9: 224.95},
    16: {1: 69.80, 2: 77.95, 3: 102.15, 4: 126.55, 5: 153.35, 6: 160.70, 7: 169.75, 8: 175.30, 9: 232.15},
    17: {1: 72.25, 2: 81.05, 3: 107.20, 4: 131.70, 5: 158.40, 6: 165.55, 7: 174.80, 8: 180.65, 9: 239.35},
    18: {1: 74.75, 2: 84.20, 3: 112.30, 4: 136.80, 5: 163.45, 6: 170.35, 7: 179.85, 8: 186.00, 9: 246.55},
    19: {1: 77.15, 2: 87.30, 3: 117.35, 4: 142.00, 5: 168.50, 6: 175.20, 7: 184.95, 8: 191.35, 9: 253.75},
    20: {1: 79.65, 2: 90.40, 3: 122.45, 4: 147.15, 5: 173.55, 6: 180.00, 7: 190.00, 8: 196.65, 9: 260.95},
    21: {1: 82.55, 2: 94.00, 3: 128.10, 4: 153.15, 5: 180.20, 6: 186.70, 7: 197.00, 8: 203.95, 9: 270.75},
    22: {1: 85.50, 2: 97.55, 3: 133.80, 4: 159.15, 5: 186.90, 6: 193.45, 7: 203.95, 8: 211.15, 9: 280.50},
    23: {1: 88.35, 2: 101.15, 3: 139.45, 4: 165.15, 5: 193.55, 6: 200.20, 7: 210.90, 8: 218.45, 9: 290.30},
    24: {1: 91.25, 2: 104.80, 3: 145.15, 4: 171.15, 5: 200.25, 6: 206.95, 7: 217.90, 8: 225.65, 9: 300.15},
    25: {1: 94.20, 2: 108.40, 3: 150.80, 4: 177.15, 5: 206.90, 6: 213.65, 7: 224.85, 8: 232.95, 9: 309.90},
    26: {1: 102.95, 2: 117.80, 3: 162.35, 4: 189.00, 5: 220.60, 6: 227.35, 7: 238.80, 8: 247.15, 9: 326.70},
    27: {1: 105.85, 2: 121.40, 3: 168.00, 4: 195.00, 5: 227.25, 6: 234.10, 7: 245.75, 8: 254.45, 9: 336.50},
    28: {1: 108.75, 2: 125.00, 3: 173.75, 4: 201.05, 5: 233.90, 6: 240.80, 7: 252.75, 8: 261.65, 9: 346.25},
    29: {1: 111.65, 2: 128.65, 3: 179.40, 4: 207.00, 5: 240.55, 6: 247.60, 7: 259.70, 8: 268.95, 9: 356.05},
    30: {1: 114.55, 2: 132.20, 3: 185.10, 4: 213.00, 5: 247.25, 6: 254.30, 7: 266.65, 8: 276.15, 9: 365.85},
    31: {1: 117.50, 2: 135.80, 3: 190.75, 4: 219.05, 5: 253.95, 6: 261.00, 7: 273.65, 8: 283.45, 9: 375.60},
    32: {1: 120.40, 2: 139.40, 3: 196.45, 4: 225.05, 5: 260.60, 6: 267.75, 7: 280.60, 8: 290.65, 9: 385.40},
    33: {1: 123.25, 2: 143.05, 3: 202.10, 4: 231.00, 5: 267.25, 6: 274.45, 7: 287.55, 8: 297.95, 9: 395.20},
    34: {1: 126.20, 2: 146.60, 3: 207.80, 4: 237.05, 5: 273.95, 6: 281.20, 7: 294.55, 8: 305.15, 9: 404.95},
    35: {1: 129.10, 2: 150.20, 3: 213.45, 4: 243.05, 5: 280.60, 6: 287.95, 7: 301.50, 8: 312.45, 9: 414.75},
    36: {1: 132.20, 2: 153.90, 3: 218.95, 4: 249.10, 5: 287.65, 6: 295.40, 7: 309.25, 8: 320.40, 9: 425.55},
    37: {1: 134.90, 2: 157.15, 3: 224.05, 4: 255.40, 5: 294.60, 6: 302.85, 7: 316.95, 8: 328.50, 9: 436.15},
    38: {1: 137.75, 2: 160.75, 3: 229.55, 4: 261.60, 5: 301.55, 6: 309.90, 7: 324.30, 8: 336.20, 9: 446.70},
    39: {1: 140.95, 2: 164.45, 3: 234.90, 4: 267.95, 5: 308.45, 6: 316.70, 7: 331.45, 8: 344.05, 9: 457.35},
    40: {1: 143.75, 2: 167.80, 3: 240.00, 4: 274.25, 5: 315.55, 6: 324.10, 7: 338.90, 8: 352.15, 9: 468.10},
    41: {1: 146.75, 2: 171.60, 3: 246.10, 4: 282.00, 5: 324.15, 6: 333.45, 7: 348.65, 8: 362.05, 9: 480.80},
    42: {1: 149.20, 2: 174.75, 3: 251.50, 4: 288.30, 5: 330.90, 6: 340.95, 7: 356.25, 8: 369.85, 9: 491.50},
    43: {1: 152.40, 2: 178.50, 3: 256.75, 4: 294.25, 5: 337.90, 6: 348.15, 7: 363.70, 8: 377.80, 9: 502.30},
    44: {1: 155.05, 2: 181.85, 3: 262.20, 4: 300.65, 5: 344.85, 6: 355.15, 7: 371.15, 8: 385.80, 9: 512.70},
    45: {1: 157.85, 2: 185.30, 3: 267.50, 4: 306.75, 5: 351.55, 6: 362.45, 7: 378.70, 8: 393.85, 9: 523.65},
    46: {1: 160.70, 2: 188.65, 3: 272.65, 4: 313.35, 5: 358.70, 6: 369.70, 7: 385.95, 8: 401.65, 9: 534.20},
    47: {1: 163.90, 2: 192.40, 3: 278.00, 4: 319.40, 5: 365.55, 6: 377.10, 7: 393.65, 8: 409.70, 9: 544.90},
    48: {1: 166.45, 2: 195.75, 3: 283.60, 4: 325.55, 5: 372.30, 6: 384.30, 7: 401.10, 8: 417.65, 9: 555.65},
    49: {1: 169.35, 2: 199.25, 3: 288.65, 4: 331.95, 5: 379.20, 6: 391.85, 7: 408.80, 8: 425.50, 9: 566.40},
    50: {1: 172.70, 2: 203.10, 3: 294.15, 4: 338.25, 5: 386.25, 6: 398.85, 7: 416.00, 8: 433.50, 9: 576.95},
    51: {1: 175.55, 2: 206.60, 3: 299.60, 4: 344.40, 5: 393.05, 6: 406.00, 7: 423.40, 8: 440.40, 9: 586.25},
    52: {1: 178.40, 2: 209.90, 3: 304.50, 4: 350.55, 5: 399.80, 6: 413.55, 7: 431.00, 8: 449.65, 9: 598.45},
    53: {1: 181.15, 2: 213.40, 3: 310.10, 4: 356.95, 5: 406.65, 6: 420.85, 7: 438.55, 8: 457.55, 9: 609.20},
    54: {1: 184.20, 2: 217.10, 3: 315.50, 4: 363.00, 5: 413.30, 6: 428.30, 7: 446.10, 8: 465.35, 9: 619.75},
    55: {1: 187.65, 2: 221.40, 3: 322.50, 4: 369.45, 5: 420.35, 6: 435.35, 7: 453.35, 8: 473.30, 9: 630.35},
    56: {1: 192.10, 2: 226.35, 3: 329.20, 4: 377.65, 5: 429.40, 6: 445.00, 7: 463.55, 8: 483.90, 9: 646.60},
    57: {1: 195.25, 2: 230.10, 3: 334.55, 4: 383.95, 5: 436.45, 6: 452.30, 7: 470.85, 8: 491.90, 9: 657.20},
    58: {1: 198.40, 2: 233.75, 3: 339.70, 4: 390.25, 5: 443.20, 6: 459.70, 7: 478.45, 8: 499.85, 9: 667.95},
    59: {1: 201.00, 2: 237.00, 3: 345.05, 4: 396.35, 5: 449.95, 6: 467.20, 7: 485.95, 8: 507.90, 9: 678.70},
    60: {1: 203.60, 2: 240.35, 3: 350.50, 4: 402.80, 5: 456.85, 6: 474.45, 7: 493.40, 8: 515.85, 9: 689.55},
    61: {1: 206.30, 2: 243.70, 3: 355.90, 4: 409.35, 5: 464.15, 6: 481.75, 7: 500.90, 8: 523.80, 9: 700.30},
    62: {1: 209.45, 2: 247.35, 3: 361.15, 4: 415.55, 5: 470.60, 6: 488.95, 7: 508.30, 8: 532.00, 9: 711.20},
    63: {1: 212.65, 2: 251.15, 3: 366.45, 4: 421.80, 5: 477.50, 6: 496.50, 7: 515.90, 8: 540.00, 9: 722.05},
    64: {1: 215.50, 2: 254.55, 3: 371.70, 4: 427.95, 5: 484.20, 6: 503.90, 7: 523.50, 8: 548.00, 9: 732.95},
    65: {1: 218.95, 2: 258.50, 3: 377.10, 4: 434.20, 5: 491.00, 6: 511.20, 7: 530.60, 8: 555.95, 9: 743.45},
    66: {1: 222.85, 2: 262.80, 3: 382.60, 4: 440.65, 5: 497.95, 6: 518.55, 7: 538.10, 8: 563.90, 9: 753.95},
    67: {1: 225.40, 2: 266.00, 3: 387.80, 4: 447.05, 5: 504.85, 6: 525.50, 7: 545.25, 8: 571.85, 9: 765.05},
    68: {1: 228.15, 2: 269.40, 3: 393.15, 4: 453.30, 5: 511.45, 6: 533.15, 7: 553.10, 8: 580.15, 9: 776.05},
    69: {1: 231.65, 2: 273.35, 3: 398.60, 4: 459.50, 5: 518.35, 6: 540.30, 7: 560.35, 8: 587.75, 9: 786.35},
    70: {1: 235.60, 2: 277.70, 3: 404.05, 4: 465.80, 5: 525.15, 6: 547.65, 7: 567.75, 8: 595.80, 9: 797.20},
}

# Available weight tiers in USPS rate tables
AVAILABLE_OZ = [4, 8, 12, 15.999]
OZ_KEY_MAP = {4: "4_oz", 8: "8_oz", 12: "12_oz", 15.999: "15_999_oz"}
AVAILABLE_LBS = list(range(1, 71))  # 1–70 inclusive

def get_usps_zone_from_distance(distance_miles):
    """
    Determine USPS zone (1-9) based on distance in miles.
    Based on USPS zone boundaries from Notice 123.
    """
    if distance_miles <= 50:
        return 1
    elif distance_miles <= 150:
        return 2
    elif distance_miles <= 300:
        return 3
    elif distance_miles <= 600:
        return 4
    elif distance_miles <= 1000:
        return 5
    elif distance_miles <= 1400:
        return 6
    elif distance_miles <= 1800:
        return 7
    elif distance_miles <= 2000:
        return 8
    else:
        return 9


# def get_weight_bracket(weight_lbs):
#     """
#     Determine the appropriate weight bracket for rate lookup.
#     Weight brackets: ≤4oz, ≤8oz, ≤12oz, ≤16oz, 1-70 lbs
#     Snaps to next valid tier if exact match not available.
#     Returns: (weight_key, is_ounces)
#     """
#     if weight_lbs < 1.0:  # Ounce-based pricing
#         # Find the first oz tier >= weight
#         for oz_tier in AVAILABLE_OZ:
#             if weight_lbs <= oz_tier / 16.0:  # Convert oz to lbs for comparison
#                 return (OZ_KEY_MAP[oz_tier], True)
#         # Fallback to highest oz tier if somehow over 1 lb
#         return (OZ_KEY_MAP[15.999], True)
#     else:  # >= 1 lb, use pound-based pricing
#         # Round up to nearest lb
#         weight_lbs_rounded = math.ceil(weight_lbs)
#         # Snap to next available tier or use the tier itself
#         for lb_tier in AVAILABLE_LBS:
#             if weight_lbs_rounded <= lb_tier:
#                 return (lb_tier, False)
#         # Cap at 70 lbs (max USPS retail limit)
#         return (70, False)

def get_weight_bracket(weight_lbs: float) -> tuple[float, bool]:
    weight_oz = weight_lbs * 16

    if weight_oz <= 15.999:
        for oz in AVAILABLE_OZ:
            if weight_oz <= oz:
                return oz, True

    rounded_lbs = math.ceil(weight_lbs)
    rounded_lbs = min(rounded_lbs, 70)

    return rounded_lbs, False



# # USPS shipping calculation function using official Notice 123 rates
# def calculate_usps_shipping(zip_code, weight_kg, service_type="ground_advantage", express=False, connect_local=False):
#     """
#     Calculate USPS shipping cost using official USPS Notice 123 rates (effective Oct 5, 2025).
    
#     Parameters:
#     - zip_code: destination ZIP code
#     - weight_kg: weight in kilograms
#     - service_type: "ground_advantage", "priority_mail", or "priority_express"
#     - express: legacy parameter (use service_type instead)
#     - connect_local: apply USPS Connect Local discount (15% off)
    
#     Returns: shipping cost in dollars
#     """
#     weight_lbs = weight_kg * 2.20462  # Convert kg to lbs
    
#     # Get origin ZIP from environment
#     origin_zip = os.getenv('ZIP_CODE', '10001')  # Default to NYC
    
#     # Calculate actual distance in miles
#     distance_miles = calculate_distance_between_zips(origin_zip, zip_code)
    
#     # Determine USPS zone
#     zone = get_usps_zone_from_distance(distance_miles)
    
#     # Determine weight bracket (snaps to next valid tier)
#     weight_key, _ = get_weight_bracket(weight_lbs)
    
#     # Select rate table based on service type
#     if express or service_type == "priority_express":
#         rate_table = USPS_PRIORITY_MAIL_EXPRESS
#     elif service_type == "priority_mail":
#         rate_table = USPS_PRIORITY_MAIL_RETAIL
#     else:  # default to ground_advantage
#         rate_table = USPS_GROUND_ADVANTAGE_RETAIL
    
#     # Look up shipping cost (weight key is guaranteed to be in table)
#     try:
#         shipping_cost = rate_table[weight_key][zone]
#     except (KeyError, TypeError):
#         # Fallback should rarely happen now with snapping logic
#         print(f"[WARNING] Error looking up rate for weight={weight_key}, zone={zone}")
#         shipping_cost = 5.00  # Minimum fallback
    
#     # Hawaii/Alaska special handling
#     # Hawaii uses 96xxx ZIP codes, Alaska uses 99xxx
#     # These are included in zone calculations, but may require additional surcharges
#     if zip_code.startswith('96') or zip_code.startswith('99'):
#         # USPS Notice 123 includes these in the zone rates, no additional surcharge needed
#         pass
    
#     # USPS Connect Local discount (15% off Ground Advantage)
#     if connect_local and service_type == "ground_advantage":
#         shipping_cost *= 0.85
    
#     return round(shipping_cost, 2)

RATE_TABLES = {
    "ground_advantage": USPS_GROUND_ADVANTAGE_RETAIL,
    "priority_mail": USPS_PRIORITY_MAIL_RETAIL,
    "priority_express": USPS_PRIORITY_MAIL_EXPRESS,
}

def calculate_usps_shipping(dest_zip, weight_kg, service_type="ground_advantage"):
    weight_grams = float(weight_kg) * 1000
    weight_lbs = round(weight_grams / GRAMS_PER_LB, 2)

    bracket, _ = get_weight_bracket(weight_lbs)
    # Get origin ZIP from environment
    origin_zip = os.getenv('ZIP_CODE', '10001')  # Default to NYC
    
    # Calculate actual distance in miles
    distance_miles = calculate_distance_between_zips(origin_zip, dest_zip)
    
    # Determine USPS zone
    zone = get_usps_zone_from_distance(distance_miles)

    table = RATE_TABLES[service_type]

    return table[bracket][zone]



def calculate_distance_between_zips(origin_zip, destination_zip):
    """
    Calculate great-circle distance in miles between two ZIP codes.
    Uses Haversine formula with data from uszips.csv.
    
    Returns distance in miles, or 500 (default) if ZIP not found.
    """
    origin_data = _zip_cache.get(origin_zip)
    dest_data = _zip_cache.get(destination_zip)
    
    # If either ZIP not found, use a default mid-range distance
    if not origin_data or not dest_data:
        print(f"[WARNING] ZIP not found - origin: {origin_zip in _zip_cache}, dest: {destination_zip in _zip_cache}")
        return 500  # Default to mid-range distance (Zone 5)
    
    # Haversine formula
    lat1, lon1 = origin_data['lat'], origin_data['lng']
    lat2, lon2 = dest_data['lat'], dest_data['lng']
    
    R = 3959  # Earth's radius in miles
    
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    distance = R * c
    return round(distance, 1)


# Request models for type validation
class QuoteRequest(BaseModel):
    zip_code: str
    filament_type: str
    quantity: int = 1
    rush_order: bool = False
    use_usps_connect_local: bool = False
    service_type: str = "ground_advantage"  # ground_advantage, priority_mail, priority_express
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
    # Customer info
    email: str
    name: str
    phone: str
    
    # Delivery address (for Click-N-Ship)
    first_name: Optional[str] = None
    middle_initial: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    street_address: Optional[str] = None
    apt_suite: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: str
    country: str = "United States of America"
    
    # Order details
    filament_type: str
    quantity: int = 1
    rush_order: bool = False
    use_usps_connect_local: bool = False
    volume: float = 0
    weight: float = 0
    
    # Packaging & contents
    packaging_type: Optional[str] = None
    contains_hazmat: bool = False
    contains_live_animals: bool = False
    contains_perishable: bool = False
    contains_cremated_remains: bool = False
    
    # Shipping service selection (from Rating API)
    shipping_service_code: Optional[str] = "03"  # Default to Ground
    shipping_service_name: Optional[str] = "UPS Ground"
    shipping_cost: Optional[float] = None  # Cost in dollars from Rating API


class CheckoutResponse(BaseModel):
    """Response with Stripe payment link"""
    payment_url: str
    total_amount_cents: int


class ShippingRatesRequest(BaseModel):
    """Request to get available shipping options and rates"""
    zip_code: str
    weight: float  # in pounds
    length: float = 5  # in inches
    width: float = 5
    height: float = 5


class ShippingRateOption(BaseModel):
    """Single shipping rate option"""
    serviceCode: str
    serviceName: str
    cost: float
    currency: str
    estimatedDays: Optional[int] = None
    displayCost: str


class ShippingRatesResponse(BaseModel):
    """Response with available shipping rates"""
    error: bool = False
    rates: List[ShippingRateOption] = []
    weight: float = 0
    origin: str = ""
    destination: str = ""
    message: Optional[str] = None


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

        # Shipping cost based on weight (includes all units + packaging)
        total_weight_with_packaging = (total_weight_g * quantity) * 1.15 / 1000  # Add 15% packaging for all units
        shipping_cost = calculate_usps_shipping(
            zip_code, 
            total_weight_with_packaging, 
            service_type=getattr(request_data, 'service_type', 'ground_advantage')
            # express=rush_order, 
            # connect_local=request_data.use_usps_connect_local
        )

        # Total cost before tax
        # NOTE: quantity already applied to material_cost, don't multiply again
        total_cost_before_tax = base_cost + total_material_cost + shipping_cost + rush_order_surcharge

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
        
        # Handle both Trimesh and Scene objects
        if isinstance(mesh, trimesh.Scene):
            # For Scene objects, merge all geometries into a single mesh
            mesh = trimesh.util.concatenate([geom for geom in mesh.geometry.values()])
        
        # Ensure mesh is a Trimesh object with volume attribute
        if not isinstance(mesh, trimesh.Trimesh):
            raise HTTPException(status_code=400, detail="Failed to process 3D model geometry")
        
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
        from .models import Customer, PrintOrder
        from .database import SessionLocal
        
        db = SessionLocal()
        
        try:
            # Debug: Check Stripe configuration
            print(f"[DEBUG] stripe.api_key set: {bool(stripe.api_key)}")
            print(f"[DEBUG] stripe.api_key value: {stripe.api_key[:20] if stripe.api_key else 'None'}...")
            print(f"[DEBUG] STRIPE_ENABLED: {os.getenv('STRIPE_ENABLED')}")
            print(f"[DEBUG] STRIPE_SECRET_KEY set: {bool(os.getenv('STRIPE_SECRET_KEY'))}")
            print(f"[DEBUG] STRIPE_API_KEY set: {bool(os.getenv('STRIPE_API_KEY'))}")
            
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
            
            def money_to_cents(amount: str) -> int:
                return int(float(amount.replace('$', '').replace(',', '')) * 100)

            base_cost_cents = money_to_cents(quote_response['base_cost'])
            material_cost_cents = money_to_cents(quote_response['material_cost'])
            rush_surcharge_cents = money_to_cents(quote_response['rush_order_surcharge'])
            
            # Use UPS shipping cost if provided, otherwise fall back to USPS quote
            if request_data.shipping_cost is not None:
                # Convert float dollars to cents
                shipping_cost_cents = int(request_data.shipping_cost * 100)
            else:
                # Fall back to USPS shipping cost from quote
                shipping_cost_cents = money_to_cents(quote_response['shipping_cost'])
            
            # Recalculate subtotal with actual shipping cost
            subtotal_cents = base_cost_cents + material_cost_cents + shipping_cost_cents + rush_surcharge_cents
            
            # Recalculate tax based on actual subtotal and ZIP code
            sales_tax_cents = int(subtotal_cents * (0.07 if request_data.state != 'DE' else 0))  # Approximate tax
            # Get exact tax from our tax rates
            state = get_state_from_zip(request_data.zip_code)
            if state and state in sales_tax_rates:
                tax_rate = sales_tax_rates[state] / 100
                sales_tax_cents = int(subtotal_cents * tax_rate)
            
            total_amount_cents = subtotal_cents + sales_tax_cents

            density = material_densities.get(request_data.filament_type, 0)
            if request_data.weight > 0:
                total_weight_g = request_data.weight
            else:
                total_weight_g = max(request_data.volume * density, MINIMUM_WEIGHT_G)
            shipping_weight_g = (total_weight_g * request_data.quantity) * 1.15

            origin_zip = os.getenv('ZIP_CODE', '10001')
            distance_miles = calculate_distance_between_zips(origin_zip, request_data.zip_code)
            shipping_zone = get_usps_zone_from_distance(distance_miles)
            
            # Check if customer exists or create new one
            customer = db.query(Customer).filter_by(email=request_data.email).first()
            if not customer:
                customer = Customer(
                    name=request_data.name,
                    email=request_data.email,
                    phone=request_data.phone or '',
                )
                db.add(customer)
                db.flush()  # Flush to get customer.id without committing yet
            
            # Create Stripe customer
            stripe_customer_id = stripe_service.get_or_create_stripe_customer(customer)
            print(f"[DEBUG] stripe_customer_id: {stripe_customer_id}")
            
            if not stripe_customer_id:
                raise HTTPException(status_code=500, detail="Failed to create payment link. Stripe may not be configured.")
            
            # Generate order number
            order_count = db.query(PrintOrder).count()
            order_number = f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{order_count + 1:03d}"
            
            # Create the PrintOrder in database (status: pending_payment)
            print_order = PrintOrder(
                customer_id=customer.id,
                order_number=order_number,
                model_filename=request_data.filament_type,  # Placeholder - would be actual filename in full implementation
                volume_cm3=request_data.volume,
                weight_g=request_data.weight,
                quantity=request_data.quantity,
                rush_order=request_data.rush_order,
                material_id=1,  # Default to first material (will be updated when order is confirmed)
                delivery_zip_code=request_data.zip_code,
                delivery_address=request_data.street_address or '',
                delivery_first_name=request_data.first_name or '',
                delivery_middle_initial=request_data.middle_initial or '',
                delivery_last_name=request_data.last_name or '',
                delivery_company=request_data.company or '',
                delivery_street=request_data.street_address or '',
                delivery_apt_suite=request_data.apt_suite or '',
                delivery_city=request_data.city or '',
                delivery_state=request_data.state or '',
                delivery_country=request_data.country,
                delivery_email=request_data.email,
                delivery_phone=request_data.phone or '',
                # Quote-derived amounts
                subtotal_cents=subtotal_cents,
                tax_cents=sales_tax_cents,
                total_cents=total_amount_cents,
                shipping_cost_cents=shipping_cost_cents,
                shipping_zone=shipping_zone,
                shipping_weight_g=shipping_weight_g,
                package_value_cents=total_amount_cents,
                # Packaging & contents
                contains_hazmat=request_data.contains_hazmat,
                contains_live_animals=request_data.contains_live_animals,
                contains_perishable=request_data.contains_perishable,
                contains_cremated_remains=request_data.contains_cremated_remains,
                packaging_type=request_data.packaging_type,
                # Status fields
                order_status='pending_payment',  # Will be 'payment_received' after successful payment
                label_status='not_created',
                payment_status='unpaid',  # Will be 'paid' after Stripe webhook
            )
            db.add(print_order)
            db.flush()  # Get the order ID
            
            # Create a temporary object for payment link creation
            class TempPrintOrder:
                def __init__(self):
                    self.id = print_order.id
                    self.order_number = print_order.order_number
                    self.customer_id = customer.id
                    self.material_id = None
                    self.model_filename = print_order.model_filename
                    self.volume_cm3 = print_order.volume_cm3
                    self.weight_g = print_order.weight_g
                    self.quantity = print_order.quantity
                    self.rush_order = print_order.rush_order
                    self.delivery_zip_code = print_order.delivery_zip_code
                    self.delivery_address = print_order.delivery_address
                    self.total_cents = total_amount_cents
                    self.scheduled_print_date = None
                    self.customer = customer
                    self.material = type('obj', (object,), {'name': request_data.filament_type})()
            
            order = TempPrintOrder()
            
            # Create payment link using stripe_service
            payment_url = stripe_service.create_payment_link_for_order(order, None, customer) # pyright: ignore[reportArgumentType]
            
            if not payment_url:
                # Rollback the order creation if payment link fails
                db.rollback()
                raise HTTPException(status_code=500, detail="Failed to create payment link. Stripe may not be configured.")
            
            # Store Stripe payment link in order for reference
            setattr(print_order, 'stripe_payment_link', payment_url)
            setattr(print_order, 'stripe_session_id', payment_url.split('/')[-1])  # Extract session ID from URL
            
            # Commit the order to database
            db.commit()
            
            return CheckoutResponse(
                payment_url=payment_url,
                total_amount_cents=total_amount_cents
            )
        
        finally:
            db.close()
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error during checkout: {e}")
        import traceback
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Checkout error: {str(e)}")


@app.get('/api/order-details')
async def get_order_details(order_id: Optional[str] = None, customer_id: Optional[str] = None):
    """Get order details after successful payment (optional - for payment success page)"""
    try:
        from .database import SessionLocal
        from .models import PrintOrder

        # Convert string "None" to actual None (frontend passes "None" as string literal)
        if order_id == "None" or not order_id:
            order_id = None
        if customer_id == "None" or not customer_id:
            customer_id = None
        
        # Try to parse as integers if they're not None
        parsed_order_id: Optional[int]
        parsed_customer_id: Optional[int]

        try:
            parsed_order_id = int(order_id) if order_id not in (None, "None", "") else None
            parsed_customer_id = int(customer_id) if customer_id not in (None, "None", "") else None
        except ValueError:
            parsed_order_id = None
            parsed_customer_id = None

        
        if not parsed_order_id or not parsed_customer_id:
            return {
                "status": "success",
                "message": "Order confirmed"
            }

        db = SessionLocal()
        try:
            order = db.query(PrintOrder).filter(
                PrintOrder.id == parsed_order_id,
                PrintOrder.customer_id == parsed_customer_id
            ).first()

            if not order:
                return {
                    "status": "success",
                    "message": "Order confirmed"
                }

            if getattr(order, 'payment_status', None) != 'paid':
                setattr(order, 'payment_status', 'paid')
                setattr(order, 'order_status', 'payment_received')
                if not getattr(order, 'paid_at', None):
                    setattr(order, 'paid_at', datetime.utcnow())
                db.commit()

            created_at = getattr(order, 'created_at', None)
            return {
                "order_id": getattr(order, 'id', None),
                "customer_id": getattr(order, 'customer_id', None),
                "order_number": getattr(order, 'order_number', None),
                "order_date": created_at.isoformat() if created_at is not None else None,
                "status": "confirmed",
                "message": "Your order has been confirmed. Check your email for details.",
                "estimated_delivery": "3-5 business days"
            }
        finally:
            db.close()
    
    except Exception as e:
        logging.error(f"Error fetching order details: {e}")
        # Don't throw error - payment was successful, just return minimal response
        return {
            "status": "success",
            "message": "Your payment was successful. Check your email for order details."
        }


# ============================================================================
# SHIPPING LABEL DASHBOARD ENDPOINTS
# ============================================================================

class ShippingLabelResponse(BaseModel):
    """Shipping label data for Click-N-Ship"""
    order_id: int
    order_number: str
    order_created_at: str
    
    # Shipping Information
    ship_date: str
    ship_from_zip: str  # Your default return ZIP (you'll fill in manually)
    
    # Ship To (from customer data)
    ship_to_first_name: Optional[str]
    ship_to_middle_initial: Optional[str]
    ship_to_last_name: Optional[str]
    ship_to_company: Optional[str]
    ship_to_street: Optional[str]
    ship_to_apt_suite: Optional[str]
    ship_to_city: Optional[str]
    ship_to_state: Optional[str]
    ship_to_zip: str
    ship_to_country: str
    ship_to_email: str
    ship_to_phone: str
    
    # Reference numbers
    reference_1: Optional[str]
    reference_2: Optional[str]
    
    # Content & Packaging
    contains_hazmat: bool
    contains_live_animals: bool
    contains_perishable: bool
    contains_cremated_remains: bool
    packaging_type: Optional[str]
    package_value_dollars: float
    
    # Shipping data
    weight_g: float
    volume_cm3: float
    quantity: int
    
    # Selected service & cost
    selected_service: Optional[str]
    shipping_cost_dollars: float
    total_order_cost_dollars: float
    
    # Label status
    label_status: str
    usps_tracking_number: Optional[str]


@app.get('/api/dashboard/shipping-labels')
async def get_shipping_labels():
    """Get shipping labels for dashboard (pending + labeled)"""
    from .models import PrintOrder, Customer, Material
    from .database import SessionLocal
    from .ups_service import ups_service
    
    db = SessionLocal()
    try:
        # Query for paid orders that should appear on the dashboard
        # - Payment received
        # - Pending or labeled status
        orders = db.query(PrintOrder).filter(
            PrintOrder.payment_status == 'paid',
            PrintOrder.label_status.in_(["not_created", "pending", "created", "printed", "shipped"])
        ).order_by(PrintOrder.created_at.desc()).all()
        
        orders_data = []
        for order in orders:
            created_at = getattr(order, 'created_at', None)
            ship_date = getattr(order, 'ship_date', None)
            label_created_date = getattr(order, 'label_created_at', None)
            order_dict = {
                "id": getattr(order, 'id', None),
                "order_number": getattr(order, 'order_number', None),
                "created_at": created_at.isoformat() if created_at else None,
                "ship_date": ship_date.isoformat() if ship_date else None,
                "reference_number_1": order.reference_number_1,
                "reference_number_2": order.reference_number_2,
                "customer_name": order.customer.name if order.customer else "Unknown",
                "customer_email": order.customer.email if order.customer else "",
                "delivery_address": {
                    "first_name": order.delivery_first_name,
                    "middle_initial": order.delivery_middle_initial,
                    "last_name": order.delivery_last_name,
                    "company": order.delivery_company,
                    "street": order.delivery_street,
                    "apt_suite": order.delivery_apt_suite,
                    "city": order.delivery_city,
                    "state": order.delivery_state,
                    "zip": order.delivery_zip_code,
                    "country": order.delivery_country,
                    "email": order.delivery_email,
                    "phone": order.delivery_phone,
                },
                "shipping_details": {
                    "weight_g": order.weight_g,
                    "shipping_weight_g": order.shipping_weight_g,
                    "volume_cm3": order.volume_cm3,
                    "quantity": order.quantity,
                    "rush_order": order.rush_order,
                    "shipping_cost_cents": order.shipping_cost_cents,
                    "shipping_zone": order.shipping_zone,
                },
                "packaging": {
                    "type": order.packaging_type,
                    "contains_hazmat": order.contains_hazmat,
                    "contains_live_animals": order.contains_live_animals,
                    "contains_perishable": order.contains_perishable,
                    "contains_cremated_remains": order.contains_cremated_remains,
                },
                "label_status": order.label_status,
                "label_created_at": label_created_date.isoformat() if label_created_date else None,
                "billing_option": order.billing_option or '01',
                "tracking_number": order.usps_tracking_number,
                "ups_tracking_number": order.ups_tracking_number,
                "ups_shipment_id": order.ups_shipment_id,
                "ups_label_image": order.ups_label_image,
                "ups_label_image_format": order.ups_label_image_format,
                "total_cost_cents": order.total_cents,
                "package_value_cents": order.package_value_cents,
            }
            
            orders_data.append(order_dict)
        
        return {
            "orders": orders_data,
            "total_pending": len([order for order in orders_data if order.get("label_status") in ("not_created", "pending")]),
            "message": f"Found {len(orders_data)} paid orders"
        }
    
    finally:
        db.close()


@app.get('/api/dashboard/shipping-labels/{order_id}')
async def get_shipping_label(order_id: int):
    """Get shipping label data for a specific order"""
    from .models import PrintOrder
    from .database import SessionLocal
    
    db = SessionLocal()
    try:
        order = db.query(PrintOrder).filter(PrintOrder.id == order_id).first()
        
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        created_at = getattr(order, 'created_at', None)
        ship_date = getattr(order, 'ship_date', None)
        label_created_date = getattr(order, 'label_created_at', None)

        return {
            "order_id": getattr(order, 'id', None),
            "order_number": getattr(order, 'order_number', None),
            "created_at": created_at.isoformat() if created_at else None,
            "ship_date": ship_date.isoformat() if ship_date else None,
            "reference_number_1": order.reference_number_1,
            "reference_number_2": order.reference_number_2,
            "ship_to": {
                "first_name": order.delivery_first_name,
                "middle_initial": order.delivery_middle_initial,
                "last_name": order.delivery_last_name,
                "company": order.delivery_company,
                "street": order.delivery_street,
                "apt_suite": order.delivery_apt_suite,
                "city": order.delivery_city,
                "state": order.delivery_state,
                "zip": order.delivery_zip_code,
                "country": order.delivery_country,
                "email": order.delivery_email,
                "phone": order.delivery_phone,
            },
            "weight_g": order.weight_g,
            "shipping_weight_g": order.shipping_weight_g,
            "volume_cm3": order.volume_cm3,
            "quantity": order.quantity,
            "shipping_cost_cents": order.shipping_cost_cents,
            "shipping_zone": order.shipping_zone,
            "packaging_type": order.packaging_type,
            "contains_hazmat": order.contains_hazmat,
            "contains_live_animals": order.contains_live_animals,
            "contains_perishable": order.contains_perishable,
            "contains_cremated_remains": order.contains_cremated_remains,
            "label_status": order.label_status,
            "label_created_at": label_created_date.isoformat() if label_created_date else None,
            "tracking_number": order.usps_tracking_number,
            "ups_tracking_number": order.ups_tracking_number,
            "ups_shipment_id": order.ups_shipment_id,
            "ups_label_image": order.ups_label_image,
            "ups_label_image_format": order.ups_label_image_format,
            "total_cost_cents": order.total_cents,
        }
    
    finally:
        db.close()


@app.post('/api/dashboard/shipping-labels/{order_id}/create-label-ups')
async def create_label_ups(order_id: int, label_request: Optional[dict] = None):
    """
    Create a UPS shipping label and mark the order as labeled.
    
    The UPS Shipping API will generate a tracking number and label.
    """
    from .models import PrintOrder
    from .database import SessionLocal
    from .ups_service import ups_service
    
    db = SessionLocal()
    try:
        order = db.query(PrintOrder).filter(PrintOrder.id == order_id).first()
        
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # Get delivery and shipping info (prefer normalized fields; delivery_address is legacy freeform text)
        delivery = {
            "first_name": order.delivery_first_name or "",
            "last_name": order.delivery_last_name or "",
            "street": order.delivery_street or order.delivery_address or "",
            "city": order.delivery_city or "",
            "state": order.delivery_state or "",
            "zip": order.delivery_zip_code or "",
        }
        if getattr(order, 'delivery_apt_suite', None) is not None and getattr(order, 'delivery_apt_suite', "") != "":
            delivery["street"] = f"{delivery['street']} {getattr(order, 'delivery_apt_suite', '')}".strip()

        # Get shipper info (default to NYC, configurable via env)
        shipper_zip = os.getenv("SHIPPER_ZIP", "10001")
        shipper_city = get_city_from_zip(shipper_zip) or "New York"
        shipper_state = get_state_from_zip(shipper_zip) or "NY"
        shipper_name = os.getenv("SHIPPER_NAME", "Print3D Shop")
        shipper_street = os.getenv("SHIPPER_STREET", "123 Main St")
        
        # Convert weight from grams to pounds
        weight_grams = order.shipping_weight_g or order.weight_g or 0

        # If weight_grams might be a SQLAlchemy Column, extract its value
        try:
            # Handle SQLAlchemy Column objects by checking for the value attribute
            if hasattr(weight_grams, 'value'):
                weight_grams = float(getattr(weight_grams, 'value')) if getattr(weight_grams, 'value') else 0.0
            else:
                weight_grams = float(getattr(order, "weight_grams", 0)) if getattr(order, "weight_grams", 0) else 0.0
        except (TypeError, ValueError, AttributeError):
            weight_grams = 0.0

        weight_lbs = round(weight_grams / GRAMS_PER_LB, 2)
        
        # Determine service type from selected_service or default to Ground (03)
        service_type = "03"  # UPS Ground
        if getattr(order, "selected_service", None):
            if "express" in order.selected_service.lower():
                service_type = "01"  # Next Day
            elif "priority" in order.selected_service.lower():
                service_type = "02"  # 2nd Day
        
        # Create the label via UPS API
        label_result = await ups_service.create_label(
            from_name=shipper_name,
            from_street=shipper_street,
            from_city=shipper_city,
            from_state=shipper_state,
            from_zip=shipper_zip,
            to_name=f"{getattr(delivery, 'first_name', '')} {getattr(delivery, 'last_name', '')}".strip(),
            to_street=getattr(delivery, 'street', ''),
            to_city=getattr(delivery, 'city', ''),
            to_state=getattr(delivery, 'state', ''),
            to_zip=getattr(delivery, 'zip', ''),
            weight_lbs=weight_lbs,
            service_type=service_type,
            billing_option=getattr(order, "billing_option", "01")
        )
        
        # Handle label creation errors
        if label_result.get('error'):
            logging.error(f"UPS label creation failed for order {order_id}: {label_result.get('message')}")
            return {
                "error": True,
                "code": label_result.get('code'),
                "message": label_result.get('message')
            }
        
        # Update order with tracking number and label status
        tracking_number = label_result.get('tracking_number')
        setattr(order, "ups_tracking_number", tracking_number)
        setattr(order, "ups_shipment_id", label_result.get('shipment_id'))
        setattr(order, "ups_label_image", label_result.get('label_image'))
        setattr(order, "ups_label_image_format", label_result.get('label_image_format'))
        setattr(order, "label_status", 'created')
        setattr(order, "label_created_at", datetime.utcnow())
        
        db.commit()
        
        logging.info(f"UPS label created for order {order_id}: tracking={tracking_number}")
        
        return {
            "error": False,
            "tracking_number": tracking_number,
            "label_image": label_result.get('label_image'),
            "label_image_format": label_result.get('label_image_format'),
            "shipment_id": label_result.get('shipment_id'),
            "message": "Label created successfully"
        }
    
    except Exception as e:
        db.rollback()
        logging.error(f"Error creating UPS label for order {order_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create label: {str(e)}")
    finally:
        db.close()


# Legacy USPS label marking endpoint (kept for backwards compatibility)
# @app.patch('/api/dashboard/shipping-labels/{order_id}/mark-labeled')
# async def mark_usps_labeled(order_id: int, tracking_number: str = None):
#     """
#     Legacy: Mark a USPS order as labeled with a tracking number.
#     Use create-label-ups for new UPS integrations.
#     """
#     from .models import PrintOrder
#     from .database import SessionLocal
#     
#     db = SessionLocal()
#     try:
#         order = db.query(PrintOrder).filter(PrintOrder.id == order_id).first()
#         
#         if not order:
#             raise HTTPException(status_code=404, detail="Order not found")
#         
#         order.usps_tracking_number = tracking_number
#         order.label_status = 'created'
#         order.label_created_at = datetime.utcnow()
#         
#         db.commit()
#         
#         return {
#             "error": False,
#             "tracking_number": tracking_number,
#             "message": "Label status updated"
#         }
#     
#     except Exception as e:
#         db.rollback()
#         logging.error(f"Error updating label status: {e}")
#         raise HTTPException(status_code=500, detail="Failed to update label status")
#     finally:
#         db.close()


@app.patch('/api/dashboard/shipping-labels/{order_id}')
async def update_shipping_label(order_id: int, label_data: dict):
    """Update shipping label status and tracking info"""
    from .models import PrintOrder
    from .database import SessionLocal
    
    db = SessionLocal()
    try:
        order = db.query(PrintOrder).filter(PrintOrder.id == order_id).first()
        
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # Update fields from the request
        if 'label_status' in label_data:
            order.label_status = label_data['label_status']
        
        if 'usps_tracking_number' in label_data:
            order.usps_tracking_number = label_data['usps_tracking_number']
        
        if 'selected_service' in label_data:
            order.selected_service = label_data['selected_service']
        
        if 'label_created_at' in label_data:
            setattr(order, "label_created_at", datetime.fromisoformat(label_data['label_created_at']))

        if 'ship_date' in label_data:
            ship_date = label_data['ship_date']
            setattr(order, "ship_date", datetime.fromisoformat(ship_date) if ship_date else None)
        if 'reference_number_1' in label_data:
            setattr(order, "reference_number_1", label_data['reference_number_1'])

        if 'reference_number_2' in label_data:
            setattr(order, "reference_number_2", label_data['reference_number_2'])

        if 'packaging_type' in label_data:
            setattr(order, "packaging_type", label_data['packaging_type'])

        if 'contains_hazmat' in label_data:
            setattr(order, "contains_hazmat", bool(label_data['contains_hazmat']))

        if 'contains_live_animals' in label_data:
            setattr(order, "contains_live_animals", bool(label_data['contains_live_animals']))

        if 'contains_perishable' in label_data:
            setattr(order, "contains_perishable", bool(label_data['contains_perishable']))

        if 'contains_cremated_remains' in label_data:
            setattr(order, "contains_cremated_remains", bool(label_data['contains_cremated_remains']))

        if 'package_value_cents' in label_data:
            package_value = label_data['package_value_cents']
            setattr(order, "package_value_cents", int(package_value) if package_value is not None else None)
        
        if 'billing_option' in label_data:
            setattr(order, "billing_option", label_data['billing_option'])
        
        setattr(order, "updated_at", datetime.utcnow())
        
        db.commit()
        
        return {
            "order_id": order_id,
            "status": "updated",
            "label_status": getattr(order, "label_status"),
            "tracking_number": getattr(order, "usps_tracking_number"),
        }
    
    finally:
        db.close()


@app.post('/api/validate-address')
async def validate_address(request: dict):
    """
    Validate and standardize a USPS address using the official USPS Addresses API
    
    On-demand validation to prevent rate limiting. Returns standardized address
    and provides options when multiple addresses match (code 22).
    """
    from .usps_service import usps_service, AddressValidationRequest
    
    try:
        # Convert request dict to validation request
        validation_request = AddressValidationRequest(
            firm=request.get("firm", ""),
            streetAddress=request.get("streetAddress", ""),
            secondaryAddress=request.get("secondaryAddress", ""),
            city=request.get("city", ""),
            state=request.get("state", ""),
            urbanization=request.get("urbanization", ""),
            ZIPCode=request.get("ZIPCode", ""),
            ZIPPlus4=request.get("ZIPPlus4", "")
        )
        
        result = await usps_service.validate_address(validation_request)
        
        # Handle rate limiting specifically
        if result.get("code") == "RATE_LIMITED":
            return {
                "error": True,
                "code": "RATE_LIMITED",
                "message": result.get("message"),
                "retry_after_seconds": result.get("retry_after_seconds", 30)
            }
        
        # Handle other errors
        if result.get("error"):
            logging.error(f"Address validation error: {result.get('message')}")
            return {
                "error": True,
                "code": result.get("code"),
                "message": result.get("message")
            }
        
        # Success - process the validated address
        data = result.get("data", {})
        corrections = data.get("corrections", [])
        matches = data.get("matches", [])
        address = data.get("address", {})
        additional_info = data.get("additionalInfo", {})
        
        # Check if there are multiple address matches (code 22)
        has_multiple_matches = any(c.get("code") == "22" for c in corrections)
        
        return {
            "error": False,
            "address": address,
            "additionalInfo": additional_info,
            "corrections": corrections,
            "matches": matches,
            "hasMultipleMatches": has_multiple_matches,
            "warnings": data.get("warnings", [])
        }
    
    except ValueError as e:
        logging.error(f"Invalid address validation request: {e}")
        return {
            "error": True,
            "code": "VALIDATION_ERROR",
            "message": f"Invalid request: {str(e)}"
        }
    except Exception as e:
        logging.error(f"Address validation error: {e}")
        return {
            "error": True,
            "code": "SERVER_ERROR",
            "message": "An error occurred during address validation"
        }


@app.post('/api/validate-address-ups')
async def validate_address_ups(request: dict):
    """
    Validate and standardize a UPS address using the UPS Address Validation API
    
    On-demand validation. Returns standardized address and provides options when 
    multiple addresses match.
    """
    from .ups_service import ups_service, AddressValidationRequest
    
    try:
        # Convert request dict to UPS validation request
        validation_request = AddressValidationRequest(
            firm=request.get("firm", ""),
            streetAddress=request.get("streetAddress", ""),
            secondaryAddress=request.get("secondaryAddress", ""),
            city=request.get("city", ""),
            state=request.get("state", ""),
            zipCode=request.get("ZIPCode", ""),
            zipPlus4=request.get("ZIPPlus4", ""),
            urbanization=request.get("urbanization", "")
        )
        
        result = await ups_service.validate_address(validation_request)
        
        # Handle invalid / unsupported addresses
        if not result.valid:
            return {
                "error": True,
                "code": "INVALID_ADDRESS",
                "message": (
                    result.alerts[0].get("message")
                    if result.alerts else
                    "UPS could not validate this address"
                ),
                "carrier": "UPS",
                "alerts": result.alerts
            }

        # Handle rate limiting specifically
        if result.alerts and any(alert.get("code") == "RATE_LIMITED" for alert in result.alerts):
            return {
                "error": True,
                "code": "RATE_LIMITED",
                "message": "Too many requests to UPS API",
                "retry_after_seconds": 30
            }
        
        # Handle validation errors
        if result.alerts and result.alerts[0].get("code") in ["AUTH_ERROR", "UNCONFIGURED", "TIMEOUT", "REQUEST_ERROR"]:
            logging.error(f"Address validation error: {result.alerts[0].get('message')}")
            return {
                "error": True,
                "code": result.alerts[0].get("code"),
                "message": result.alerts[0].get("message")
            }
        
        # Success - process the validated address
        primary_address = result.address
        candidates = result.candidates or []
        
        # Format response to match USPS response structure for frontend compatibility
        matches = []
        if candidates and len(candidates) > 1:
            matches = [
                {
                    "address": {
                        "streetAddress": c.get("streetAddress"),
                        "city": c.get("city"),
                        "state": c.get("state"),
                        "ZIPCode": c.get("zipCode"),
                        "ZIPPlus4": c.get("zipPlus4")
                    }
                }
                for c in candidates
            ]
        
        return {
            "error": False,
            "address": {
                "streetAddress": primary_address.get("streetAddress") if primary_address else None,
                "city": primary_address.get("city") if primary_address else None,
                "state": primary_address.get("state") if primary_address else None,
                "ZIPCode": primary_address.get("zipCode") if primary_address else None,
                "ZIPPlus4": primary_address.get("zipPlus4") if primary_address else None
            } if primary_address else None,
            "matches": matches,
            "hasMultipleMatches": result.ambiguous,
            "classification": result.classification,
            "carrier": "UPS"
        }
    
    except ValueError as e:
        logging.error(f"Invalid address validation request: {e}")
        return {
            "error": True,
            "code": "VALIDATION_ERROR",
            "message": f"Invalid request: {str(e)}"
        }
    except Exception as e:
        logging.error(f"Address validation error: {e}")
        return {
            "error": True,
            "code": "SERVER_ERROR",
            "message": "An error occurred during address validation"
        }


@app.get('/api/lookup/zip-location/{zip_code}')
async def lookup_zip_location(zip_code: str):
    """Lookup city and state for a ZIP code - for prefilling checkout form"""
    try:
        city = get_city_from_zip(zip_code)
        state = get_state_from_zip(zip_code)
        
        if not city or not state:
            raise HTTPException(status_code=404, detail="ZIP code not found")
        
        return {
            "zip_code": zip_code,
            "city": city,
            "state": state
        }
    except Exception as e:
        logging.error(f"Error looking up ZIP code {zip_code}: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid ZIP code: {str(e)}")


@app.post('/api/shipping-rates', response_model=ShippingRatesResponse)
async def get_shipping_rates(request_data: ShippingRatesRequest):
    """
    Get available UPS shipping rates for a package.
    
    Returns list of available services with costs and estimated delivery times.
    """
    try:
        zip_code = request_data.zip_code
        weight_grams = request_data.weight
        weight_lbs = round(weight_grams / GRAMS_PER_LB, 2)
        length = request_data.length
        width = request_data.width
        height = request_data.height
        
        # Validate inputs
        if not zip_code or not _zip_cache.get(zip_code):
            return ShippingRatesResponse(
                error=True,
                message="Invalid ZIP code",
                rates=[]
            )

        if weight_lbs <= 0 or weight_lbs > 150:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid package weight: {weight_lbs} lbs"
            )
        
        # Get shipper location (default from env or config)
        shipper_zip = os.getenv("SHIPPER_ZIP_CODE", "21093")  # Default MD location
        shipper_city = get_city_from_zip(shipper_zip) or "Timonium"
        shipper_state = get_state_from_zip(shipper_zip) or "MD"
        
        # Get recipient location
        recipient_city = get_city_from_zip(zip_code)
        recipient_state = get_state_from_zip(zip_code)
        
        if not recipient_city or not recipient_state:
            return ShippingRatesResponse(
                error=True,
                message=f"Could not find city/state for ZIP code {zip_code}",
                rates=[]
            )
        
        # Call UPS Rating API
        from . import ups_service as ups_module
        
        rates_response = await ups_module.ups_service.get_shipping_rates(
            from_zip=shipper_zip,
            from_city=shipper_city,
            from_state=shipper_state,
            to_zip=zip_code,
            to_city=recipient_city,
            to_state=recipient_state,
            weight_lbs=weight_lbs,
            length_in=length,
            width_in=width,
            height_in=height,
            get_all_services=True
        )
        
        if rates_response.get("error"):
            return ShippingRatesResponse(
                error=True,
                message=rates_response.get("message", "Failed to get shipping rates"),
                rates=[]
            )
        
        # Convert rate objects to ShippingRateOption models
        rates = []
        for rate in rates_response.get("rates", []):
            rates.append(ShippingRateOption(
                serviceCode=rate.get("serviceCode"),
                serviceName=rate.get("serviceName"),
                cost=rate.get("cost", 0),
                currency=rate.get("currency", "USD"),
                estimatedDays=rate.get("estimatedDays"),
                displayCost=rate.get("displayCost", "$0.00")
            ))
        
        return ShippingRatesResponse(
            error=False,
            rates=rates,
            weight=weight_lbs,
            origin=rates_response.get("origin", ""),
            destination=rates_response.get("destination", "")
        )
    
    except Exception as e:
        logging.error(f"Error getting shipping rates: {e}")
        return ShippingRatesResponse(
            error=True,
            message=f"Error getting shipping rates: {str(e)}",
            rates=[]
        )


@app.get('/api/dashboard/track/{tracking_number}')
async def track_shipment(tracking_number: str):
    """
    Track a UPS shipment using the provided tracking number.
    
    Returns tracking information including current status, location, and activity history.
    Note: UPS retains tracking data for 120 days after shipment pickup.
    """
    try:
        from . import ups_service as ups_module
        
        # Use the UPS service to get tracking information
        result = await ups_module.ups_service.track_shipment(tracking_number)
        
        if result.get('error'):
            raise HTTPException(status_code=400, detail=result.get('message', 'Failed to track shipment'))
        
        return result
    
    except Exception as e:
        logging.error(f"Error tracking shipment {tracking_number}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to track shipment: {str(e)}")


# Mount static files (React app) - must be after API routes
app.mount("/", StaticFiles(directory="static", html=True), name="static")
