/**
 * Who is logged in, available to every page.
 *
 * React's *context* is a way to share one value with a whole tree of components
 * without passing it down through every level by hand. Without it, the logged-in
 * user would have to be handed from App to the layout to the header to the
 * button, one prop at a time.
 *
 * The pattern in this file is the usual one:
 *
 *   <AuthProvider>  wraps the app (see main.jsx) and holds the state
 *   useAuth()       is what a page calls to read it - it lives next door in
 *                   context/useAuth.js, for the reason explained there
 *
 * Where the token lives, and why
 * ------------------------------
 * The token is kept in `localStorage`, which survives a page refresh and
 * closing the tab. That is what makes "stay logged in" work. The trade-off is
 * that JavaScript running on the page can read it, so a cross-site-scripting
 * hole would expose it - the safer alternative is an HttpOnly cookie, which
 * needs CSRF protection in return. For a local project this is the standard
 * choice, and it is written up as a known limitation in the README.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  api,
  errorMessage,
  getToken,
  setToken,
  setUnauthorizedHandler,
} from "../services/api";
import { AuthContext } from "./useAuth";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);

  // True until the "is my stored token still good?" check has finished.
  //
  // This exists to stop a flicker. On a refresh the app starts with a token but
  // no user, and without this flag the router would decide "not logged in" and
  // show the login page for a moment before the check came back and bounced the
  // person to where they actually were.
  const [checking, setChecking] = useState(Boolean(getToken()));

  /** Forget the session in this browser. */
  const clearSession = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  // --- Deal with a token that has expired ---------------------------------
  //
  // A token lasts JWT_EXPIRE_MINUTES (60 by default). After that the backend
  // refuses everything with a 401, and this hands the app back to the login
  // page instead of leaving it showing panels that will not load.
  useEffect(() => {
    setUnauthorizedHandler(clearSession);
    return () => setUnauthorizedHandler(null);
  }, [clearSession]);

  // --- On start-up: is the stored token still valid? ----------------------
  //
  // The browser has a token but cannot tell whether it has expired - only the
  // backend knows, because only the backend can check the signature. GET
  // /api/auth/me is the cheapest way to ask.
  useEffect(() => {
    // No token, so there is nothing to check. `checking` already started as
    // false in that case - it is initialised from getToken() above - so there
    // is deliberately no setState here.
    if (!getToken()) return;

    let cancelled = false;

    api
      .get("/api/auth/me")
      .then((response) => {
        if (!cancelled) setUser(response.data);
      })
      .catch(() => {
        // Expired or invalid. The 401 interceptor has already cleared the
        // session; this catch just stops an unhandled rejection appearing in
        // the console.
        if (!cancelled) clearSession();
      })
      .finally(() => {
        if (!cancelled) setChecking(false);
      });

    // React runs effects twice in development (StrictMode) to help surface
    // bugs. This flag means the second run cannot overwrite state from the
    // first after it has been thrown away.
    return () => {
      cancelled = true;
    };
  }, [clearSession]);

  /**
   * Log in, and remember the session.
   *
   * Returns `{ ok: true }` or `{ ok: false, message }` rather than throwing.
   * The form needs to *display* the reason, and a returned message is simpler
   * for that than a try/catch in every caller.
   */
  const login = useCallback(async (email, password) => {
    try {
      const response = await api.post("/api/auth/login", { email, password });
      setToken(response.data.access_token);
      setUser(response.data.user);
      return { ok: true };
    } catch (error) {
      return { ok: false, message: errorMessage(error, "Could not log in.") };
    }
  }, []);

  /**
   * Create an account, then log straight in with it.
   *
   * POST /api/auth/register returns the new account but **not** a token, so a
   * second request is needed to get one. Doing it here means the person is not
   * made to type the password they just chose all over again.
   */
  const register = useCallback(
    async (details) => {
      try {
        await api.post("/api/auth/register", details);
      } catch (error) {
        return { ok: false, message: errorMessage(error, "Could not register.") };
      }
      return login(details.email, details.password);
    },
    [login],
  );

  /**
   * Log out.
   *
   * The real work happens in the browser: deleting the token is what ends the
   * session. A JWT is stateless, so the server keeps no list of who is logged
   * in and cannot cancel a token that is already out in the world - it stays
   * technically valid until it expires.
   *
   * The backend is still told, because the endpoint exists and calling it keeps
   * the two sides honest about what happened. If that call fails - the server
   * is down, say - the local session is cleared regardless: being unable to
   * reach the backend must never leave someone stuck logged in.
   */
  const logout = useCallback(async () => {
    try {
      await api.post("/api/auth/logout");
    } catch {
      // Deliberately ignored, for the reason above.
    }
    clearSession();
  }, [clearSession]);

  // useMemo keeps this object identical between renders unless something in it
  // actually changed. Without it, every render would build a new object and
  // every component reading the context would re-render for no reason.
  const value = useMemo(
    () => ({ user, checking, isLoggedIn: user !== null, login, register, logout }),
    [user, checking, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
