import { useCallback, useEffect, useMemo, useState } from "react";

import { api, errorMessage } from "../services/api";
import { perGramLabel } from "../services/format";
import ListingCard from "./ListingCard";
import {
  FilterIcon,
  GridIcon,
  ListIcon,
  RefreshIcon,
  SearchIcon,
  ShieldCheckIcon,
  StoreIcon,
  TagIcon,
  TrendingUpIcon,
  TrophyIcon,
} from "./icons";
import { Alert, Card, Spinner } from "./ui";

const SORTS = [
  { value: "price", label: "Price: Low to High 💰" },
  { value: "price_desc", label: "Price: High to Low 🏷️" },
  { value: "price_per_gram", label: "Best Value per Gram (Lowest ৳/g) ⚡" },
  { value: "newest", label: "Newest Listings First ⏱️" },
];

function StatPanel({ title, icon: Icon, children, tone = "default" }) {
  const tones = {
    default:
      "border-stone-200/90 bg-white/95 text-stone-800 hover:border-amber-300 shadow-xs hover:shadow-md transition-all duration-300",
    best: "border-amber-300/90 bg-gradient-to-br from-amber-500/15 via-amber-500/5 to-emerald-500/10 text-stone-900 shadow-md hover:shadow-lg transition-all duration-300",
  };
  return (
    <div className={`rounded-2xl border p-5 transition-all ${tones[tone] ?? tones.default}`}>
      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-stone-500 mb-2">
        {Icon && <Icon className="w-4 h-4 text-amber-600 shrink-0" />}
        <span>{title}</span>
      </div>
      <div>{children}</div>
    </div>
  );
}

