#!/usr/bin/env python3
"""
Test script for USPS Notice 123 rate integration
Tests the new shipping cost calculation with official USPS rates
"""

import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from api.quote import (
    calculate_usps_shipping,
    get_weight_bracket,
    get_usps_zone_from_distance,
    calculate_distance_between_zips,
    AVAILABLE_OZ,
    AVAILABLE_LBS,
    OZ_KEY_MAP,
    USPS_GROUND_ADVANTAGE_RETAIL,
    USPS_PRIORITY_MAIL_RETAIL,
    USPS_PRIORITY_MAIL_EXPRESS
)

OZ_KEY_TO_LABEL = {value: key for key, value in OZ_KEY_MAP.items()}

def test_weight_brackets():
    """Test weight bracket logic"""
    print("=" * 70)
    print("WEIGHT BRACKET TESTS")
    print("=" * 70)
    print(f"Available oz tiers: {AVAILABLE_OZ}")
    print(f"Available lb tiers: {AVAILABLE_LBS}")
    print()
    
    test_cases = [
        (0.2, "4_oz", True),      # 0.2 lbs < 4 oz
        (0.25, "4_oz", True),     # 4 oz boundary
        (0.4, "8_oz", True),      # 0.4 lbs < 8 oz
        (0.5, "8_oz", True),      # 8 oz boundary
        (0.75, "12_oz", True),    # 12 oz boundary
        (0.9, "15_999_oz", True), # < 1 lb
        (1.0, 1, False),     # 1 lb
        (2.5, 3, False),     # 2.5 lbs -> 3 lbs
        (5.0, 5, False),     # 5 lbs
        (70.0, 70, False),   # 70 lbs max
        (75.0, 70, False),   # Over max -> capped at 70
    ]
    
    for weight_lbs, expected_bracket, is_oz in test_cases:
        bracket, returned_is_oz = get_weight_bracket(weight_lbs)
        status = "✓" if bracket == expected_bracket else "✗"
        if returned_is_oz:
            oz_label = OZ_KEY_TO_LABEL.get(bracket, bracket)
            print(f"{status} {weight_lbs:5.1f} lbs -> Bracket: {oz_label} oz")
        else:
            print(f"{status} {weight_lbs:5.1f} lbs -> Bracket: {bracket} lbs")
    print()


def test_zone_determination():
    """Test zone determination from distance"""
    print("=" * 70)
    print("ZONE DETERMINATION TESTS")
    print("=" * 70)
    
    test_cases = [
        (25, 1),      # Local
        (75, 2),      # 50-150
        (200, 3),     # 150-300
        (450, 4),     # 300-600
        (800, 5),     # 600-1000
        (1200, 6),    # 1000-1400
        (1600, 7),    # 1400-1800
        (1900, 8),    # 1800-2000
        (2500, 9),    # 2000+
    ]
    
    for distance, expected_zone in test_cases:
        zone = get_usps_zone_from_distance(distance)
        status = "✓" if zone == expected_zone else "✗"
        print(f"{status} {distance:4d} miles -> Zone {zone} (expected {expected_zone})")
    print()


