/**
 * The one place in the React app that talks to FastAPI.
 *
 * Everything the browser sends to the backend goes through the `api` object
 * below. That is deliberate: the backend address, the login token and the
 * error-message handling are each written once here instead of being repeated
 * in every page. If the backend ever moves to a different port, this file is
 * the only one that changes.
 */

import axios from "axios";

// ---------------------------------------------------------------------------
// Where the backend lives
// ---------------------------------------------------------------------------
//
// Vite replaces `import.meta.env.VITE_API_URL` with the value from
// frontend/.env when it builds the app. Only names starting with VITE_ are
// exposed to the browser - that rule is Vite's way of stopping you leaking a
// secret into a public page by accident.
//
// The fallback matters for a fresh clone: if someone forgets to copy
// .env.example to .env, the app still points at the usual local address rather
// than at "undefined".
//
// The trailing slash is stripped so joining paths never produces a double
const defaultBackend = (typeof window !== "undefined" && window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1")
  ? "https://bac55cbe19d50a71-116-204-148-137.serveousercontent.com"
  : "http://localhost:8000";
const RAW_BASE = import.meta.env.VITE_API_URL || defaultBackend;
export const API_BASE = RAW_BASE.replace(/\/+$/, "");

/** Where the login token is kept in the browser. */
const TOKEN_KEY = "date_fruit_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

// ---------------------------------------------------------------------------
// The axios client
// ---------------------------------------------------------------------------
export const api = axios.create({ baseURL: API_BASE });

/**
 * Attach the login token to every outgoing request.
 *
 * An *interceptor* is a function axios runs on each request before it leaves
 * the browser. Doing it here means no page ever has to remember to send the
 * token - which is exactly the kind of thing that gets forgotten in one place
 * and causes a confusing 401.
 *
 * The backend expects the header `Authorization: Bearer <token>`; that format
 * is what `app/core/deps.py` reads on the server side.
 */
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ---------------------------------------------------------------------------
// Expired-token handling
// ---------------------------------------------------------------------------
//
// A token is only valid for JWT_EXPIRE_MINUTES (60 by default). Once it
// expires the backend answers 401 to everything, and the app should return to
// the login page rather than showing broken panels.
//
// AuthContext registers a function here at start-up. This file deliberately
// does not import React: keeping the HTTP layer separate from the interface
// means either can be understood without the other.
let onUnauthorized = null;

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    const url = error.config?.url ?? "";

    // A 401 from the login or register endpoint means "wrong email or
    // password" - a normal, expected answer that the form shows as a message.
    // Treating that as an expired session would wipe the session of someone
    // who simply mistyped, and on the login page there is no session to wipe
    // anyway. So those two are excluded.
    const isLoginAttempt =
      url.includes("/api/auth/login") || url.includes("/api/auth/register");

    if (status === 401 && !isLoginAttempt && onUnauthorized) {
      onUnauthorized();
    }
    return Promise.reject(error);
  },
);

// ---------------------------------------------------------------------------
// Turning an error into a sentence a person can read
// ---------------------------------------------------------------------------
/**
 * Pull a human-readable message out of whatever went wrong.
 *
 * FastAPI reports problems in two different shapes, and both have to be
 * handled or the interface ends up displaying "[object Object]":
 *
 *   A deliberate rejection (HTTPException) - `detail` is a string:
 *       { "detail": "Incorrect email or password." }
 *
 *   A validation failure (422) - `detail` is a list, one entry per bad field:
 *       { "detail": [ { "loc": ["body", "price"], "msg": "..." } ] }
 *
 * There is also the case where the request never arrived at all - the backend
 * is not running - which has no response to read.
 */
export function errorMessage(error, fallback = "Something went wrong.") {
  // The request never got a reply: server down, or the wrong address.
  if (error?.response === undefined) {
    if (error?.code === "ERR_NETWORK") {
      return (
        `Could not reach the backend at ${API_BASE}. Is the FastAPI server ` +
        `running?`
      );
    }
    return error?.message || fallback;
  }

  const detail = error.response.data?.detail;

  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {
    // Name the field as well as the problem. `loc` is a path like
    // ["body", "price"], and the last part is the field the person can see.
    return detail
      .map((item) => {
        const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : null;
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .join(" ");
  }

  // Some other shape, or an empty body (a 500, typically).
  return `${fallback} (HTTP ${error.response.status})`;
}

// ---------------------------------------------------------------------------
// Listing photographs
// ---------------------------------------------------------------------------
/**
 * Turn a listing's `image_url` into an address the browser can load.
 *
 * The API returns a root-relative path - "/uploads/listings/9f2c8b1d.jpg" -
 * because it does not know what address the browser reached it on. That path
 * has to be joined onto the backend base, otherwise the browser would look for
 * the photo on the React dev server (port 5173) where it does not exist.
 *
 * Returns null when a listing has no photo, so the caller can show a
 * placeholder instead of a broken image icon.
 */
export function imageUrl(path) {
  if (!path) return null;
  return `${API_BASE}${path}`;
}
