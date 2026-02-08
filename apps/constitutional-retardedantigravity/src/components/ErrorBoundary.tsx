import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

interface Props {
  fallback?: ReactNode;
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary] Caught:", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: "100%",
            height: "100%",
            backgroundColor: "rgba(15, 118, 110, 0.06)",
            borderRadius: "12px",
          }}
        >
          <div
            style={{
              textAlign: "center",
              fontFamily: "monospace",
              color: "#0f766e",
              padding: "24px",
            }}
          >
            <div style={{ fontSize: "14px", fontWeight: 600, marginBottom: "8px" }}>
              3D visualization unavailable
            </div>
            <div style={{ fontSize: "12px", opacity: 0.7 }}>
              {this.state.error?.message || "WebGL context lost or unsupported"}
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
