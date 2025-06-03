'use client';

import { useState } from 'react';

interface DocumentPanelProps {
  documentText: string;
}

export default function DocumentPanel({ documentText }: DocumentPanelProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);

  return (
    <div className={`h-full bg-white dark:bg-gray-800 shadow-lg transition-all duration-300 ease-in-out ${
      isCollapsed ? 'w-12' : 'w-96'
    }`}>
      {/* Collapse/Expand Button */}
      <button
        onClick={() => setIsCollapsed(!isCollapsed)}
        className="absolute right-0 top-4 bg-blue-500 hover:bg-blue-600 text-white rounded-full p-1 shadow-md"
      >
        {isCollapsed ? (
          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        ) : (
          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        )}
      </button>

      {/* Document Content */}
      <div className={`h-full overflow-y-auto p-4 ${isCollapsed ? 'hidden' : 'block'}`}>
        <h2 className="text-xl font-semibold mb-4 text-gray-800 dark:text-gray-200">Document Content</h2>
        <div className="prose dark:prose-invert max-w-none">
          <pre className="whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-300">
            {documentText}
          </pre>
        </div>
      </div>
    </div>
  );
} 