"""
UPS Address Validation API Integration Service
Handles OAuth2 token management, address validation, and rate limit handling
"""

import os
import time
import json
import httpx
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ============================================================================
# TOKEN CACHE (In-memory with expiry)
# ============================================================================

class TokenCache:
    """Thread-safe in-memory token cache with TTL"""
    
    def __init__(self):
        self.token: Optional[str] = None
        self.expires_at: Optional[float] = None
    
    def set_token(self, token: str, expires_in: int) -> None:
        """Store token with expiry time (in seconds)"""
        self.token = token
        # Store expiry with 30-second buffer to refresh early
        self.expires_at = time.time() + expires_in - 30
        logger.debug(f"Token cached, expires in {expires_in}s")
    
    def get_token(self) -> Optional[str]:
        """Get token if still valid, otherwise None"""
        if self.token is None or self.expires_at is None:
            return None
        
        if time.time() >= self.expires_at:
            logger.debug("Token expired, will refresh")
            self.token = None
            self.expires_at = None
            return None
        
        return self.token


_token_cache = TokenCache()

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def parse_ups_date(ups_date_str: str) -> Optional[str]:
    """
    Convert UPS date format (YYYYMMDD) to ISO format (YYYY-MM-DD).
    Returns None if invalid.
    
    Args:
        ups_date_str: Date in format YYYYMMDD (e.g., "20210210")
    
    Returns:
        ISO format date string (e.g., "2021-02-10") or None
    """
    if not ups_date_str or len(ups_date_str) < 8:
        return None
    
    try:
        year = ups_date_str[0:4]
        month = ups_date_str[4:6]
        day = ups_date_str[6:8]
        
        # Validate ranges
        if not (1900 <= int(year) <= 2100 and 1 <= int(month) <= 12 and 1 <= int(day) <= 31):
            return None
        
        return f"{year}-{month}-{day}"
    except (ValueError, IndexError):
        return None


def parse_ups_time(ups_time_str: str) -> Optional[str]:
    """
    Convert UPS time format to HH:MM:SS.
    UPS can send HHMMSS or seconds since midnight.
    
    Args:
        ups_time_str: Time string (e.g., "123456" for 12:34:56 or seconds)
    
    Returns:
        ISO time string (e.g., "12:34:56") or None
    """
    if not ups_time_str:
        return None
    
    try:
        time_int = int(ups_time_str)
        
        # If > 86400 (seconds in a day), it's likely already in seconds format
        if time_int > 86400:
            return None
        
        # Assume HHMMSS format if 6 digits
        if len(ups_time_str) == 6:
            hours = ups_time_str[0:2]
            minutes = ups_time_str[2:4]
            seconds = ups_time_str[4:6]
            return f"{hours}:{minutes}:{seconds}"
        
        # If it's a smaller number, treat as seconds since midnight
        hours = time_int // 3600
        minutes = (time_int % 3600) // 60
        seconds = time_int % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    except (ValueError, IndexError):
        return None


def format_ups_datetime(date_str: str, time_str: Optional[str] = None) -> Optional[str]:
    """
    Combine UPS date and time into a readable ISO datetime format.
    
    Args:
        date_str: Date in YYYYMMDD format
        time_str: Time in HHMMSS format (optional)
    
    Returns:
        ISO datetime string or just date if time unavailable
    """
    parsed_date = parse_ups_date(date_str)
    if not parsed_date:
        return None
    
    if time_str:
        parsed_time = parse_ups_time(time_str)
        if parsed_time:
            return f"{parsed_date}T{parsed_time}Z"
    
    return parsed_date


def normalize_ups_status_code(code: Optional[str]) -> Optional[str]:
    """
    Normalize UPS status codes that are zero-padded numeric strings.
    Keeps alphanumeric codes intact.
    """
    if code is None:
        return None
    code_str = str(code)
    if code_str.isdigit():
        normalized = code_str.lstrip("0")
        return normalized if normalized else "0"
    return code_str


# ============================================================================

US_STATE_MAP = {
    "ALABAMA": "AL",
    "ALASKA": "AK",
    "ARIZONA": "AZ",
    "ARKANSAS": "AR",
    "CALIFORNIA": "CA",
    "COLORADO": "CO",
    "CONNECTICUT": "CT",
    "DELAWARE": "DE",
    "FLORIDA": "FL",
    "GEORGIA": "GA",
    "HAWAII": "HI",
    "IDAHO": "ID",
    "ILLINOIS": "IL",
    "INDIANA": "IN",
    "IOWA": "IA",
    "KANSAS": "KS",
    "KENTUCKY": "KY",
    "LOUISIANA": "LA",
    "MAINE": "ME",
    "MARYLAND": "MD",
    "MASSACHUSETTS": "MA",
    "MICHIGAN": "MI",
    "MINNESOTA": "MN",
    "MISSISSIPPI": "MS",
    "MISSOURI": "MO",
    "MONTANA": "MT",
    "NEBRASKA": "NE",
    "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH",
    "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM",
    "NEW YORK": "NY",
    "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND",
    "OHIO": "OH",
    "OKLAHOMA": "OK",
    "OREGON": "OR",
    "PENNSYLVANIA": "PA",
    "RHODE ISLAND": "RI",
    "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD",
    "TENNESSEE": "TN",
    "TEXAS": "TX",
    "UTAH": "UT",
    "VERMONT": "VT",
    "VIRGINIA": "VA",
    "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI",
    "WYOMING": "WY",
}

