/**
 * Reading the logged-in user from any component.
 *
 * This sits in its own file, apart from `AuthContext.jsx`, for a practical
 * reason: Vite's "fast refresh" can only hot-reload a file while you edit it if
 * that file exports *only* components. `AuthProvider` is a component and
 * `useAuth` is not, so keeping them together would mean every edit to either one
 * reloaded the whole page and threw away your login.
 *
 * The context object lives here too, because both files need it.
 */

import { createContext, useContext } from "react";

/**
 * The shared box the provider puts the auth state into.
 *
 * `null` is the default, which is what a component gets if it reads this without
 * an <AuthProvider> above it. `useAuth` below turns that into a clear error.
 */
export const AuthContext = createContext(null);

/**
 * Read the logged-in user: `const { user, isLoggedIn, logout } = useAuth()`.
 *
 * What comes back:
 *
 *     user        the account object, or null when logged out
 *     isLoggedIn  true when there is a user
 *     checking    true while a stored token is being verified on start-up
 *     login       (email, password)   -> { ok, message? }
 *     register    (details)           -> { ok, message? }
 *     logout      ()                  -> Promise
 */
export function useAuth() {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth() must be used inside <AuthProvider>.");
  }
  return context;
}
