import React from "react";

/* A thrown render error blanked the whole page during development, which in
   production would leave an operator staring at empty paper. The chart keeps
   its own boundary so a bad series cannot take the verdict down with it. */
export default class ErrorBoundary extends React.Component<
  { children: React.ReactNode; label: string },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.error("BloomPulse render failure", error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <p className="notice" role="alert">
        <span className="notice-tag">Fault</span>
        <span>
          {this.props.label} could not be drawn. Reload the page, and if it
          keeps happening the file is likely shaped in a way this build does
          not handle yet.
        </span>
      </p>
    );
  }
}