class AddressKeyFormat(BaseModel):
    """UPS Address format model"""
    ConsigneeName: Optional[str] = None
    AttentionName: Optional[str] = None
    AddressLine: Optional[List[str]] = None
    PoliticalDivision2: Optional[str] = None
    PoliticalDivision1: str
    PostcodePrimaryLow: Optional[str] = None
    PostcodeExtendedLow: Optional[str] = None
    Urbanization: Optional[str] = None
    CountryCode: str = "US"


class AddressValidationRequest(BaseModel):
    """Request model for UPS address validation"""
    firm: Optional[str] = None
    streetAddress: str
    secondaryAddress: Optional[str] = None
    city: Optional[str] = None
    state: str
    zipCode: Optional[str] = None
    zipPlus4: Optional[str] = None
    urbanization: Optional[str] = None
    countryCode: str = "US"
    
    def to_ups_format(self) -> Dict[str, Any]:
        """Convert to UPS XAVRequest format"""
        address_lines = [self.streetAddress]
        if self.secondaryAddress:
            address_lines.append(self.secondaryAddress)
        
        return {
            "XAVRequest": {
                "AddressKeyFormat": {
                    "ConsigneeName": self.firm,
                    "AddressLine": address_lines,
                    "PoliticalDivision2": self.city,
                    "PoliticalDivision1": self.state,
                    "PostcodePrimaryLow": self.zipCode,
                    "PostcodeExtendedLow": self.zipPlus4,
                    "Urbanization": self.urbanization if self.urbanization else None,
                    "CountryCode": self.countryCode
                }
            }
        }


class AddressValidationResponse(BaseModel):
    """Response model for validated address"""
    valid: bool
    address: Optional[Dict[str, Any]] = None
    candidates: Optional[List[Dict[str, Any]]] = None
    classification: Optional[Dict[str, str]] = None
    alerts: Optional[List[Dict[str, str]]] = None
    ambiguous: bool = False
    noCandidates: bool = False


