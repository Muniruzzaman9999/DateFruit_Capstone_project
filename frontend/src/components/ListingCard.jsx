import { imageUrl } from "../services/api";
import { perGramLabel, priceLabel } from "../services/format";
import { LocationIcon, PhoneIcon, ShieldCheckIcon, StoreIcon, UserIcon } from "./icons";

function DetailRow({ icon: Icon, children }) {
  return (
    <div className="flex items-center gap-1.5 text-xs text-stone-600">
      <Icon className="w-3.5 h-3.5 text-amber-600/70 shrink-0" />
      <span className="min-w-0 font-medium truncate text-stone-700">{children}</span>
    </div>
  );
}

function StatusBadge({ status }) {
  const active = status === "ACTIVE";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
        active
          ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
          : "bg-stone-100 text-stone-600 border border-stone-200"
      }`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${active ? "bg-emerald-500 animate-pulse" : "bg-stone-400"}`} />
      {status}
    </span>
  );
}

export default function ListingCard({
  listing,
  showStatus = false,
  highlight = false,
  badge = null,
  viewMode = "grid",
  hideCallButton = false,
  children = null,
}) {
  const photo = imageUrl(listing.image_url);
  const perGram = perGramLabel(listing.price_per_gram);

  const isGrid = viewMode === "grid";

  return (
    <div
      className={`group relative overflow-hidden rounded-2xl border transition-all duration-300 ${
        highlight
          ? "border-amber-400/90 bg-gradient-to-br from-amber-500/10 via-white to-amber-500/5 shadow-md hover:shadow-xl hover:border-amber-500"
          : "border-stone-200/90 bg-white shadow-xs hover:border-amber-400 hover:shadow-xl hover:-translate-y-0.5"
      }`}
    >
      <div
        className={`flex ${
          isGrid ? "flex-col" : "flex-col sm:flex-row"
        } gap-4 p-4 sm:p-5`}
      >
        {/* --- Image Container ------------------------------------------ */}
        <div
          className={`relative shrink-0 overflow-hidden rounded-xl bg-stone-100/80 ${
            isGrid ? "h-48 w-full" : "h-48 w-full sm:h-36 sm:w-36"
          }`}
        >
          {photo ? (
            <img
              src={photo}
              alt={`${listing.category.name} dates from ${listing.shop_name}`}
              loading="lazy"
              className="h-full w-full object-cover group-hover:scale-108 transition-transform duration-500 ease-out"
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center bg-stone-100 text-xs font-medium text-stone-400">
              No Photo
            </div>
          )}

          {/* AI Verification Badge */}
          <div className="absolute top-2 left-2 z-10 flex flex-col gap-1">
            {badge}
            <span className="inline-flex items-center gap-1 rounded-full bg-stone-900/80 backdrop-blur-md px-2 py-0.5 text-[9px] font-semibold text-amber-300 border border-amber-500/30">
              <ShieldCheckIcon className="w-3 h-3 text-emerald-400" />
              AI Verified
            </span>
          </div>
        </div>

        {/* --- Details Content ------------------------------------------ */}
        <div className="min-w-0 flex-1 flex flex-col justify-between space-y-3">
          <div>
            <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-amber-900 bg-amber-100/90 border border-amber-300/60 px-2.5 py-0.5 rounded-md">
                  {listing.category.name}
                </span>
                {showStatus && <StatusBadge status={listing.status} />}
              </div>
              <span className="text-[11px] text-stone-400 font-mono">
                #{listing.id}
              </span>
            </div>

            <div className="flex flex-wrap items-baseline gap-2.5 mt-2">
              <h4 className="text-2xl font-black text-stone-900 tracking-tight">
                {priceLabel(listing)}
              </h4>
              {perGram && (
                <span className="inline-flex items-center gap-1 rounded-lg bg-emerald-50 px-2.5 py-1 text-xs font-bold text-emerald-800 border border-emerald-200/80 shadow-2xs">
                  ⚡ {perGram}
                </span>
              )}
            </div>

            {!perGram && (
              <p className="text-[11px] text-stone-400 mt-1 italic">
                Priced per piece (excluded from gram averages)
              </p>
            )}
          </div>

          {/* Shop & Contact Information Bar */}
          <div className="grid gap-2 sm:grid-cols-2 pt-3 border-t border-stone-100">
            <DetailRow icon={StoreIcon}>{listing.shop_name}</DetailRow>
            <DetailRow icon={LocationIcon}>{listing.shop_location}</DetailRow>
            <DetailRow icon={PhoneIcon}>
              <a
                href={`tel:${listing.contact_number}`}
                className="font-semibold text-stone-800 hover:text-amber-700 hover:underline transition-colors"
              >
                {listing.contact_number}
              </a>
            </DetailRow>
            <DetailRow icon={UserIcon}>Posted by {listing.posted_by.name}</DetailRow>
          </div>

          {/* Action Row */}
          <div className="pt-2 flex flex-wrap items-center justify-between gap-2">
            {!hideCallButton ? (
              <a
                href={`tel:${listing.contact_number}`}
                className="inline-flex items-center gap-1.5 rounded-xl bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold px-3.5 py-1.5 transition-all shadow-xs hover:shadow-md active:scale-95"
              >
                <PhoneIcon className="w-3.5 h-3.5" />
                Call Seller
              </a>
            ) : <div />}
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}
