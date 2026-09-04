import React from "react";
import { AlertTriangleIcon, CheckCircleIcon } from "./icons";

/** A coloured message box for errors, successes and hints. */
export function Alert({ kind = "error", children }) {
  if (!children) return null;

  const styles = {
    error: "border-l-4 border-l-red-500 bg-red-50/90 border-red-200 text-red-900",
    success: "border-l-4 border-l-emerald-500 bg-emerald-50/90 border-emerald-200 text-emerald-900",
    info: "border-l-4 border-l-sky-500 bg-sky-50/90 border-sky-200 text-sky-900",
    warning: "border-l-4 border-l-amber-500 bg-amber-50/90 border-amber-200 text-amber-900",
  };

  const icons = {
    error: <AlertTriangleIcon className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />,
    success: <CheckCircleIcon className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />,
    info: <CheckCircleIcon className="w-5 h-5 text-sky-600 shrink-0 mt-0.5" />,
    warning: <AlertTriangleIcon className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />,
  };

  return (
    <div
      role="alert"
      className={`rounded-xl border p-4 text-sm font-medium shadow-sm transition-all flex items-start gap-3 ${styles[kind] ?? styles.error}`}
    >
      {icons[kind] ?? icons.error}
      <div className="flex-1 leading-relaxed">{children}</div>
    </div>
  );
}

/** A small spinning circle for "working on it". */
export function Spinner({ label = "Loading…" }) {
  return (
    <span className="inline-flex items-center gap-2.5 text-sm font-medium text-stone-600">
      <span
        aria-hidden="true"
        className="h-4 w-4 animate-spin rounded-full border-2 border-stone-300 border-t-amber-600"
      />
      {label}
    </span>
  );
}

/** A polished modern white panel card. */
export function Card({ children, className = "" }) {
  return (
    <div
      className={`rounded-2xl border border-stone-200/80 bg-white/95 p-6 shadow-sm hover:shadow-md transition-all duration-200 backdrop-blur-sm ${className}`}
    >
      {children}
    </div>
  );
}

/** A labelled form field, with room for a per-field error message. */
export function Field({ label, htmlFor, error, hint, children }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block text-xs font-semibold uppercase tracking-wider text-stone-600">
        {label}
      </label>
      {children}
      {hint && !error && <p className="text-xs text-stone-500 leading-normal">{hint}</p>}
      {error && <p className="text-xs font-medium text-red-600">{error}</p>}
    </div>
  );
}

/** Shared input styling. Spread onto an <input> or <select>. */
export const inputClass =
  "w-full rounded-xl border border-stone-200 bg-white px-3.5 py-2.5 text-sm text-stone-800 shadow-sm transition-all duration-150 " +
  "placeholder:text-stone-400 focus:border-amber-500 focus:outline-none focus:ring-4 focus:ring-amber-500/10 " +
  "disabled:bg-stone-100 disabled:text-stone-400";

/** Primary action button styling. */
export const buttonClass =
  "inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-amber-600 to-amber-700 hover:from-amber-500 hover:to-amber-600 px-5 py-2.5 " +
  "text-sm font-semibold text-white shadow-md shadow-amber-600/20 hover:shadow-lg hover:shadow-amber-600/30 transition-all duration-150 active:scale-[0.99] " +
  "disabled:cursor-not-allowed disabled:opacity-60 disabled:shadow-none disabled:active:scale-100";

/** Secondary action button styling. */
export const secondaryButtonClass =
  "inline-flex items-center justify-center gap-2 rounded-xl border border-stone-200 " +
  "bg-white px-5 py-2.5 text-sm font-semibold text-stone-700 shadow-sm hover:bg-stone-50 hover:border-stone-300 " +
  "transition-all duration-150 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-60";