export default function MarketplaceSection({ categories }) {
  const [categoryId, setCategoryId] = useState("");
  const [sort, setSort] = useState("price");
  const [searchQuery, setSearchQuery] = useState("");
  const [viewMode, setViewMode] = useState("grid");

  const [listings, setListings] = useState([]);
  const [total, setTotal] = useState(0);
  const [categoryStats, setCategoryStats] = useState(null);
  const [bestPrice, setBestPrice] = useState(null);
  const [globalStats, setGlobalStats] = useState(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    const wantsCategory = categoryId !== "";

    try {
      const [listingsResponse, globalResponse, statsResponse, bestResponse] =
        await Promise.all([
          api.get("/api/marketplace/listings", {
            params: {
              category_id: wantsCategory ? categoryId : undefined,
              sort,
            },
          }),
          api.get("/api/categories/statistics"),
          wantsCategory ? api.get(`/api/categories/${categoryId}/stats`) : null,
          wantsCategory
            ? api.get("/api/marketplace/best-price", {
                params: { category_id: categoryId },
              })
            : null,
        ]);

      setListings(listingsResponse.data.listings);
      setTotal(listingsResponse.data.total);
      setGlobalStats(globalResponse.data);
      setCategoryStats(statsResponse ? statsResponse.data : null);
      setBestPrice(bestResponse ? bestResponse.data : null);
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not load the marketplace."));
    } finally {
      setLoading(false);
    }
  }, [categoryId, sort]);

  useEffect(() => {
    load();
  }, [load]);

  // Client-side search filtering by shop name, location, contact or category
  const filteredListings = useMemo(() => {
    if (!searchQuery.trim()) return listings;
    const q = searchQuery.toLowerCase().trim();
    return listings.filter(
      (item) =>
        item.shop_name?.toLowerCase().includes(q) ||
        item.shop_location?.toLowerCase().includes(q) ||
        item.category?.name?.toLowerCase().includes(q) ||
        item.contact_number?.includes(q) ||
        item.posted_by?.name?.toLowerCase().includes(q)
    );
  }, [listings, searchQuery]);

  const best = globalStats?.best_average_price ?? null;

  return (
    <div className="space-y-6">
      {/* ================= Modern Header Banner ====================== */}
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-r from-amber-700 via-amber-600 to-amber-800 p-6 text-white shadow-xl">
        <div className="absolute -right-10 -bottom-10 w-48 h-48 rounded-full bg-amber-400/20 blur-2xl pointer-events-none" />
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <span className="inline-flex items-center gap-1 rounded-full bg-white/20 backdrop-blur-md px-3 py-1 text-xs font-bold text-amber-100">
                <StoreIcon className="w-3.5 h-3.5 text-amber-200" />
                Live Date Fruit Marketplace
              </span>
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/30 backdrop-blur-md px-3 py-1 text-xs font-bold text-emerald-200 border border-emerald-400/40">
                <ShieldCheckIcon className="w-3.5 h-3.5" />
                AI Verified Prices
              </span>
            </div>
            <h2 className="text-2xl sm:text-3xl font-black tracking-tight">
              Compare Market Prices & Deals
            </h2>
            <p className="mt-1 text-xs sm:text-sm text-amber-100/90 max-w-xl">
              Discover verified date fruit shop listings, compare price per gram averages, and find the best local shop deals in real-time.
            </p>
          </div>

          <div className="flex items-center gap-3 self-start md:self-center">
            <button
              type="button"
              onClick={load}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-2xl bg-white/10 hover:bg-white/20 backdrop-blur-md px-4 py-2 text-xs font-bold text-white border border-white/20 transition-all shadow-sm active:scale-95"
            >
              <RefreshIcon className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </button>
          </div>
        </div>
      </div>

      {/* ================= Variety Filter Pills Bar ================== */}
      <div className="flex items-center gap-2 overflow-x-auto pb-2 scrollbar-none">
        <button
          type="button"
          onClick={() => setCategoryId("")}
          className={`shrink-0 inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-xs font-extrabold transition-all ${
            categoryId === ""
              ? "bg-amber-600 text-white shadow-md shadow-amber-600/20"
              : "bg-white text-stone-700 hover:bg-amber-50 border border-stone-200"
          }`}
        >
          <TagIcon className="w-3.5 h-3.5" />
          All Varieties ({total})
        </button>

        {categories.map((cat) => {
          const isSelected = categoryId === String(cat.id);
          return (
            <button
              key={cat.id}
              type="button"
              onClick={() => setCategoryId(String(cat.id))}
              className={`shrink-0 inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-bold transition-all ${
                isSelected
                  ? "bg-amber-600 text-white shadow-md shadow-amber-600/20"
                  : "bg-white text-stone-700 hover:bg-amber-50 border border-stone-200"
              }`}
            >
              {cat.name}
            </button>
          );
        })}
      </div>

      {/* ================= Search & Filter Control Bar =============== */}
      <Card className="p-4 sm:p-5">
        <div className="grid gap-4 md:grid-cols-12 items-center">
          {/* Search Input Box */}
          <div className="md:col-span-5 relative">
            <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-stone-400">
              <SearchIcon className="w-4 h-4" />
            </div>
            <input
              type="text"
              placeholder="Search by shop name, location, variety or contact..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 bg-stone-50 hover:bg-stone-100/80 focus:bg-white text-xs font-medium text-stone-800 rounded-xl border border-stone-200 focus:border-amber-500 focus:ring-2 focus:ring-amber-500/20 transition-all outline-none"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className="absolute inset-y-0 right-0 pr-3 flex items-center text-stone-400 hover:text-stone-600 text-xs font-bold"
              >
                Clear
              </button>
            )}
          </div>

          {/* Sort Selector Dropdown */}
          <div className="md:col-span-5 flex items-center gap-2">
            <FilterIcon className="w-4 h-4 text-stone-400 shrink-0 hidden sm:block" />
            <select
              id="market-sort"
              className="w-full bg-stone-50 hover:bg-stone-100/80 focus:bg-white text-xs font-semibold text-stone-800 rounded-xl border border-stone-200 py-2.5 px-3 focus:border-amber-500 focus:ring-2 focus:ring-amber-500/20 transition-all outline-none cursor-pointer"
              value={sort}
              onChange={(event) => setSort(event.target.value)}
              disabled={loading}
            >
              {SORTS.map((option) => (
                <option key={option.value} value={option.value}>
                  Sort: {option.label}
                </option>
              ))}
            </select>
          </div>

          {/* View Toggle Buttons */}
          <div className="md:col-span-2 flex items-center justify-end gap-1.5">
            <button
              type="button"
              onClick={() => setViewMode("grid")}
              className={`p-2.5 rounded-xl border font-bold text-xs flex items-center gap-1.5 transition-all ${
                viewMode === "grid"
                  ? "bg-amber-600 text-white border-amber-600 shadow-md shadow-amber-600/20 ring-2 ring-amber-500/30"
                  : "bg-white text-stone-600 border-stone-200 hover:bg-stone-50"
              }`}
              title="Grid View"
            >
              <GridIcon className="w-4 h-4" />
              <span className="hidden sm:inline">Grid</span>
            </button>
            <button
              type="button"
              onClick={() => setViewMode("list")}
              className={`p-2.5 rounded-xl border font-bold text-xs flex items-center gap-1.5 transition-all ${
                viewMode === "list"
                  ? "bg-amber-600 text-white border-amber-600 shadow-md shadow-amber-600/20 ring-2 ring-amber-500/30"
                  : "bg-white text-stone-600 border-stone-200 hover:bg-stone-50"
              }`}
              title="List View"
            >
              <ListIcon className="w-4 h-4" />
              <span className="hidden sm:inline">List</span>
            </button>
          </div>
        </div>

        {error && (
          <div className="mt-4">
            <Alert kind="error">{error}</Alert>
          </div>
        )}
      </Card>

      {/* ================= Market Statistics Dashboard ================ */}
      <div className="grid gap-4 lg:grid-cols-3">
        {/* --- Average Market Price Card --------------------- */}
        <StatPanel title="Average Market Price" icon={TrendingUpIcon}>
          {categoryStats === null ? (
            <p className="text-xs text-stone-500">
              Select a date variety above to view real-time average price per gram.
            </p>
          ) : categoryStats.average_price_per_gram === null ? (
            <div>
              <p className="text-sm font-semibold text-stone-700">
                No gram-based data available
              </p>
              <p className="mt-1 text-xs text-stone-500">{categoryStats.message}</p>
            </div>
          ) : (
            <div>
              <p className="text-3xl font-black text-amber-700 tracking-tight">
                {perGramLabel(categoryStats.average_price_per_gram)}
              </p>
              <p className="text-xs font-bold text-stone-800 mt-1">
                {categoryStats.category} Date Variety
              </p>
              <p className="mt-2 text-[11px] text-stone-500">
                Averaged across {categoryStats.listing_count} verified weight listing(s).
              </p>
            </div>
          )}
        </StatPanel>

        {/* --- Lowest Offer Card ---------------------------- */}
        <StatPanel title="Cheapest Single Deal" icon={StoreIcon}>
          {bestPrice === null ? (
            <p className="text-xs text-stone-500">
              Select a date variety to find the lowest cost shop offer.
            </p>
          ) : bestPrice.listing === null ? (
            <p className="text-xs text-stone-600">{bestPrice.message}</p>
          ) : (
            <div>
              <p className="text-3xl font-black text-emerald-700 tracking-tight">
                {perGramLabel(bestPrice.listing.price_per_gram)}
              </p>
              <p className="text-xs font-bold text-stone-900 mt-1 truncate">
                {bestPrice.listing.shop_name} &middot; {bestPrice.category.name}
              </p>
              <p className="mt-2 text-[11px] text-stone-500">
                Normalized per gram for instant cost comparison.
              </p>
            </div>
          )}
        </StatPanel>

        {/* --- Best Overall Average Card -------------------- */}
        <StatPanel title="Best Average Price Overall" icon={TrophyIcon} tone="best">
          {best === null ? (
            <p className="text-xs text-stone-600">
              No category has comparable price data yet.
            </p>
          ) : (
            <div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-extrabold text-amber-900 bg-amber-200/90 border border-amber-300 px-2.5 py-0.5 rounded-md">
                  {best.category}
                </span>
                <span className="text-[10px] font-bold text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded-md border border-emerald-200">
                  🏆 Lowest Market Avg
                </span>
              </div>
              <p className="text-3xl font-black text-amber-800 tracking-tight mt-1.5">
                {perGramLabel(best.average_price_per_gram)}
              </p>
              <p className="mt-2 text-[11px] text-stone-600 font-medium">
                Lowest overall average across {best.listing_count} verified listing(s).
              </p>
            </div>
          )}
        </StatPanel>
      </div>

      {/* ================= Category Price Index Table ================= */}
      {globalStats && globalStats.categories.length > 0 && (
        <Card className="p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
            <div>
              <h3 className="text-base font-extrabold text-stone-900 tracking-tight">
                Category Price Index
              </h3>
              <p className="text-xs text-stone-500">
                Sorted by lowest average price per gram across active marketplace listings.
              </p>
            </div>
          </div>

          <div className="overflow-x-auto rounded-2xl border border-stone-200/80">
            <table className="w-full text-xs text-left">
              <thead className="bg-stone-100/90 text-stone-700 font-bold border-b border-stone-200">
                <tr>
                  <th className="py-3 px-4">Date Variety</th>
                  <th className="py-3 px-4">Average Price / Gram</th>
                  <th className="py-3 px-4">Listings Averaged</th>
                  <th className="py-3 px-4">Active Listings</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100 bg-white">
                {globalStats.categories.map((row, index) => (
                  <tr
                    key={row.category_id}
                    className={`hover:bg-amber-50/50 transition-colors ${
                      index === 0 ? "bg-amber-50/70 font-semibold" : ""
                    }`}
                  >
                    <td className="py-3.5 px-4 flex items-center gap-2">
                      <span className="font-extrabold text-stone-800">{row.category}</span>
                      {index === 0 && (
                        <span className="rounded-full bg-amber-200/90 px-2 py-0.5 text-[10px] font-extrabold text-amber-900 border border-amber-300">
                          🏆 Best Value
                        </span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 font-black text-amber-700">
                      {perGramLabel(row.average_price_per_gram)}
                    </td>
                    <td className="py-3.5 px-4 text-stone-600 font-medium">{row.listing_count}</td>
                    <td className="py-3.5 px-4 text-stone-600 font-medium">{row.active_listing_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* ================= Live Listings Grid / List ================== */}
      <section className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <h3 className="text-xl font-black text-stone-900 tracking-tight">
              Live Market Listings
            </h3>
            {categoryStats && (
              <span className="text-xs font-bold text-amber-900 bg-amber-100 border border-amber-200 px-2.5 py-0.5 rounded-full">
                {categoryStats.category}
              </span>
            )}
          </div>
          <span className="text-xs font-semibold text-stone-500">
            {filteredListings.length === 0
              ? "No matching listings"
              : `Showing ${filteredListings.length} of ${total} active listing${total === 1 ? "" : "s"} (${viewMode.toUpperCase()} VIEW)`}
          </span>
        </div>

        {loading ? (
          <div className="py-12 text-center">
            <Spinner label="Loading live marketplace deals..." />
          </div>
        ) : filteredListings.length === 0 ? (
          <Card className="text-center py-12">
            <p className="text-sm font-semibold text-stone-700">
              {searchQuery
                ? `No marketplace listings found matching "${searchQuery}"`
                : categoryId === ""
                ? "No active listings yet. Be the first to publish one from Classify & Publish!"
                : "No active listings in this date category yet."}
            </p>
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className="mt-3 inline-flex items-center gap-1 text-xs font-bold text-amber-700 hover:underline"
              >
                Clear search filter
              </button>
            )}
          </Card>
        ) : (
          <div className={viewMode === "grid" ? "grid gap-5 sm:grid-cols-2 lg:grid-cols-3" : "space-y-4 flex flex-col"}>
            {filteredListings.map((listing, index) => (
              <ListingCard
                key={listing.id}
                listing={listing}
                viewMode={viewMode}
                highlight={index === 0 && categoryId !== ""}
                badge={
                  index === 0 && categoryId !== "" ? (
                    <span className="rounded-full bg-emerald-600 px-2.5 py-0.5 text-[10px] font-extrabold text-white shadow-xs border border-emerald-400">
                      🏆 Lowest Price
                    </span>
                  ) : null
                }
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
