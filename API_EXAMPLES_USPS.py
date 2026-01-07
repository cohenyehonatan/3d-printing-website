#!/usr/bin/env python3
"""
Example API calls demonstrating the USPS rate integration
Shows how to use the new service_type parameter
"""

import json

# Example 1: Ground Advantage (economical option)
example_ground_advantage = {
    "method": "POST",
    "endpoint": "/api/quote",
    "request": {
        "zip_code": "90210",
        "filament_type": "PLA",
        "quantity": 1,
        "rush_order": False,
        "use_usps_connect_local": False,
        "service_type": "ground_advantage",
        "volume": 150.5,
        "weight": 0.0
    },
    "expected_response": {
        "total_cost_with_tax": "$245.65",
        "sales_tax": "$19.87",
        "base_cost": "$50.00",
        "material_cost": "$150.00",
        "shipping_cost": "$25.78",
        "rush_order_surcharge": "$0.00"
    },
    "notes": "Basic quote with Ground Advantage shipping to California"
}

# Example 2: Priority Mail (faster delivery)
example_priority_mail = {
    "method": "POST",
    "endpoint": "/api/quote",
    "request": {
        "zip_code": "60601",
        "filament_type": "PETG",
        "quantity": 2,
        "rush_order": False,
        "use_usps_connect_local": False,
        "service_type": "priority_mail",
        "volume": 200.0,
        "weight": 0.0
    },
    "expected_response": {
        "total_cost_with_tax": "$575.42",
        "sales_tax": "$46.32",
        "base_cost": "$100.00",
        "material_cost": "$385.00",
        "shipping_cost": "$44.10",
        "rush_order_surcharge": "$0.00"
    },
    "notes": "Quantity 2 with Priority Mail to Chicago (higher cost but faster)"
}

# Example 3: Priority Express (fastest delivery)
example_priority_express = {
    "method": "POST",
    "endpoint": "/api/quote",
    "request": {
        "zip_code": "02101",
        "filament_type": "ABS",
        "quantity": 1,
        "rush_order": True,
        "use_usps_connect_local": False,
        "service_type": "priority_express",
        "volume": 100.0,
        "weight": 0.0
    },
    "expected_response": {
        "total_cost_with_tax": "$364.88",
        "sales_tax": "$28.94",
        "base_cost": "$50.00",
        "material_cost": "$250.00",
        "shipping_cost": "$35.94",
        "rush_order_surcharge": "$20.00"
    },
    "notes": "Express shipping to Boston with rush order surcharge"
}

# Example 4: Ground Advantage with USPS Connect Local discount
example_connect_local = {
    "method": "POST",
    "endpoint": "/api/quote",
    "request": {
        "zip_code": "78201",
        "filament_type": "TPU",
        "quantity": 1,
        "rush_order": False,
        "use_usps_connect_local": True,
        "service_type": "ground_advantage",
        "volume": 175.5,
        "weight": 0.0
    },
    "expected_response": {
        "total_cost_with_tax": "$228.15",
        "sales_tax": "$18.12",
        "base_cost": "$50.00",
        "material_cost": "$150.00",
        "shipping_cost": "$10.03",  # 15% discount applied
        "rush_order_surcharge": "$0.00"
    },
    "notes": "Ground Advantage with 15% USPS Connect Local discount to Texas"
}

# Example 5: Hawaii/Alaska (included in zone pricing)
example_hawaii = {
    "method": "POST",
    "endpoint": "/api/quote",
    "request": {
        "zip_code": "96801",
        "filament_type": "Nylon",
        "quantity": 1,
        "rush_order": False,
        "use_usps_connect_local": False,
        "service_type": "ground_advantage",
        "volume": 125.0,
        "weight": 0.0
    },
    "expected_response": {
        "total_cost_with_tax": "$265.42",
        "sales_tax": "$21.08",
        "base_cost": "$50.00",
        "material_cost": "$175.00",
        "shipping_cost": "$19.34",  # Zone 9 (highest)
        "rush_order_surcharge": "$0.00"
    },
    "notes": "Hawaii ZIP code automatically assigned to Zone 9 (highest cost)"
}

# Example 6: Backward compatibility - using express parameter
example_backward_compat = {
    "method": "POST",
    "endpoint": "/api/quote",
    "request": {
        "zip_code": "75201",
        "filament_type": "PLA",
        "quantity": 1,
        "rush_order": False,
        "use_usps_connect_local": False,
        "express": True,  # Legacy parameter - still works!
        "volume": 150.0,
        "weight": 0.0
    },
    "note": "express=true automatically selects priority_express service"
}

