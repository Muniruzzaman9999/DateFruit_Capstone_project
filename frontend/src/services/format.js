/**
 * Turning the API's numbers into text a person can read.
 *
 * One thing to know before reading this file: **prices arrive as strings**, not
 * numbers - `"850.00"` rather than `850`. The backend does that on purpose.
 * Money in floating point goes wrong (in JavaScript, `0.1 + 0.2` is
 * `0.30000000000000004`), so the API sends exact decimal text and leaves the
 * rounding to the moment of display, which is here.
 *
 * So every function below calls `Number(...)` itself. Nothing else in the app
 * should be doing arithmetic on a price.
 */

/** The currency this marketplace prices in: Bangladeshi Taka. */
export const CURRENCY = "৳";

/**
 * A plain number, tidied for display.
 *
 * Whole numbers lose their decimals ("850", not "850.00") because that is how a
 * price is written on a shop sign. Anything with real decimals keeps two.
 */
function tidyNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  return Number.isInteger(number) ? String(number) : number.toFixed(2);
}

/** `"850.00"` becomes `"৳850"`. Returns null for anything unusable. */
export function formatTaka(value) {
  const tidy = tidyNumber(value);
  return tidy === null ? null : `${CURRENCY}${tidy}`;
}

/**
 * The price line on a listing card: `"৳850 / kg"` or `"৳180 / 200 gram"`.
 *
 * A quantity of 1 is left out, because "৳850 / 1 kg" reads worse than
 * "৳850 / kg" and means exactly the same thing.
 *
 * The seller's own unit is always what gets shown here. Statistics are worked
 * out per gram, but a listing published as "per kg" is never rewritten as a
 * per-gram price on its own card - that would misrepresent what is on offer.
 */
export function priceLabel(listing) {
  const price = formatTaka(listing.price);
  if (price === null) return "";

  const quantity = Number(listing.quantity);
  const amount = quantity === 1 ? listing.unit : `${tidyNumber(quantity)} ${listing.unit}`;
  return `${price} / ${amount}`;
}

/**
 * A per-gram figure: `"৳0.86 / gram"`.
 *
 * Two decimal places normally. But a genuinely tiny price - a cheap variety
 * sold in bulk might work out at ৳0.004 per gram - would round to "৳0.00" and
 * look like it was free, so those fall back to four decimals, which is the
 * precision the API sends.
 */
export function perGramLabel(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return null;

  const rounded = number.toFixed(2);
  const text = Number(rounded) === 0 && number !== 0 ? number.toFixed(4) : rounded;
  return `${CURRENCY}${text} / gram`;
}

/** `0.9421` becomes `"94%"`, for the confidence line under a prediction. */
export function confidencePercent(confidence) {
  return `${Math.round(Number(confidence) * 100)}%`;
}

/** A date the API sent, as a short readable line. */
export function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
