import React from 'react';
import { Package } from 'lucide-react';
import { Link } from 'react-router-dom';

const GlobalHeader = ({ showBackButton = false, backTo = "/" }) => {
  return (
    <header className="bg-white border-b border-gray-200">
      <div className="max-w-7xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Package className="w-8 h-8 text-indigo-600" />
            <h1 className="text-2xl font-bold text-gray-900">Print3D Pro</h1>
          </div>
          <div className="flex items-center space-x-4">
            {showBackButton && (
              <Link
                to={backTo}
                className="px-4 py-2 text-sm font-medium text-indigo-600 hover:text-indigo-700 transition-colors"
              >
                ← Back to Previous Page
              </Link>
            )}
            <div className="flex space-x-4 text-sm text-gray-600">
              <span>Instant Quote</span>
              <span>•</span>
              <span>Fast Turnaround</span>
              <span>•</span>
              <span>Quality Assured</span>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};

export default GlobalHeader;
