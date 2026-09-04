/**
 * Which address shows which page.
 *
 * Four routes, exactly as the specification asks:
 *
 *     /           the public introduction
 *     /login      log in
 *     /register   create an account
 *     /app        everything else, for logged-in users
 *
 * `/app` holds the classification, marketplace and My Listings sections as tabs
 * rather than as separate addresses. That is a deliberate choice to avoid a
 * sprawl of pages that each show one panel.
 */

import { Navigate, Route, Routes } from "react-router-dom";

import Layout from "./components/Layout.jsx";
import { Spinner } from "./components/ui.jsx";
import { useAuth } from "./context/useAuth.js";
import AppPage from "./pages/AppPage.jsx";
import HomePage from "./pages/HomePage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import NotFoundPage from "./pages/NotFoundPage.jsx";
import RegisterPage from "./pages/RegisterPage.jsx";

/** Shown while the stored token is being checked against the backend. */
function CheckingSession() {
  return (
    <div className="flex justify-center py-16">
      <Spinner label="Checking your session…" />
    </div>
  );
}

/**
 * Wraps a page that requires a login.
 *
 * Note this is a convenience, not the security boundary. Every endpoint checks
 * the token on the server, so nothing sensitive is protected by this component -
 * it exists so someone who is not logged in sees the login page instead of a
 * screen of failed requests.
 *
 * `replace` matters: without it the redirect would be added to the browser
 * history, and the Back button would bounce the person forwards again.
 */
function RequireAuth({ children }) {
  const { isLoggedIn, checking } = useAuth();

  if (checking) return <CheckingSession />;
  if (!isLoggedIn) return <Navigate to="/login" replace />;
  return children;
}

/**
 * Wraps the login and register pages.
 *
 * Someone who is already logged in has no use for these, so they go straight to
 * the application instead.
 */
function RedirectIfLoggedIn({ children }) {
  const { isLoggedIn, checking } = useAuth();

  if (checking) return <CheckingSession />;
  if (isLoggedIn) return <Navigate to="/app" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      {/* Every page below shares the header from Layout. */}
      <Route element={<Layout />}>
        <Route path="/" element={<HomePage />} />

        <Route
          path="/login"
          element={
            <RedirectIfLoggedIn>
              <LoginPage />
            </RedirectIfLoggedIn>
          }
        />
        <Route
          path="/register"
          element={
            <RedirectIfLoggedIn>
              <RegisterPage />
            </RedirectIfLoggedIn>
          }
        />

        <Route
          path="/app"
          element={
            <RequireAuth>
              <AppPage />
            </RequireAuth>
          }
        />

        {/* Anything else. */}
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