def test_sample_rates():
    """Display sample rates from rate tables"""
    print("=" * 70)
    print("SAMPLE RATE TABLE VALUES")
    print("=" * 70)
    
    print("\n--- USPS Ground Advantage Retail ---")
    print("Weight (oz/lbs) | Zone 1  | Zone 5  | Zone 9  |")
    print("-" * 50)
    
    for weight in [4, 8, 12, 15.999, 1, 2, 3, 5]:
        key = OZ_KEY_MAP.get(weight, weight)
        z1 = USPS_GROUND_ADVANTAGE_RETAIL[key][1]
        z5 = USPS_GROUND_ADVANTAGE_RETAIL[key][5]
        z9 = USPS_GROUND_ADVANTAGE_RETAIL[key][9]
        unit = "oz" if weight in OZ_KEY_MAP else "lb"
        print(f"{weight:6.3f} {unit:3s}     | ${z1:6.2f} | ${z5:6.2f} | ${z9:6.2f} |")
    
    print("\n--- USPS Priority Mail Retail ---")
    print("Weight (oz/lbs) | Zone 1  | Zone 5  | Zone 9  |")
    print("-" * 50)
    
    for weight in [4, 8, 12, 15.999, 1, 2, 3, 5]:
        key = OZ_KEY_MAP.get(weight, weight)
        z1 = USPS_PRIORITY_MAIL_RETAIL[key][1]
        z5 = USPS_PRIORITY_MAIL_RETAIL[key][5]
        z9 = USPS_PRIORITY_MAIL_RETAIL[key][9]
        unit = "oz" if weight in OZ_KEY_MAP else "lb"
        print(f"{weight:6.3f} {unit:3s}     | ${z1:6.2f} | ${z5:6.2f} | ${z9:6.2f} |")
    
    print("\n--- USPS Priority Mail Express ---")
    print("Weight (oz/lbs) | Zone 1  | Zone 5  | Zone 9  |")
    print("-" * 50)
    
    for weight in [4, 8, 12, 15.999, 1, 2, 3, 5]:
        key = OZ_KEY_MAP.get(weight, weight)
        z1 = USPS_PRIORITY_MAIL_EXPRESS[key][1]
        z5 = USPS_PRIORITY_MAIL_EXPRESS[key][5]
        z9 = USPS_PRIORITY_MAIL_EXPRESS[key][9]
        unit = "oz" if weight in OZ_KEY_MAP else "lb"
        print(f"{weight:6.3f} {unit:3s}     | ${z1:6.2f} | ${z5:6.2f} | ${z9:6.2f} |")
    print()


def test_service_type_comparison():
    """Compare shipping costs across different service types"""
    print("=" * 70)
    print("SERVICE TYPE COMPARISON")
    print("=" * 70)
    distance = calculate_distance_between_zips('33179', '94105')  # Miami to San Francisco
    zone = get_usps_zone_from_distance(distance)
    print(f"(Prices for 2 lbs to Zone {zone})")
    print()
    
    # Set origin ZIP in environment
    os.environ['ZIP_CODE'] = '33179'  # Miami
    
    # Example destination ZIP for Zone 5 (approximately 800 miles from Miami)
    # Let's use a simple comparison
    example_weights_kg = [0.5, 1.0, 2.0, 3.0, 5.0]
    
    print("Weight (kg) | Ground Advantage | Priority Mail | Express     |")
    print("-" * 65)
    
    # Note: Actual calculation will depend on distance from origin ZIP
    # This is just a demonstration structure
    for weight_kg in example_weights_kg:
        try:
            ga_cost = calculate_usps_shipping('94105', weight_kg, service_type='ground_advantage')
            pm_cost = calculate_usps_shipping('94105', weight_kg, service_type='priority_mail')
            pe_cost = calculate_usps_shipping('94105', weight_kg, service_type='priority_express')
            
            print(f"   {weight_kg:4.1f}     |      ${ga_cost:6.2f}      |    ${pm_cost:6.2f}     | ${pe_cost:6.2f}   |")
        except Exception as e:
            print(f"   {weight_kg:4.1f}     | Error: {str(e)[:20]}")
    
    print()


if __name__ == "__main__":
    # Set a default origin ZIP if not in environment
    if 'ZIP_CODE' not in os.environ:
        os.environ['ZIP_CODE'] = '33179'  # Miami as default
    
    test_weight_brackets()
    test_zone_determination()
    test_sample_rates()
    test_service_type_comparison()
    
    print("=" * 70)
    print("USPS RATE INTEGRATION TESTS COMPLETE")
    print("=" * 70)
    print("\nRate tables are now integrated using USPS Notice 123")
    print("(Effective October 5, 2025)")