# cURL examples for testing

curl_ground_advantage = """
curl -X POST http://localhost:8003/api/quote \\
  -H "Content-Type: application/json" \\
  -d '{
    "zip_code": "90210",
    "filament_type": "PLA",
    "quantity": 1,
    "service_type": "ground_advantage",
    "volume": 150.5
  }'
"""

curl_priority_mail = """
curl -X POST http://localhost:8003/api/quote \\
  -H "Content-Type: application/json" \\
  -d '{
    "zip_code": "60601",
    "filament_type": "PETG",
    "quantity": 1,
    "service_type": "priority_mail",
    "volume": 200.0
  }'
"""

curl_connect_local = """
curl -X POST http://localhost:8003/api/quote \\
  -H "Content-Type: application/json" \\
  -d '{
    "zip_code": "78201",
    "filament_type": "TPU",
    "quantity": 1,
    "service_type": "ground_advantage",
    "use_usps_connect_local": true,
    "volume": 175.5
  }'
"""

# JavaScript/Fetch examples

js_ground_advantage = """
fetch('/api/quote', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    zip_code: '90210',
    filament_type: 'PLA',
    quantity: 1,
    service_type: 'ground_advantage',
    volume: 150.5
  })
})
.then(r => r.json())
.then(data => console.log(data))
.catch(e => console.error(e));
"""

js_priority_express = """
fetch('/api/quote', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    zip_code: '02101',
    filament_type: 'ABS',
    quantity: 1,
    service_type: 'priority_express',
    rush_order: true,
    volume: 100.0
  })
})
.then(r => r.json())
.then(data => {
  console.log('Total:', data.total_cost_with_tax);
  console.log('Shipping:', data.shipping_cost);
  console.log('Tax:', data.sales_tax);
})
.catch(e => console.error(e));
"""

# Print all examples
if __name__ == "__main__":
    examples = [
        ("Ground Advantage (economical)", example_ground_advantage),
        ("Priority Mail (faster)", example_priority_mail),
        ("Priority Express (fastest)", example_priority_express),
        ("USPS Connect Local (discount)", example_connect_local),
        ("Hawaii/Alaska (Zone 9)", example_hawaii),
        ("Backward Compatibility", example_backward_compat),
    ]
    
    print("=" * 80)
    print("USPS RATE INTEGRATION - API EXAMPLES")
    print("=" * 80)
    
    for title, example in examples:
        print(f"\n{title}")
        print("-" * 80)
        print(json.dumps(example, indent=2))
    
    print("\n" + "=" * 80)
    print("cURL EXAMPLES")
    print("=" * 80)
    print("\n1. Ground Advantage:")
    print(curl_ground_advantage)
    print("\n2. Priority Mail:")
    print(curl_priority_mail)
    print("\n3. USPS Connect Local:")
    print(curl_connect_local)
    
    print("\n" + "=" * 80)
    print("JAVASCRIPT/FETCH EXAMPLES")
    print("=" * 80)
    print("\n1. Ground Advantage:")
    print(js_ground_advantage)
    print("\n2. Priority Express:")
    print(js_priority_express)
    
    print("\n" + "=" * 80)
    print("SERVICE TYPE OPTIONS")
    print("=" * 80)
    print("""
    "ground_advantage"   - USPS Ground Advantage Retail
                          Economical option, 1-3 business days
                          15% discount with USPS Connect Local
    
    "priority_mail"      - USPS Priority Mail Retail
                          Faster than Ground, includes tracking
                          1-3 business days depending on zone
    
    "priority_express"   - USPS Priority Mail Express Retail
                          Overnight/2-day guaranteed delivery
                          Includes $100 free insurance
    """)
    
    print("=" * 80)
    print("SPECIAL PARAMETERS")
    print("=" * 80)
    print("""
    use_usps_connect_local: bool
        - Only applies to "ground_advantage" service
        - Grants 15% discount off Ground Advantage rates
        - Customer must use USPS Connect Local pickup/drop-off
    
    rush_order: bool
        - Adds $20 surcharge to order
        - Can be combined with any service type
        - express=true automatically selects "priority_express"
    
    service_type: string
        - Default: "ground_advantage"
        - Options: "ground_advantage", "priority_mail", "priority_express"
        - Replaces legacy express parameter for clarity
    """)
