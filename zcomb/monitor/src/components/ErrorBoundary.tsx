import { Component, type ReactNode, type ErrorInfo } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null, errorInfo: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ errorInfo });
    console.error('Dashboard render error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          height: '100vh',
          background: '#0d1117',
          color: '#e6edf3',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif',
        }}>
          <div style={{
            maxWidth: 600,
            padding: 40,
            background: '#161b22',
            borderRadius: 12,
            border: '1px solid #30363d',
          }}>
            <h2 style={{ color: '#f85149', margin: '0 0 16px', fontSize: 20 }}>
              Dashboard Error
            </h2>
            <p style={{ color: '#7d8590', margin: '0 0 16px', lineHeight: 1.5 }}>
              The dashboard encountered a rendering error. This is usually caused by
              unexpected data in the state files.
            </p>
            <pre style={{
              background: '#0d1117',
              padding: 16,
              borderRadius: 8,
              overflow: 'auto',
              fontSize: 12,
              color: '#f85149',
              border: '1px solid #21262d',
              maxHeight: 200,
            }}>
              {this.state.error?.message}
              {this.state.errorInfo?.componentStack && (
                <span style={{ color: '#7d8590' }}>
                  {'\n'}
                  {this.state.errorInfo.componentStack}
                </span>
              )}
            </pre>
            <button
              onClick={() => this.setState({ hasError: false, error: null, errorInfo: null })}
              style={{
                marginTop: 16,
                background: '#238636',
                color: '#fff',
                border: 'none',
                borderRadius: 6,
                padding: '8px 20px',
                fontSize: 14,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Retry
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
