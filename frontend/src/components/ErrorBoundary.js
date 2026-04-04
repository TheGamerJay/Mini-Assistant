/**
 * ErrorBoundary.js
 * Catches runtime errors in any child component tree and shows a
 * recoverable fallback instead of a blank screen.
 */
import React from 'react';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error('[ErrorBoundary] Caught error:', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-full min-h-[200px] gap-4 p-8 text-center">
          <div className="text-2xl">⚠️</div>
          <p className="text-slate-300 font-medium">Something went wrong.</p>
          <p className="text-slate-500 text-sm max-w-xs">
            {this.state.error?.message || 'An unexpected error occurred in this section.'}
          </p>
          <button
            onClick={() => {
              this.setState({ hasError: false, error: null });
              window.location.reload();
            }}
            className="mt-2 px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-sm transition-colors"
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
