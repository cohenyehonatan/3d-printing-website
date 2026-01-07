"""
USPS Addresses API Integration Service
Handles OAuth2 token management, address validation, and rate limit handling
"""

import os
import time
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
# USPS SERVICE
# ============================================================================

class AddressValidationRequest(BaseModel):
    """Request model for address validation"""
    firm: Optional[str] = None
    streetAddress: str
    secondaryAddress: Optional[str] = None
    city: Optional[str] = None
    state: str
    urbanization: Optional[str] = None
    ZIPCode: Optional[str] = None
    ZIPPlus4: Optional[str] = None


class AddressValidationResponse(BaseModel):
    """Response model for validated address"""
    firm: Optional[str] = None
    address: Dict[str, Any]
    additionalInfo: Optional[Dict[str, Any]] = None
    corrections: Optional[List[Dict[str, str]]] = None
    matches: Optional[List[Dict[str, str]]] = None
    warnings: Optional[List[str]] = None


class USPSService:
    """USPS Addresses API integration with OAuth2 token caching and rate limiting"""
    
    def __init__(self):
        self.client_id = os.getenv("USPS_CLIENT_ID")
        self.client_secret = os.getenv("USPS_CLIENT_SECRET")
        self.api_base_url = os.getenv("USPS_API_BASE_URL", "https://apis.usps.com/addresses/v3")
        self.token_url = os.getenv("USPS_TOKEN_URL", "https://apis.usps.com/oauth2/v3/token")
        
        # Validate required credentials
        if not self.client_id or not self.client_secret:
            logger.warning(
                "USPS_CLIENT_ID or USPS_CLIENT_SECRET not set. "
                "Address validation will fail. Please configure these env vars."
            )
    
    async def _get_access_token(self) -> str:
        """Get OAuth2 access token with caching and automatic refresh"""
        
        # Check cache first
        cached_token = _token_cache.get_token()
        if cached_token:
            logger.debug("Using cached USPS token")
            return cached_token
        
        logger.debug("Fetching new USPS access token")
        
        try:
            if not self.client_id or not self.client_secret:
                raise Exception("USPS API credentials are not configured")
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.token_url,
                    auth=(self.client_id, self.client_secret),
                    data={
                        "grant_type": "client_credentials",
                        "scope": "addresses"
                    }
                )
                
                if response.status_code != 200:
                    logger.error(f"Token fetch failed: {response.status_code} {response.text}")
                    raise Exception(f"Failed to get USPS token: {response.text}")
                
                token_data = response.json()
                token = token_data.get("access_token")
                expires_in = token_data.get("expires_in", 3600)
                
                _token_cache.set_token(token, expires_in)
                return token
        
        except Exception as e:
            logger.error(f"Error fetching USPS token: {e}")
            raise
    
    async def validate_address(
        self, 
        request: AddressValidationRequest
    ) -> Dict[str, Any]:
        """
        Validate and standardize a USPS address
        
        Returns:
            Dict with validated address data or error info
        """
        
        if not self.client_id or not self.client_secret:
            return {
                "error": True,
                "message": "USPS API credentials not configured",
                "code": "UNCONFIGURED"
            }
        
        try:
            token = await self._get_access_token()
        except Exception as e:
            return {
                "error": True,
                "message": f"Failed to authenticate with USPS: {str(e)}",
                "code": "AUTH_ERROR"
            }
        
        # Build query parameters
        params = {
            "streetAddress": request.streetAddress,
            "state": request.state,
        }
        
        if request.firm:
            params["firm"] = request.firm
        if request.secondaryAddress:
            params["secondaryAddress"] = request.secondaryAddress
        if request.city:
            params["city"] = request.city
        if request.urbanization:
            params["urbanization"] = request.urbanization
        if request.ZIPCode:
            params["ZIPCode"] = request.ZIPCode
        if request.ZIPPlus4:
            params["ZIPPlus4"] = request.ZIPPlus4
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.api_base_url}/address",
                    params=params,
                    headers=headers
                )
                
                # Handle rate limiting (429)
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "30")
                    logger.warning(f"USPS rate limit hit, retry after {retry_after}s")
                    return {
                        "error": True,
                        "code": "RATE_LIMITED",
                        "message": "Too many requests to USPS API",
                        "retry_after_seconds": int(retry_after)
                    }
                
                # Handle other errors
                if response.status_code != 200:
                    error_data = response.json() if response.headers.get("content-type") == "application/json" else {}
                    error_message = error_data.get("error", {}).get("message", response.text)
                    
                    return {
                        "error": True,
                        "code": str(response.status_code),
                        "message": error_message,
                        "details": error_data
                    }
                
                # Success
                result = response.json()
                
                # Check for address corrections/matches
                corrections = result.get("corrections", [])
                matches = result.get("matches", [])
                
                # Log the response codes for debugging
                if corrections:
                    correction_codes = [c.get("code") for c in corrections]
                    logger.info(f"Address corrections found: {correction_codes}")
                
                if matches:
                    match_codes = [m.get("code") for m in matches]
                    logger.info(f"Address matches found: {match_codes}")
                
                return {
                    "error": False,
                    "data": result
                }
        
        except httpx.TimeoutException:
            logger.error("USPS API request timed out")
            return {
                "error": True,
                "code": "TIMEOUT",
                "message": "USPS API request timed out"
            }
        except Exception as e:
            logger.error(f"Error validating address: {e}")
            return {
                "error": True,
                "code": "REQUEST_ERROR",
                "message": str(e)
            }


# Single instance
usps_service = USPSService()
