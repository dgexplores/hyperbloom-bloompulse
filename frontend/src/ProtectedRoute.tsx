import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./auth";

interface ProtectedRouteProps {
  children: React.ReactNode;
  allowedRoles?: ("admin" | "engineer" | "viewer")[];
}

export function ProtectedRoute({ children, allowedRoles }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading, user } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="loading-screen" role="status" aria-label="Loading authentication">
        <div className="spinner" aria-hidden="true"></div>
        <p>Verifying authentication…</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (allowedRoles && allowedRoles.length > 0) {
    const userRole = user?.role;
    if (!userRole || !allowedRoles.includes(userRole)) {
      return <Navigate to="/unauthorized" replace />;
    }
  }

  return <>{children}</>;
}