class UPSService:
    """UPS Address Validation API integration with OAuth2 token caching and rate limiting"""
    
    def __init__(self):
        self.client_id = os.getenv("UPS_CLIENT_ID")
        self.client_secret = os.getenv("UPS_CLIENT_SECRET")
        self.account_number = os.getenv("UPS_ACCOUNT_NUMBER")
        
        # Environment-based URL selection (CIE vs Production)
        environment = os.getenv("UPS_ENVIRONMENT", "cie").lower()
        
        if environment == "cie":
            self.api_base_url = "https://wwwcie.ups.com/api/addressvalidation"
            self.token_url = "https://wwwcie.ups.com/security/v1/oauth/token"
        else:
            self.api_base_url = "https://onlinetools.ups.com/api/addressvalidation"
            self.token_url = "https://onlinetools.ups.com/security/v1/oauth/token"
        
        # Validate required credentials
        if not self.client_id or not self.client_secret:
            logger.warning(
                "UPS_CLIENT_ID or UPS_CLIENT_SECRET not set. "
                "Address validation will fail. Please configure these env vars."
            )
    
    async def _get_access_token(self) -> str:
        """Get OAuth2 access token with caching and automatic refresh"""
        
        # Check cache first
        cached_token = _token_cache.get_token()
        if cached_token:
            logger.debug("Using cached UPS token")
            return cached_token
        
        logger.debug("Fetching new UPS access token")
        
        try:
            if not self.client_id or not self.client_secret:
                raise RuntimeError("UPS client_id or client_secret is not configured")
            async with httpx.AsyncClient(timeout=10.0) as client:
                # UPS uses Basic Auth like USPS
                response = await client.post(
                    self.token_url,
                    auth=(self.client_id, self.client_secret),
                    data={"grant_type": "client_credentials"},
                    headers={
                        "x-merchant-id": self.account_number
                    } if self.account_number else {}
                )

                if response.status_code != 200:
                    error_text = response.text
                    logger.error(f"Token fetch failed: {response.status_code} {error_text}")
                    raise Exception(f"Failed to get UPS token: {error_text}")
                
                token_data = response.json()
                token = token_data.get("access_token")
                expires_in = int(token_data.get("expires_in", 3600))
                
                _token_cache.set_token(token, expires_in)
                return token
        
        except Exception as e:
            logger.error(f"Error fetching UPS token: {e}")
            raise
    
    async def validate_address(
        self, 
        request: AddressValidationRequest
    ) -> AddressValidationResponse:
        """
        Validate and standardize a UPS address
        
        Returns:
            AddressValidationResponse with validated address data or error info
        """
        
        if not self.client_id or not self.client_secret:
            logger.error("UPS API credentials not configured")
            return AddressValidationResponse(
                valid=False,
                ambiguous=False,
                noCandidates=True,
                alerts=[{
                    "code": "UNCONFIGURED",
                    "message": "UPS API credentials not configured"
                }]
            )
        
        try:
            token = await self._get_access_token()
        except Exception as e:
            logger.error(f"Failed to authenticate with UPS: {str(e)}")
            return AddressValidationResponse(
                valid=False,
                ambiguous=False,
                noCandidates=True,
                alerts=[{
                    "code": "AUTH_ERROR",
                    "message": f"Failed to authenticate with UPS: {str(e)}"
                }]
            )
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "x-merchant-id": self.account_number,
        }
        
        # Build UPS request format
        payload = request.to_ups_format()
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Use requestoption 3 for validation + classification
                response = await client.post(
                    f"{self.api_base_url}/v2/3",
                    json=payload,
                    headers=headers
                )
                
                # Handle rate limiting (429)
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "30")
                    logger.warning(f"UPS rate limit hit, retry after {retry_after}s")
                    return AddressValidationResponse(
                        valid=False,
                        ambiguous=False,
                        noCandidates=True,
                        alerts=[{
                            "code": "RATE_LIMITED",
                            "message": "Too many requests to UPS API"
                        }]
                    )
                
                # Handle other errors
                if response.status_code != 200:
                    try:
                        error_data = response.json()
                        error_message = error_data.get("response", {}).get("errors", [{}])[0].get("message", response.text)
                    except:
                        error_message = response.text
                    
                    logger.error(f"UPS API error {response.status_code}: {error_message}")
                    return AddressValidationResponse(
                        valid=False,
                        ambiguous=False,
                        noCandidates=True,
                        alerts=[{
                            "code": str(response.status_code),
                            "message": error_message
                        }]
                    )
                
                # Parse success response
                result = response.json()
                xav_response = result.get("XAVResponse", {})
                response_status = xav_response.get("Response", {}).get("ResponseStatus", {})
                
                # Check if validation was successful
                is_valid = response_status.get("Code") == "1"
                
                if not is_valid:
                    status_desc = response_status.get("Description", "Unknown error")
                    logger.warning(f"UPS address validation failed: {status_desc}")
                    return AddressValidationResponse(
                        valid=False,
                        ambiguous=False,
                        noCandidates=True,
                        alerts=[{
                            "code": response_status.get("Code", ""),
                            "message": status_desc
                        }]
                    )
                
                # Extract response indicators
                valid_address_indicator = xav_response.get("ValidAddressIndicator") == "Y"
                ambiguous_address_indicator = xav_response.get("AmbiguousAddressIndicator") == "Y"
                no_candidates_indicator = xav_response.get("NoCandidatesIndicator") == "Y"
                
                # Extract candidates
                candidates = []
                candidate_list = xav_response.get("Candidate", [])
                if not isinstance(candidate_list, list):
                    candidate_list = [candidate_list]
                
                for candidate in candidate_list:
                    addr_key = candidate.get("AddressKeyFormat", {})
                    candidates.append({
                        "firm": addr_key.get("ConsigneeName"),
                        "streetAddress": " ".join(addr_key.get("AddressLine", [])),
                        "city": addr_key.get("PoliticalDivision2"),
                        "state": addr_key.get("PoliticalDivision1"),
                        "zipCode": addr_key.get("PostcodePrimaryLow"),
                        "zipPlus4": addr_key.get("PostcodeExtendedLow"),
                        "classification": candidate.get("AddressClassification", {}).get("Description")
                    })
                
                # Extract classification
                classification = None
                addr_classification = xav_response.get("AddressClassification", {})
                if addr_classification:
                    classification = {
                        "code": addr_classification.get("Code"),
                        "description": addr_classification.get("Description")
                    }
                
                # Extract alerts
                alerts = []
                alert_list = xav_response.get("Alert", [])
                if not isinstance(alert_list, list):
                    alert_list = [alert_list] if alert_list else []
                
                for alert in alert_list:
                    alerts.append({
                        "code": alert.get("Code"),
                        "message": alert.get("Description")
                    })
                
                logger.info(f"UPS address validation: valid={valid_address_indicator}, ambiguous={ambiguous_address_indicator}, candidates={len(candidates)}")
                
                # Return primary candidate if exact match, otherwise return all candidates
                primary_address = None
                if candidates and valid_address_indicator and not ambiguous_address_indicator:
                    primary_address = candidates[0]
                
                return AddressValidationResponse(
                    valid=valid_address_indicator,
                    address=primary_address,
                    candidates=candidates if len(candidates) > 1 else None,
                    classification=classification,
                    alerts=alerts if alerts else None,
                    ambiguous=ambiguous_address_indicator,
                    noCandidates=no_candidates_indicator
                )
        
        except httpx.TimeoutException:
            logger.error("UPS API request timed out")
            return AddressValidationResponse(
                valid=False,
                ambiguous=False,
                noCandidates=True,
                alerts=[{
                    "code": "TIMEOUT",
                    "message": "UPS API request timed out"
                }]
            )
        except Exception as e:
            logger.error(f"Error validating address: {e}")
            return AddressValidationResponse(
                valid=False,
                ambiguous=False,
                noCandidates=True,
                alerts=[{
                    "code": "REQUEST_ERROR",
                    "message": str(e)
                }]
            )

    def normalize_state(self, state: str) -> str:
        if not state:
            raise ValueError("State is required")

        s = state.strip().upper()

        # Already valid
        if len(s) == 2:
            return s

        # Convert full name → code
        if s in US_STATE_MAP:
            return US_STATE_MAP[s]

        raise ValueError(f"Invalid UPS state code: {state!r}")
    
    async def create_label(
        self,
        from_name: str,
        from_street: str,
        from_city: str,
        from_state: str,
        from_zip: str,
        to_name: str,
        to_street: str,
        to_city: str,
        to_state: str,
        to_zip: str,
        weight_lbs: float,
        service_type: str = "03",  # UPS Ground = 03, Next Day = 01, 2nd Day = 02
        billing_option: str = "01",  # 01=BillShipper, 02=BillReceiver, 03=BillThirdParty, 04=ConsigneeBilled
        return_label: bool = False
    ) -> Dict[str, Any]:
        """
        Create a UPS shipping label.
        
        Args:
            from_name: Shipper name
            from_street: Shipper street address
            from_city: Shipper city
            from_state: Shipper state
            from_zip: Shipper ZIP code
            to_name: Recipient name
            to_street: Recipient street address
            to_city: Recipient city
            to_state: Recipient state
            to_zip: Recipient ZIP code
            weight_lbs: Package weight in pounds
            service_type: UPS service code (01=Next Day, 02=2nd Day, 03=Ground)
            return_label: Whether this is a return label
        
        Returns:
            Dict with label data (tracking number, label URL, etc.) or error info
        """
        
        if not self.client_id or not self.client_secret:
            logger.error("UPS API credentials not configured")
            return {
                "error": True,
                "code": "UNCONFIGURED",
                "message": "UPS API credentials not configured"
            }
        
        try:
            token = await self._get_access_token()
        except Exception as e:
            logger.error(f"Failed to authenticate with UPS: {str(e)}")
            return {
                "error": True,
                "code": "AUTH_ERROR",
                "message": f"Failed to authenticate with UPS: {str(e)}"
            }
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "x-merchant-id": self.account_number,
        }
        
        # Build UPS Shipping API request
        # Build billing information based on billing option
        shipment_charge: Dict[str, Any] = {
            "Type": "01"  # Transportation charges
        }
        
        if billing_option == "02":
            # Bill to Receiver
            shipment_charge["BillReceiver"] = {
                "AccountNumber": self.account_number
            }
        elif billing_option == "03":
            # Bill to Third Party
            shipment_charge["BillThirdParty"] = {
                "AccountNumber": self.account_number,
                "Address": {
                    "CountryCode": "US"
                }
            }
        elif billing_option == "04":
            # Consignee Billed
            shipment_charge["ConsigneeBilledIndicator"] = ""
        else:  # Default to "01" - Bill to Shipper
            shipment_charge["BillShipper"] = {
                "AccountNumber": self.account_number
            }
        
        payload = {
            "ShipmentRequest": {
                "Shipment": {
                    "Shipper": {
                        "Name": from_name,
                        "ShipperNumber": self.account_number,
                        "Address": {
                            "AddressLine": [from_street],  # ✅ array
                            "City": from_city,
                            "StateProvinceCode": self.normalize_state(from_state),
                            "PostalCode": from_zip,
                            "CountryCode": "US"
                        }
                    },
                    "ShipTo": {
                        "Name": to_name,
                        "Address": {
                            "AddressLine": [to_street],  # ✅ array
                            "City": to_city,
                            "StateProvinceCode": self.normalize_state(to_state),
                            "PostalCode": to_zip,
                            "CountryCode": "US"
                        }
                    },
                    "PaymentInformation": {
                        "ShipmentCharge": [shipment_charge]
                    },
                    "ShipmentServiceOptions": {
                        "LabelDelivery": {
                            "LabelDeliveryMethod": "03"  # Return label as PNG
                        }
                    },
                    "Package": [
                        {
                            # UPS Shipping API expects "Packaging" (not "PackagingType").
                            "Packaging": {
                                "Code": "02"
                            },
                            "Dimensions": {
                                "UnitOfMeasurement": {
                                    "Code": "IN"
                                },
                                "Length": "12",
                                "Width": "8",
                                "Height": "6"
                            },
                            "PackageWeight": {
                                "UnitOfMeasurement": {
                                    "Code": "LBS"
                                },
                                "Weight": str(weight_lbs)
                            },
                            "Description": "3D Printed Item"
                        }
                    ],
                    "Service": {
                        "Code": service_type
                    }
                },
                "LabelSpecification": {
                    "LabelImageFormat": {
                        "Code": "PNG"
                    }
                }
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Construct the shipments endpoint - replace addressvalidation with shipments
                base_url = self.api_base_url.replace('/addressvalidation', '/shipments/v2409')
                endpoint = f"{base_url}/ship"
                
                # Log the exact payload being sent
                logger.debug(f"UPS Shipment Payload: {payload}")
                
                response = await client.post(
                    endpoint,
                    json=payload,
                    headers=headers
                )
                
                if response.status_code not in [200, 201]:
                    error_text = response.text
                    logger.error(f"Label creation failed: {response.status_code} {error_text}")
                    
                    error_message = error_text
                    try:
                        error_data = response.json()
                        if isinstance(error_data, dict):
                            # Try different error response structures
                            if "response" in error_data and isinstance(error_data.get("response"), dict):
                                errors = error_data["response"].get("errors", [])
                                if errors and isinstance(errors, list) and len(errors) > 0:
                                    error_message = errors[0].get("message", error_text) if isinstance(errors[0], dict) else str(errors[0])
                            elif "message" in error_data:
                                error_message = error_data["message"]
                            elif "error" in error_data:
                                error_message = error_data["error"]
                    except Exception as e:
                        logger.debug(f"Could not parse error response as JSON: {e}")
                        error_message = error_text
                    
                    return {
                        "error": True,
                        "code": str(response.status_code),
                        "message": error_message
                    }
                
                # Parse success response
                try:
                    result = response.json()
                except Exception as e:
                    logger.error(f"Failed to parse UPS response as JSON: {e}")
                    return {
                        "error": True,
                        "code": "PARSE_ERROR",
                        "message": f"Failed to parse UPS response: {str(e)}"
                    }
                
                if not isinstance(result, dict):
                    logger.error(f"UPS response is not a dict, got: {type(result)}")
                    return {
                        "error": True,
                        "code": "INVALID_RESPONSE",
                        "message": "UPS API returned invalid response format"
                    }
                
                shipment_response = result.get("ShipmentResponse", {})
                
                # DEBUG: Log full response structure
                logger.debug(f"Full UPS ShipmentResponse: {shipment_response}")
                
                # Extract tracking number and label
                tracking_number = None
                label_image = None
                label_image_format = None
                label_url = None
                
                # Validate shipment_response is a dict
                if not isinstance(shipment_response, dict):
                    logger.error(f"ShipmentResponse is not a dict: {type(shipment_response)}")
                    return {
                        "error": True,
                        "code": "INVALID_RESPONSE",
                        "message": "UPS API returned invalid shipment response format"
                    }
                
                # Try to get tracking number from response
                shipments = shipment_response.get("ShipmentResults", [])
                if not isinstance(shipments, list):
                    shipments = [shipments] if shipments else []
                
                if shipments and isinstance(shipments[0], dict):
                    logger.debug(f"ShipmentResults[0]: {shipments[0]}")
                    tracking_number = shipments[0].get("TrackingNumber")
                    
                    # If not in ShipmentResults, try PackageResults
                    if not tracking_number:
                        package_results = shipments[0].get("PackageResults", [])
                        if not isinstance(package_results, list):
                            package_results = [package_results] if package_results else []
                        
                        if package_results and isinstance(package_results[0], dict):
                            logger.debug(f"PackageResults[0]: {package_results[0]}")
                            tracking_number = package_results[0].get("TrackingNumber")
                            shipping_label = package_results[0].get("ShippingLabel", {})
                            label_image = shipping_label.get("GraphicImage")
                            label_image_format = shipping_label.get("ImageFormat", {}).get("Code")
                    else:
                        # Extract label image data
                        package_results = shipments[0].get("PackageResults", [])
                        if not isinstance(package_results, list):
                            package_results = [package_results] if package_results else []
                        
                        if package_results and isinstance(package_results[0], dict):
                            shipping_label = package_results[0].get("ShippingLabel", {})
                            label_image = shipping_label.get("GraphicImage")
                            label_image_format = shipping_label.get("ImageFormat", {}).get("Code")
                
                logger.info(f"UPS label created successfully: tracking={tracking_number}")
                
                return {
                    "error": False,
                    "tracking_number": tracking_number,
                    "label_image": label_image,
                    "label_image_format": label_image_format,
                    "shipment_id": shipment_response.get("ShipmentIdentificationNumber")
                }
        
        except httpx.TimeoutException:
            logger.error("UPS API request timed out")
            return {
                "error": True,
                "code": "TIMEOUT",
                "message": "UPS API request timed out"
            }
        except Exception as e:
            logger.error(f"Error creating label: {e}")
            return {
                "error": True,
                "code": "REQUEST_ERROR",
                "message": str(e)
            }
    
    async def track_shipment(self, tracking_number: str) -> Dict[str, Any]:
        """
        Track a UPS shipment using the Track API.
        
        Args:
            tracking_number: The UPS tracking number (1Z format)
        
        Returns:
            Dict with tracking data or error info
        """
        
        if not self.client_id or not self.client_secret:
            logger.error("UPS API credentials not configured")
            return {
                "error": True,
                "code": "UNCONFIGURED",
                "message": "UPS API credentials not configured"
            }
        
        if not tracking_number:
            logger.error("Tracking number is required")
            return {
                "error": True,
                "code": "INVALID_INPUT",
                "message": "Tracking number is required"
            }
        
        try:
            token = await self._get_access_token()
        except Exception as e:
            logger.error(f"Failed to authenticate with UPS: {str(e)}")
            return {
                "error": True,
                "code": "AUTH_ERROR",
                "message": f"Failed to authenticate with UPS: {str(e)}"
            }
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "x-merchant-id": self.account_number or "",
            "transId": f"track-{tracking_number[:10]}",
            "transactionSrc": "ShippingDashboard"
        }
        
        try:
            # Construct track API endpoint based on environment
            environment = os.getenv("UPS_ENVIRONMENT", "cie").lower()
            if environment == "cie":
                track_api_url = f"https://wwwcie.ups.com/api/track/v1/details/{tracking_number}"
            else:
                track_api_url = f"https://onlinetools.ups.com/api/track/v1/details/{tracking_number}"
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    track_api_url,
                    headers=headers,
                    params={
                        "locale": "en_US",
                        "returnSignature": "false",
                        "returnMilestones": "true",
                        "returnPOD": "false"
                    }
                )
                
                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "30")
                    logger.warning(f"UPS track API rate limit hit, retry after {retry_after}s")
                    return {
                        "error": True,
                        "code": "RATE_LIMITED",
                        "message": "Too many requests to UPS API, please try again later",
                        "retryAfter": retry_after
                    }
                
                # Handle other errors
                if response.status_code != 200:
                    try:
                        error_data = response.json()
                        errors = error_data.get("errors", [{}])
                        error_message = errors[0].get("message", response.text) if errors else response.text
                    except:
                        error_message = response.text
                    
                    logger.error(f"UPS track API error {response.status_code}: {error_message}")
                    
                    # Check if it's a 404 (tracking number not found)
                    if response.status_code == 404:
                        return {
                            "error": True,
                            "code": "NOT_FOUND",
                            "message": f"Tracking number {tracking_number} not found"
                        }
                    
                    return {
                        "error": True,
                        "code": str(response.status_code),
                        "message": error_message
                    }
                
                # Parse successful tracking response
                result = response.json()
                logger.debug(f"Full tracking response: {json.dumps(result, indent=2, default=str)}")
                
                track_response = result.get("trackResponse", {})
                shipments = track_response.get("shipment", [])
                
                if not shipments:
                    return {
                        "error": True,
                        "code": "NO_DATA",
                        "message": f"No tracking data found for {tracking_number}"
                    }
                
                # Extract first shipment
                shipment = shipments[0] if isinstance(shipments, list) else shipments
                
                # Extract key tracking info
                inquiry_number = shipment.get("inquiryNumber")
                status_code = None
                status_description = None
                delivery_date = None
                current_location = None
                activities = []
                
                # Get package info (tracking data is at package level)
                packages = shipment.get("package", [])
                if packages:
                    package = packages[0] if isinstance(packages, list) else packages
                    
                    # Get current status from package.currentStatus (not from activities)
                    current_status = package.get("currentStatus", {})
                    status_code = normalize_ups_status_code(current_status.get("code"))
                    status_description = current_status.get("description") or current_status.get("simplifiedTextDescription")
                    
                    # Get package-level delivery date
                    delivery_dates = package.get("deliveryDate", [])
                    if delivery_dates:
                        raw_date = delivery_dates[0].get("date") if isinstance(delivery_dates, list) else delivery_dates.get("date")
                        delivery_date = parse_ups_date(raw_date) if raw_date else None
                    
                    # Get delivery information (includes delivery location)
                    delivery_info = package.get("deliveryInformation", {})
                    if delivery_info:
                        delivery_location = delivery_info.get("location", {})
                        if delivery_location:
                            delivery_address = delivery_location.get("address", {})
                            current_location = {
                                "city": delivery_address.get("city"),
                                "state": delivery_address.get("stateProvince"),
                                "zip": delivery_address.get("postalCode"),
                                "country": delivery_address.get("countryCode"),
                            }
                    
                    # Get activity history (most recent first)
                    activity_list = package.get("activity", [])
                    if activity_list and not isinstance(activity_list, list):
                        activity_list = [activity_list]
                    
                    if activity_list and not current_location:
                        # If no delivery location, try to get from most recent activity
                        latest_activity = activity_list[0] if isinstance(activity_list, list) else activity_list
                        activity_location = latest_activity.get("location", {})
                        current_location = {
                            "city": activity_location.get("address", {}).get("city"),
                            "state": activity_location.get("address", {}).get("stateProvince"),
                            "zip": activity_location.get("address", {}).get("postalCode"),
                            "country": activity_location.get("address", {}).get("countryCode"),
                        }
                    
                    # Build activity list (limit to last 10)
                    for activity in activity_list[:10]:
                        activity_time = activity.get("gmtTime") or activity.get("time")
                        activity_date = activity.get("gmtDate") or activity.get("date")
                        
                        # Format date/time properly
                        formatted_datetime = format_ups_datetime(activity_date, activity_time) if activity_date else None
                        
                        activities.append({
                            "date": formatted_datetime,  # ISO format datetime
                            "status": activity.get("status", {}).get("description", "Unknown"),
                            "statusCode": normalize_ups_status_code(activity.get("status", {}).get("code")),
                            "location": {
                                "city": activity.get("location", {}).get("address", {}).get("city"),
                                "state": activity.get("location", {}).get("address", {}).get("stateProvince"),
                                "zip": activity.get("location", {}).get("address", {}).get("postalCode"),
                            }
                        })
                
                logger.info(f"UPS tracking retrieved for {tracking_number}: status={status_code}")
                
                return {
                    "error": False,
                    "trackingNumber": inquiry_number or tracking_number,
                    "statusCode": status_code,
                    "statusDescription": status_description,
                    "currentLocation": current_location,
                    "deliveryDate": delivery_date,
                    "activities": activities,
                    "shipmentData": {
                        "shipper": shipment.get("shipperInformation", {}),
                        "recipient": shipment.get("shipToInformation", {}),
                        "service": shipment.get("service", {}).get("description")
                    }
                }
        
        except httpx.TimeoutException:
            logger.error("UPS track API request timed out")
            return {
                "error": True,
                "code": "TIMEOUT",
                "message": "UPS track API request timed out"
            }
        except Exception as e:
            logger.error(f"Error tracking shipment: {e}")
            return {
                "error": True,
                "code": "REQUEST_ERROR",
                "message": str(e)
            }
    
    async def get_shipping_rates(
        self,
        from_zip: str,
        from_city: str,
        from_state: str,
        to_zip: str,
        to_city: str,
        to_state: str,
        weight_lbs: float,
        length_in: float = 5,
        width_in: float = 5,
        height_in: float = 5,
        get_all_services: bool = True
    ) -> Dict[str, Any]:
        """
        Get UPS shipping rates for a shipment using the Rating API.
        
        Args:
            from_zip: Shipper ZIP code
            from_city: Shipper city
            from_state: Shipper state (2-letter code)
            to_zip: Recipient ZIP code
            to_city: Recipient city
            to_state: Recipient state (2-letter code)
            weight_lbs: Package weight in pounds
            length_in: Package length in inches
            width_in: Package width in inches
            height_in: Package height in inches
            get_all_services: If True, use Shop mode to get all services; if False, get Ground only
        
        Returns:
            Dict with available UPS services and rates, or error info
        """
        
        if not self.client_id or not self.client_secret:
            logger.error("UPS API credentials not configured")
            return {
                "error": True,
                "code": "UNCONFIGURED",
                "message": "UPS API credentials not configured",
                "rates": []
            }
        
        try:
            token = await self._get_access_token()
        except Exception as e:
            logger.error(f"Failed to authenticate with UPS: {str(e)}")
            return {
                "error": True,
                "code": "AUTH_ERROR",
                "message": f"Failed to authenticate with UPS: {str(e)}",
                "rates": []
            }
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "x-merchant-id": self.account_number,
        }
        
        # Build Rating API request
        # Use 'Shop' to get all services, or 'Rate' for specific service
        request_option = "Shop" if get_all_services else "Rate"
        
        payload = {
            "RateRequest": {
                "Request": {
                    "SubVersion": "2409",
                    "RequestOption": request_option,
                    "TransactionReference": {
                        "CustomerContext": "Rating Request"
                    }
                },
                "Shipment": {
                    "Shipper": {
                        "Name": "Shipper",
                        "ShipperNumber": self.account_number,
                        "Address": {
                            "AddressLine": ["Shipper Address"],
                            "City": from_city,
                            "StateProvinceCode": self.normalize_state(from_state),
                            "PostalCode": from_zip,
                            "CountryCode": "US"
                        }
                    },
                    "ShipTo": {
                        "Name": "Recipient",
                        "Address": {
                            "AddressLine": ["Recipient Address"],
                            "City": to_city,
                            "StateProvinceCode": self.normalize_state(to_state),
                            "PostalCode": to_zip,
                            "CountryCode": "US"
                        }
                    },
                    "ShipFrom": {
                        "Name": "Shipper",
                        "Address": {
                            "AddressLine": ["Shipper Address"],
                            "City": from_city,
                            "StateProvinceCode": self.normalize_state(from_state),
                            "PostalCode": from_zip,
                            "CountryCode": "US"
                        }
                    },
                    "PaymentDetails": {
                        "ShipmentCharge": [
                            {
                                "Type": "01",
                                "BillShipper": {
                                    "AccountNumber": self.account_number
                                }
                            }
                        ]
                    },
                    "Package": [
                        {
                            "PackagingType": {
                                "Code": "02"  # Package
                            },
                            "Dimensions": {
                                "UnitOfMeasurement": {
                                    "Code": "IN"
                                },
                                "Length": str(length_in),
                                "Width": str(width_in),
                                "Height": str(height_in)
                            },
                            "PackageWeight": {
                                "UnitOfMeasurement": {
                                    "Code": "LBS"
                                },
                                "Weight": str(weight_lbs)
                            },
                            "NumOfPieces": "1"
                        }
                    ]
                }
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Determine environment URL
                environment = os.getenv("UPS_ENVIRONMENT", "cie").lower()
                if environment == "cie":
                    rating_url = "https://wwwcie.ups.com/api/rating/v2409/Shop"
                else:
                    rating_url = "https://onlinetools.ups.com/api/rating/v2409/Shop"
                
                response = await client.post(
                    rating_url,
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 429:
                    logger.warning("UPS rate limit hit, retrying...")
                    return {
                        "error": True,
                        "code": "RATE_LIMIT",
                        "message": "UPS API rate limit exceeded. Please try again later.",
                        "rates": []
                    }
                
                if response.status_code != 200:
                    error_text = response.text
                    logger.error(f"UPS Rating API error: {response.status_code} {error_text}")
                    return {
                        "error": True,
                        "code": "API_ERROR",
                        "message": f"UPS API error: {response.status_code}",
                        "rates": []
                    }
                
                response_data = response.json()
                
                # Extract rates from response
                rates = []
                rate_response = response_data.get("RateResponse", {})
                
                # Check if response was successful
                response_status = rate_response.get("Response", {}).get("ResponseStatus", {})
                if response_status.get("Code") != "1":
                    error_code = response_status.get("Code", "UNKNOWN")
                    error_desc = response_status.get("Description", "Unknown error")
                    logger.error(f"UPS Rating API failed: {error_code} - {error_desc}")
                    return {
                        "error": True,
                        "code": error_code,
                        "message": error_desc,
                        "rates": []
                    }
                
                # Process rated shipments
                rated_shipments = rate_response.get("RatedShipment", [])
                if not isinstance(rated_shipments, list):
                    rated_shipments = [rated_shipments]
                
                for shipment in rated_shipments:
                    service = shipment.get("Service", {})
                    service_code = service.get("Code", "")
                    service_desc = service.get("Description", "Unknown Service")
                    
                    # Get transportation charges
                    transport_charges = shipment.get("TransportationCharges", {})
                    cost = transport_charges.get("MonetaryValue", "0.00")
                    currency = transport_charges.get("CurrencyCode", "USD")
                    
                    # Get transit time if available
                    time_in_transit = shipment.get("TimeInTransit", {})
                    transit_days = None
                    if time_in_transit:
                        # Try to extract business days
                        transit_info = time_in_transit.get("ServiceSummary", {})
                        transit_days = transit_info.get("EstimatedArrival", {}).get("BusinessDaysInTransit")
                    
                    rates.append({
                        "serviceCode": service_code,
                        "serviceName": service_desc,
                        "cost": float(cost),
                        "currency": currency,
                        "estimatedDays": transit_days,
                        "displayCost": f"${float(cost):.2f}"
                    })
                
                logger.info(f"Retrieved {len(rates)} UPS rate options")
                
                return {
                    "error": False,
                    "rates": sorted(rates, key=lambda x: x["cost"]),  # Sort by price
                    "weight": weight_lbs,
                    "origin": f"{from_city}, {from_state} {from_zip}",
                    "destination": f"{to_city}, {to_state} {to_zip}"
                }
        
        except httpx.TimeoutException:
            logger.error("UPS Rating API request timed out")
            return {
                "error": True,
                "code": "TIMEOUT",
                "message": "UPS API request timed out",
                "rates": []
            }
        except Exception as e:
            logger.error(f"Error getting shipping rates: {e}")
            return {
                "error": True,
                "code": "REQUEST_ERROR",
                "message": str(e),
                "rates": []
            }


# Single instance
ups_service = UPSService()
