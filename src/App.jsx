import React, { useState, useEffect } from 'react';
import { Upload, Package, DollarSign, Settings, CheckCircle } from 'lucide-react';
import STLParser from './STLParser';
import PaymentSuccess from './PaymentSuccess';
import ShippingDashboard from './ShippingDashboard';
import GlobalHeader from './GlobalHeader';
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import { apiFetch } from './api.js';


const QuoteForm = ({ /* pass your existing props */ }) => {
  const [step, setStep] = useState(1);
  const [showPaymentSuccess, setShowPaymentSuccess] = useState(false);
  const [paymentParams, setPaymentParams] = useState({});
  const [modelFile, setModelFile] = useState(null);
  const [modelStats, setModelStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selections, setSelections] = useState({
    // Contact info
    email: '',
    name: '',
    phone: '',
    // Delivery address (for Click-N-Ship)
    first_name: '',
    middle_initial: '',
    last_name: '',
    company: '',
    street_address: '',
    apt_suite: '',
    city: '',
    state: '',
    zip_code: '',
    country: 'United States of America',
    // Order details
    material: '',
    quantity: 1,
    rush_order: false,
    // Packaging
    packaging_type: '',
    contains_hazmat: false,
    contains_live_animals: false,
    contains_perishable: false,
    contains_cremated_remains: false
  });
  const [quote, setQuote] = useState(null);
  const [showDashboard, setShowDashboard] = useState(false);
  const [shippingRates, setShippingRates] = useState([]);
  const [selectedShippingService, setSelectedShippingService] = useState(null);
  const [loadingRates, setLoadingRates] = useState(false);

  // Check URL on mount for payment success redirect
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.has('payment-success') || params.has('order_id')) {
      setPaymentParams({
        order_id: params.get('order_id'),
        customer_id: params.get('customer_id')
      });
      setShowPaymentSuccess(true);
    }
  }, []);

  // Auto-fill city and state when ZIP code is entered
  useEffect(() => {
    const prefillZipData = async () => {
      if (selections.zip_code && selections.zip_code.length === 5) {
        try {
          const response = await apiFetch(`/api/lookup/zip-location/${selections.zip_code}`);
          if (response.ok) {
            const data = await response.json();
            setSelections(prev => ({
              ...prev,
              city: data.city,
              state: data.state
            }));
          }
        } catch (err) {
          console.log(`Could not auto-fill for ZIP code ${selections.zip_code}:`, err.message);
        }
      }
    };

    prefillZipData();
  }, [selections.zip_code]);

  const materials = [
    { id: 'PLA Basic', name: 'PLA Basic', pricePerKg: 19.99, density: 1.24, description: 'Standard, eco-friendly' },
    { id: 'PETG Basic', name: 'PETG Basic', pricePerKg: 19.99, density: 1.27, description: 'Durable, heat-resistant' },
    { id: 'PLA Matte', name: 'PLA Matte', pricePerKg: 19.99, density: 1.24, description: 'Matte finish PLA' },
    { id: 'PETG HF', name: 'PETG HF', pricePerKg: 19.99, density: 1.27, description: 'High flow PETG' }
  ];

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    setLoading(true);
    setError(null);
    
    try {
      setModelFile(file);
      
      // Parse STL on client side
      const stats = await STLParser.parse(file);
      setModelStats(stats);
      
      // Skip server verification for now - client-side parsing is sufficient
      // for estimates. Server validates during quote calculation if needed.
      
      setStep(2);
    } catch (err) {
      setError(`Failed to parse model: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const calculatePrice = async () => {
    if (!modelStats || !selections.material || !selections.zip_code) {
      alert('Please complete all required fields');
      return;
    }

    setLoading(true);
    setError(null);
    
    try {
      const material = materials.find(m => m.id === selections.material);
      const weight = modelStats.weight || (modelStats.volume * material.density);
      
      const response = await apiFetch('/api/quote', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          zip_code: selections.zip_code,
          filament_type: selections.material,
          quantity: selections.quantity,
          rush_order: selections.rush_order,
          volume: modelStats.volume,
          weight: weight,
          use_usps_connect_local: false
        })
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.error || 'Failed to get quote');
      }

      const quoteData = await response.json();
      setQuote(quoteData);
      
      // Fetch shipping rates for the destination
      await fetchShippingRates(weight);
      
      setStep(3);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchShippingRates = async (weight) => {
    try {
      setLoadingRates(true);
      const weightInLbs = (weight * 2.20462) || 0.5; // Convert grams to pounds
      
      const response = await apiFetch('/api/shipping-rates', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          zip_code: selections.zip_code,
          weight: weightInLbs,
          length: 5,
          width: 5,
          height: 5,
          rush_order: selections.rush_order
        })
      });

      if (!response.ok) {
        console.warn('Failed to fetch shipping rates');
        return;
      }

      const ratesData = await response.json();
      if (!ratesData.error && ratesData.rates && ratesData.rates.length > 0) {
        setShippingRates(ratesData.rates);
        // Auto-select the first (cheapest) option
        setSelectedShippingService(ratesData.rates[0]);
      } else {
        console.warn('No shipping rates available');
      }
    } catch (err) {
      console.warn('Error fetching shipping rates:', err.message);
      // Don't fail the quote if rates fail - continue with default
    } finally {
      setLoadingRates(false);
    }
  };

  const proceedToCheckout = async () => {
    if (!selections.email || !selections.name) {
      alert('Please enter your email and name to proceed');
      return;
    }
    
    if (!selections.street_address || !selections.city || !selections.state || !selections.zip_code) {
      alert('Please enter complete shipping address');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const material = materials.find(m => m.id === selections.material);
      const weight = modelStats.weight || (modelStats.volume * material.density);

      const checkoutData = {
        // Contact info
        email: selections.email,
        name: selections.name,
        phone: selections.phone || '',
        // Delivery address
        first_name: selections.first_name || selections.name.split(' ')[0],
        middle_initial: selections.middle_initial || '',
        last_name: selections.last_name || selections.name.split(' ').slice(1).join(' '),
        company: selections.company || '',
        street_address: selections.street_address,
        apt_suite: selections.apt_suite || '',
        city: selections.city,
        state: selections.state,
        zip_code: selections.zip_code,
        country: selections.country,
        // Order details
        filament_type: selections.material,
        quantity: selections.quantity,
        rush_order: selections.rush_order,
        volume: modelStats.volume,
        weight: weight,
        use_usps_connect_local: false,
        // Shipping service selection with cost
        shipping_service_code: selectedShippingService?.serviceCode || '03',
        shipping_service_name: selectedShippingService?.serviceName || 'UPS Ground',
        shipping_cost: selectedShippingService?.cost || 0  // UPS shipping cost in dollars
      };

      const response = await apiFetch('/api/checkout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(checkoutData)
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to create checkout');
      }

      const finalCheckoutData = await response.json();
      
      // Redirect to Stripe payment link
      window.location.href = finalCheckoutData.payment_url;
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {showPaymentSuccess ? (
        <PaymentSuccess orderId={paymentParams.order_id} customerId={paymentParams.customer_id} />
      ) : (
        <>
          <GlobalHeader />
          <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      {/* Progress Bar */}
      <div className="max-w-7xl mx-auto px-4 py-6 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center space-x-2">
            <div className={`w-10 h-10 rounded-full flex items-center justify-center ${step >= 1 ? 'bg-indigo-600 text-white' : 'bg-gray-300'}`}>
              1
            </div>
            <span className="text-sm font-medium">Upload Model</span>
          </div>
          <div className="flex-1 h-1 mx-4 bg-gray-300">
            <div className={`h-full ${step >= 2 ? 'bg-indigo-600' : ''} transition-all`} style={{width: step >= 2 ? '100%' : '0%'}}></div>
          </div>
          <div className="flex items-center space-x-2">
            <div className={`w-10 h-10 rounded-full flex items-center justify-center ${step >= 2 ? 'bg-indigo-600 text-white' : 'bg-gray-300'}`}>
              2
            </div>
            <span className="text-sm font-medium">Configure</span>
          </div>
          <div className="flex-1 h-1 mx-4 bg-gray-300">
            <div className={`h-full ${step >= 3 ? 'bg-indigo-600' : ''} transition-all`} style={{width: step >= 3 ? '100%' : '0%'}}></div>
          </div>
          <div className="flex items-center space-x-2">
            <div className={`w-10 h-10 rounded-full flex items-center justify-center ${step >= 3 ? 'bg-indigo-600 text-white' : 'bg-gray-300'}`}>
              3
            </div>
            <span className="text-sm font-medium">Review & Order</span>
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-6">
            {error}
          </div>
        )}

        {/* Step 1: Upload */}
        {step === 1 && (
          <div className="bg-white rounded-lg shadow-lg p-8 max-w-2xl mx-auto">
            <div className="text-center">
              <Upload className="w-16 h-16 text-indigo-600 mx-auto mb-4" />
              <h2 className="text-2xl font-bold mb-2">Upload Your 3D Model</h2>
              <p className="text-gray-600 mb-6">We accept STL files up to 100MB</p>
              
              <label className="block">
                <input
                  type="file"
                  accept=".stl"
                  onChange={handleFileUpload}
                  disabled={loading}
                  className="hidden"
                />
                <div className="border-2 border-dashed border-indigo-300 rounded-lg p-12 cursor-pointer hover:border-indigo-500 hover:bg-indigo-50 transition">
                  <div className="text-center">
                    <p className="text-lg font-medium text-gray-700">
                      {loading ? 'Parsing...' : 'Click to upload or drag and drop'}
                    </p>
                    <p className="text-sm text-gray-500 mt-2">STL (max 100MB)</p>
                  </div>
                </div>
              </label>
            </div>
          </div>
        )}

        {/* Step 2: Configure */}
        {step === 2 && modelStats && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Model Info */}
            <div className="bg-white rounded-lg shadow-lg p-6">
              <h3 className="text-lg font-bold mb-4 flex items-center">
                <Settings className="w-5 h-5 mr-2 text-indigo-600" />
                Model Analysis
              </h3>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-gray-600">File:</span>
                  <span className="font-medium text-sm">{modelFile?.name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Volume:</span>
                  <span className="font-medium">{modelStats.volume?.toFixed(2)} cm³</span>
                </div>
                {modelStats.weight && (
                  <div className="flex justify-between">
                    <span className="text-gray-600">Est. Weight:</span>
                    <span className="font-medium">{modelStats.weight?.toFixed(2)}g</span>
                  </div>
                )}
                {modelStats.bounding_box && (
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600">Dimensions:</span>
                    <span className="font-medium">
                      {modelStats.bounding_box.x?.toFixed(1)} × {modelStats.bounding_box.y?.toFixed(1)} × {modelStats.bounding_box.z?.toFixed(1)} mm
                    </span>
                  </div>
                )}
                {modelStats.is_watertight !== undefined && (
                  <div className="flex justify-between">
                    <span className="text-gray-600">Watertight:</span>
                    <span className={`font-medium ${modelStats.is_watertight ? 'text-green-600' : 'text-yellow-600'}`}>
                      {modelStats.is_watertight ? 'Yes' : 'No'}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Configuration */}
            <div className="lg:col-span-2 bg-white rounded-lg shadow-lg p-6">
              <h3 className="text-lg font-bold mb-4">Configure Your Print</h3>
              
              {/* Material Selection */}
              <div className="mb-6">
                <label className="block text-sm font-medium text-gray-700 mb-2">Material</label>
                <div className="grid grid-cols-2 gap-3">
                  {materials.map(material => (
                    <div
                      key={material.id}
                      onClick={() => setSelections({...selections, material: material.id})}
                      className={`p-4 border-2 rounded-lg cursor-pointer transition ${
                        selections.material === material.id ? 'border-indigo-600 bg-indigo-50' : 'border-gray-200 hover:border-indigo-300'
                      }`}
                    >
                      <div className="font-medium">{material.name}</div>
                      <div className="text-xs text-gray-600">{material.description}</div>
                      <div className="text-sm text-indigo-600 mt-1">${material.pricePerKg}/kg</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* ZIP Code */}
              <div className="mb-6">
                <label className="block text-sm font-medium text-gray-700 mb-2">ZIP Code (for tax & shipping)</label>
                <input
                  type="text"
                  value={selections.zip_code}
                  onChange={(e) => setSelections({...selections, zip_code: e.target.value})}
                  placeholder="12345"
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                />
              </div>

              {/* Quantity */}
              <div className="mb-6">
                <label className="block text-sm font-medium text-gray-700 mb-2">Quantity</label>
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={selections.quantity}
                  onChange={(e) => setSelections({...selections, quantity: parseInt(e.target.value) || 1})}
                  className="w-32 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                />
              </div>

              {/* Rush Order */}
              <div className="mb-6">
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={selections.rush_order}
                    onChange={(e) => setSelections({...selections, rush_order: e.target.checked})}
                    className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-2 focus:ring-indigo-500"
                  />
                  <span className="ml-2 text-sm font-medium text-gray-700">Rush Order (+$20)</span>
                </label>
              </div>

              <button
                onClick={calculatePrice}
                disabled={!selections.material || !selections.zip_code || loading}
                className="w-full bg-indigo-600 text-white py-3 rounded-lg font-medium hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition"
              >
                {loading ? 'Calculating...' : 'Get Quote'}
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Review & Order */}
        {step === 3 && quote && (
          <div className="max-w-4xl mx-auto">
            <div className="bg-white rounded-lg shadow-lg p-8">
              <h2 className="text-2xl font-bold mb-6 flex items-center">
                <CheckCircle className="w-7 h-7 mr-2 text-green-600" />
                Review Your Order
              </h2>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
                {/* Model Details */}
                <div>
                  <h3 className="font-semibold mb-3 text-gray-700">Model Details</h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-600">File:</span>
                      <span>{modelFile?.name}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Volume:</span>
                      <span>{modelStats.volume?.toFixed(2)} cm³</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Weight:</span>
                      <span>{(modelStats.weight || (modelStats.volume * materials.find(m => m.id === selections.material)?.density))?.toFixed(2)}g</span>
                    </div>
                  </div>
                </div>

                {/* Configuration */}
                <div>
                  <h3 className="font-semibold mb-3 text-gray-700">Configuration</h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-600">Material:</span>
                      <span>{materials.find(m => m.id === selections.material)?.name}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Quantity:</span>
                      <span>{selections.quantity}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Rush Order:</span>
                      <span>{selections.rush_order ? 'Yes' : 'No'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">ZIP Code:</span>
                      <span>{selections.zip_code}</span>
                    </div>
                  </div>
                </div>

                {/* Contact Information */}
                <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
                  <h3 className="font-semibold mb-3 text-gray-700">Your Information</h3>
                  <div className="space-y-3">
                    <div>
                      <label className="text-xs font-medium text-gray-600">Email *</label>
                      <input
                        type="email"
                        value={selections.email}
                        onChange={(e) => setSelections({...selections, email: e.target.value})}
                        placeholder="your@email.com"
                        className="w-full mt-1 px-2 py-1 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-gray-600">Full Name *</label>
                      <input
                        type="text"
                        value={selections.name}
                        onChange={(e) => setSelections({...selections, name: e.target.value})}
                        placeholder="John Doe"
                        className="w-full mt-1 px-2 py-1 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-gray-600">Phone</label>
                      <input
                        type="tel"
                        value={selections.phone}
                        onChange={(e) => setSelections({...selections, phone: e.target.value})}
                        placeholder="(555) 123-4567"
                        className="w-full mt-1 px-2 py-1 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                      />
                    </div>
                  </div>
                </div>

                {/* Shipping Address (for Click-N-Ship) */}
                <div className="bg-red-50 p-4 rounded-lg border-2 border-red-300">
                  <h3 className="font-semibold mb-1 text-gray-700">Shipping Address *</h3>
                  <p className="text-xs text-gray-600 mb-3">(Required for label creation)</p>
                  
                  <div className="space-y-2">
                    {/* Name fields */}
                    <div className="grid grid-cols-12 gap-2">
                      <div className="col-span-5">
                        <label className="text-xs font-medium text-gray-600">First Name</label>
                        <input
                          type="text"
                          value={selections.first_name}
                          onChange={(e) => setSelections({...selections, first_name: e.target.value})}
                          placeholder="John"
                          className="w-full mt-1 px-2 py-1 border border-gray-300 rounded text-xs focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                        />
                      </div>
                      <div className="col-span-2">
                        <label className="text-xs font-medium text-gray-600">MI</label>
                        <input
                          type="text"
                          maxLength="1"
                          value={selections.middle_initial}
                          onChange={(e) => setSelections({...selections, middle_initial: e.target.value.toUpperCase()})}
                          placeholder="M"
                          className="w-full mt-1 px-2 py-1 border border-gray-300 rounded text-xs text-center focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                        />
                      </div>
                      <div className="col-span-5">
                        <label className="text-xs font-medium text-gray-600">Last Name</label>
                        <input
                          type="text"
                          value={selections.last_name}
                          onChange={(e) => setSelections({...selections, last_name: e.target.value})}
                          placeholder="Doe"
                          className="w-full mt-1 px-2 py-1 border border-gray-300 rounded text-xs focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                        />
                      </div>
                    </div>

                    {/* Company */}
                    <div>
                      <label className="text-xs font-medium text-gray-600">Company</label>
                      <input
                        type="text"
                        value={selections.company}
                        onChange={(e) => setSelections({...selections, company: e.target.value})}
                        placeholder="Company Name (optional)"
                        className="w-full mt-1 px-2 py-1 border border-gray-300 rounded text-xs focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                      />
                    </div>

                    {/* Street */}
                    <div>
                      <label className="text-xs font-medium text-gray-600">Street Address *</label>
                      <input
                        type="text"
                        value={selections.street_address}
                        onChange={(e) => setSelections({...selections, street_address: e.target.value})}
                        placeholder="123 Main St"
                        className="w-full mt-1 px-2 py-1 border border-gray-300 rounded text-xs focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                      />
                    </div>

                    {/* Apt/Suite */}
                    <div>
                      <label className="text-xs font-medium text-gray-600">Apt/Suite/Other</label>
                      <input
                        type="text"
                        value={selections.apt_suite}
                        onChange={(e) => setSelections({...selections, apt_suite: e.target.value})}
                        placeholder="Apt 4B (optional)"
                        className="w-full mt-1 px-2 py-1 border border-gray-300 rounded text-xs focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                      />
                    </div>

                    {/* City, State, ZIP */}
                    <div className="grid grid-cols-12 gap-2">
                      <div className="col-span-6">
                        <label className="text-xs font-medium text-gray-600">City *</label>
                        <input
                          type="text"
                          value={selections.city}
                          readOnly
                          placeholder="New York"
                          className="w-full mt-1 px-2 py-1 border border-gray-300 rounded text-xs bg-gray-50 text-gray-700 cursor-not-allowed"
                        />
                      </div>
                      <div className="col-span-2">
                        <label className="text-xs font-medium text-gray-600">State *</label>
                        <input
                          type="text"
                          maxLength="2"
                          value={selections.state}
                          readOnly
                          placeholder="NY"
                          className="w-full mt-1 px-2 py-1 border border-gray-300 rounded text-xs text-center bg-gray-50 text-gray-700 cursor-not-allowed"
                        />
                      </div>
                      <div className="col-span-4">
                        <label className="text-xs font-medium text-gray-600">ZIP *</label>
                        <input
                          type="text"
                          value={selections.zip_code}
                          onChange={(e) => setSelections({...selections, zip_code: e.target.value})}
                          placeholder="10001"
                          className="w-full mt-1 px-2 py-1 border border-gray-300 rounded text-xs focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                        />
                      </div>
                    </div>
                  </div>
                </div>

              </div>

              {/* Shipping Options */}
              <div className="bg-blue-50 p-4 rounded-lg border-2 border-blue-300">
                <h3 className="font-semibold mb-3 text-gray-700">Shipping Options</h3>
                {loadingRates ? (
                  <div className="text-center py-4">
                    <p className="text-gray-600">Loading available shipping services...</p>
                  </div>
                ) : shippingRates.length > 0 ? (
                  <div className="space-y-2">
                    {shippingRates.map((rate, idx) => (
                      <label key={idx} className="flex items-center p-3 border rounded-lg cursor-pointer hover:bg-blue-100 transition" style={{backgroundColor: selectedShippingService?.serviceCode === rate.serviceCode ? '#dbeafe' : '#f0f9ff'}}>
                        <input
                          type="radio"
                          name="shippingService"
                          checked={selectedShippingService?.serviceCode === rate.serviceCode}
                          onChange={() => {
                            setSelectedShippingService(rate);
                          }}
                          className="mr-3 w-4 h-4 text-indigo-600"
                        />
                        <div className="flex-1">
                          <div className="font-medium text-gray-700">
                            {rate.serviceName || `Service ${idx + 1}`}
                          </div>
                          <div className="text-xs text-gray-500">
                            {rate.estimatedDays ? `Estimated delivery: ${rate.estimatedDays} business day${rate.estimatedDays > 1 ? 's' : ''}` : 'Delivery time TBA'}
                          </div>
                        </div>
                        <div className="text-lg font-semibold text-indigo-600">{rate.displayCost || `$${rate.cost?.toFixed(2)}`}</div>
                      </label>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-4">
                    <p className="text-gray-600 text-sm">Unable to load shipping rates. Proceeding with standard shipping.</p>
                  </div>
                )}
              </div>

              <div className="bg-white rounded-lg shadow-lg p-8 mt-6">
                <div className="space-y-2 mb-6 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Base Cost:</span>
                    <span>{quote.base_cost}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Material Cost:</span>
                    <span>{quote.material_cost}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Shipping ({selectedShippingService?.serviceName || 'Standard'}):</span>
                    <span>${selectedShippingService?.cost?.toFixed(2) || parseFloat(quote.shipping_cost.replace('$', '')).toFixed(2)}</span>
                  </div>
                  {selections.rush_order && (
                    <div className="flex justify-between">
                      <span className="text-gray-600">Rush Surcharge:</span>
                      <span>{quote.rush_order_surcharge}</span>
                    </div>
                  )}
                  <div className="flex justify-between">
                    <span className="text-gray-600">Sales Tax:</span>
                    <span>
                      {(() => {
                        const baseAmount = parseFloat(quote.base_cost.replace('$', ''));
                        const materialAmount = parseFloat(quote.material_cost.replace('$', ''));
                        const shippingAmount = selectedShippingService?.cost || parseFloat(quote.shipping_cost.replace('$', ''));
                        const rushAmount = selections.rush_order ? parseFloat(quote.rush_order_surcharge.replace('$', '')) : 0;
                        const subtotal = baseAmount + materialAmount + shippingAmount + rushAmount;
                        const taxRate = 0.07; // Default 7% if not found
                        const tax = subtotal * taxRate;
                        return `$${tax.toFixed(2)}`;
                      })()}
                    </span>
                  </div>
                </div>

                <div className="flex items-center justify-between mb-6 border-t pt-6">
                  <div className="flex items-center">
                    <DollarSign className="w-8 h-8 text-green-600 mr-2" />
                    <div>
                      <div className="text-sm text-gray-600">Total Price</div>
                      <div className="text-3xl font-bold text-gray-900">
                        {(() => {
                          const baseAmount = parseFloat(quote.base_cost.replace('$', ''));
                          const materialAmount = parseFloat(quote.material_cost.replace('$', ''));
                          const shippingAmount = selectedShippingService?.cost || parseFloat(quote.shipping_cost.replace('$', ''));
                          const rushAmount = selections.rush_order ? parseFloat(quote.rush_order_surcharge.replace('$', '')) : 0;
                          const subtotal = baseAmount + materialAmount + shippingAmount + rushAmount;
                          const taxRate = 0.07; // Default 7% if not found
                          const tax = subtotal * taxRate;
                          const total = subtotal + tax;
                          return `$${total.toFixed(2)}`;
                        })()}
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm text-gray-600">Estimated Delivery</div>
                    <div className="text-lg font-semibold">{selectedShippingService?.estimatedDays ? `${selectedShippingService.estimatedDays} business day${selectedShippingService.estimatedDays > 1 ? 's' : ''}` : '3-5 business days'}</div>
                  </div>
                </div>

              <div className="grid grid-cols-2 gap-4">
                  <button
                    onClick={() => setStep(2)}
                    className="px-6 py-3 border-2 border-gray-300 rounded-lg font-medium hover:bg-gray-50 transition"
                  >
                    Back to Configure
                  </button>
                  <button
                    onClick={proceedToCheckout}
                    disabled={!selections.email || !selections.name || loading}
                    className="px-6 py-3 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition"
                  >
                    {loading ? 'Processing...' : 'Proceed to Checkout'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
          </div>
        </>
      )}
    </>
  );
};

const App = () => {
  const PaymentSuccessRoute = () => {
    const location = useLocation();
    const params = new URLSearchParams(location.search);
    return (
      <PaymentSuccess
        orderId={params.get('order_id')}
        customerId={params.get('customer_id')}
      />
    );
  };

  return (
    <Router>
      <Routes>
        <Route path="/" element={<QuoteForm />} />
        <Route path="/payment-success" element={<PaymentSuccessRoute />} />
        <Route path="/dashboard/shipping" element={<ShippingDashboard />} />
      </Routes>
    </Router>
  );
};

export default App;
