import { useCallback, useEffect, useState } from "react";

import ClassifySection from "../components/ClassifySection";
import MarketplaceSection from "../components/MarketplaceSection";
import MyListingsSection from "../components/MyListingsSection";
import { SparklesIcon, StoreIcon, TagIcon } from "../components/icons";
import { Alert, Card, Spinner } from "../components/ui";
import { useAuth } from "../context/useAuth";
import { api, errorMessage } from "../services/api";

const TABS = [
  { id: "classify", label: "Classify & Publish", icon: SparklesIcon },
  { id: "marketplace", label: "Marketplace", icon: StoreIcon },
  { id: "mine", label: "My Listings", icon: TagIcon },
];

export default function AppPage() {
  const { user } = useAuth();

  const [tab, setTab] = useState("classify");

  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modelLoaded, setModelLoaded] = useState(true);

  const loadCategories = useCallback(async () => {
    try {
      const response = await api.get("/api/categories");
      setCategories(response.data.categories);
      setError("");
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not load the date-fruit categories."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCategories();
  }, [loadCategories]);

  useEffect(() => {
    api
      .get("/api/health")
      .then((response) => setModelLoaded(response.data.model_loaded))
      .catch(() => {});
  }, []);

  return (
    <div className="space-y-6">
      {/* --- Welcome Hero Card ---------------------------------------- */}
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-r from-amber-700 via-amber-600 to-emerald-700 p-6 sm:p-8 text-white shadow-xl shadow-amber-900/10">
        <div className="relative z-10 max-w-2xl">
          <div className="inline-flex items-center gap-2 rounded-full bg-white/20 px-3 py-1 text-xs font-semibold backdrop-blur-md mb-3">
            <SparklesIcon className="w-4 h-4 text-amber-200" />
            AI-Powered Date Classification
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight">
            Welcome, {user?.name ?? "Trader"} 👋
          </h1>
          <p className="mt-2 text-sm sm:text-base text-amber-100/90 font-medium leading-relaxed">
            Upload a date fruit photo for instant AI variety recognition, publish live shop prices, or analyze market deals per gram.
          </p>
        </div>
        {/* Background decorative element */}
        <div className="absolute -right-8 -bottom-10 h-48 w-48 rounded-full bg-white/10 blur-2xl pointer-events-none" />
      </div>

      {/* --- Interactive Tab Switcher ---------------------------------- */}
      <div className="flex rounded-2xl bg-stone-200/60 p-1.5 backdrop-blur-xs">
        {TABS.map((item) => {
          const selected = tab === item.id;
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => setTab(item.id)}
              className={`flex-1 flex items-center justify-center gap-2 rounded-xl py-3 px-4 text-sm font-semibold transition-all duration-200 ${
                selected
                  ? "bg-white text-amber-900 shadow-md shadow-stone-900/5 font-bold"
                  : "text-stone-600 hover:text-stone-900 hover:bg-white/50"
              }`}
            >
              <Icon className={`w-4 h-4 ${selected ? "text-amber-600" : "text-stone-500"}`} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>

      {error && <Alert kind="error">{error}</Alert>}

      {!modelLoaded && (
        <Alert kind="warning">
          The classification model is not loaded on the server, so classifying an
          image will fail. Check the backend logs and{" "}
          <code className="font-mono">GET /api/health</code>. You can still publish
          listings by choosing a category yourself.
        </Alert>
      )}

      {loading ? (
        <Card className="flex items-center justify-center py-12">
          <Spinner label="Loading categories & market data…" />
        </Card>
      ) : (
        <>
          {tab === "classify" && (
            <ClassifySection
              categories={categories}
              onCategoryCreated={loadCategories}
              onPublished={loadCategories}
            />
          )}

          {tab === "marketplace" && <MarketplaceSection categories={categories} />}

          {tab === "mine" && (
            <MyListingsSection
              categories={categories}
              onCategoryCreated={loadCategories}
              onChanged={loadCategories}
            />
          )}
        </>
      )}
    </div>
  );
}
