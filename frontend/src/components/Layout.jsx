import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/useAuth";
import { LogOutIcon, PalmIcon, StoreIcon, UserIcon } from "./icons";

function HeaderLink({ to, children }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `rounded-xl px-4 py-2 text-sm font-semibold transition-all duration-150 flex items-center gap-2 ${
          isActive
            ? "bg-amber-500/10 text-amber-900 border border-amber-500/20 shadow-xs"
            : "text-stone-600 hover:bg-stone-100 hover:text-stone-900"
        }`
      }
    >
      {children}
    </NavLink>
  );
}

export default function Layout() {
  const { user, isLoggedIn, logout } = useAuth();

  return (
    <div className="min-h-screen bg-stone-50/60 flex flex-col font-sans">
      {/* --- Sticky Glassmorphic Header --------------------------------- */}
      <header className="sticky top-0 z-40 border-b border-stone-200/80 bg-white/90 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <Link to="/" className="flex items-center gap-3 group">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-amber-600 to-amber-500 text-white shadow-md shadow-amber-600/20 group-hover:scale-105 transition-transform">
              <PalmIcon className="h-5 w-5 text-white" />
            </div>
            <div>
              <span className="text-base font-bold tracking-tight text-stone-900 block leading-tight">
                Date Fruit AI
              </span>
              <span className="text-xs font-medium text-amber-700 block">
                Price Marketplace
              </span>
            </div>
          </Link>

          <nav className="flex items-center gap-2 sm:gap-3">
            {isLoggedIn ? (
              <>
                <HeaderLink to="/app">
                  <StoreIcon className="h-4 w-4 text-amber-600" />
                  Marketplace
                </HeaderLink>

                <div className="h-5 w-px bg-stone-200 mx-1 hidden sm:block" />

                <div className="flex items-center gap-2 rounded-xl bg-stone-100/80 px-3 py-1.5 border border-stone-200/60">
                  <div className="flex h-6 w-6 items-center justify-center rounded-full bg-amber-600 text-[10px] font-bold text-white uppercase">
                    {user?.name ? user.name[0] : <UserIcon className="w-3.5 h-3.5" />}
                  </div>
                  <span className="text-xs font-semibold text-stone-700 hidden sm:inline">
                    {user?.name}
                  </span>
                </div>

                <button
                  type="button"
                  onClick={logout}
                  className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-stone-200 bg-white px-3 py-1.5 text-xs font-semibold text-stone-700 shadow-xs hover:bg-stone-50 hover:text-red-600 transition"
                  title="Log out"
                >
                  <LogOutIcon className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">Log out</span>
                </button>
              </>
            ) : (
              <>
                <HeaderLink to="/login">Log in</HeaderLink>
                <Link
                  to="/register"
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-amber-600 px-4 py-2 text-sm font-semibold text-white shadow-xs hover:bg-amber-700 transition"
                >
                  Register
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>

      {/* --- Main Content Area ------------------------------------------ */}
      <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6 flex-1">
        <Outlet />
      </main>

      {/* --- Footer ---------------------------------------------------- */}
      <footer className="border-t border-stone-200/60 bg-white py-6">
        <div className="mx-auto max-w-6xl px-4 text-center text-xs text-stone-500 flex flex-col sm:flex-row items-center justify-between gap-2">
          <p className="flex items-center gap-1">
            <PalmIcon className="w-4 h-4 text-amber-600 inline" />
            &copy; {new Date().getFullYear()} Date Fruit AI &amp; Marketplace. All rights reserved.
          </p>
          <p className="text-stone-400">
            Prices are published by users &amp; verified via AI classification confidence score.
          </p>
        </div>
      </footer>
    </div>
  );
}
