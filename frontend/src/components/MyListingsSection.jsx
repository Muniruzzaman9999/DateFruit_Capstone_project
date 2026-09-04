import { useCallback, useEffect, useMemo, useState } from "react";

import { api, errorMessage } from "../services/api";
import { ACCEPT_IMAGES, validateImageFile } from "../services/uploads";
import CategorySelect from "./CategorySelect";
import ListingCard from "./ListingCard";
import ListingFields from "./ListingFields";
import {
  CheckCircleIcon,
  FilterIcon,
  GridIcon,
  ListIcon,
  RefreshIcon,
  StoreIcon,
  TagIcon,
} from "./icons";
import {
  Alert,
  Card,
  Field,
  Spinner,
  buttonClass,
  inputClass,
  secondaryButtonClass,
} from "./ui";

function listingToForm(listing) {
  return {
    category_id: String(listing.category.id),
    price: String(Number(listing.price)),
    quantity: String(Number(listing.quantity)),
    unit: listing.unit,
    shop_name: listing.shop_name,
    contact_number: listing.contact_number,
    shop_location: listing.shop_location,
  };
}

function EditForm({ listing, categories, onCategoryCreated, onSaved, onCancel }) {
  const initial = useMemo(() => listingToForm(listing), [listing]);

  const [values, setValues] = useState(initial);
  const [newImage, setNewImage] = useState(null);
  const [imageError, setImageError] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const changedFields = Object.keys(initial).filter(
    (field) => values[field] !== initial[field]
  );
  const hasChanges = changedFields.length > 0 || newImage !== null;

  function handleImageChange(event) {
    const chosen = event.target.files?.[0];
    if (!chosen) {
      setNewImage(null);
      setImageError("");
      return;
    }

    const problem = validateImageFile(chosen);
    if (problem) {
      setNewImage(null);
      setImageError(problem);
      return;
    }
    setImageError("");
    setNewImage(chosen);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!hasChanges) {
      setError("Nothing has changed yet. Edit a field, then save.");
      return;
    }

    setError("");
    setSaving(true);

    try {
      const formData = new FormData();
      for (const field of changedFields) {
        formData.append(field, values[field]);
      }
      if (newImage) {
        formData.append("image", newImage);
      }

      const response = await api.patch(`/api/listings/${listing.id}`, formData);
      onSaved(response.data);
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not save those changes."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-4 space-y-4 rounded-2xl border border-amber-300/80 bg-gradient-to-br from-amber-50/70 to-orange-50/30 p-5 sm:p-6 shadow-md transition-all animate-fadeIn"
      noValidate
    >
      <div className="flex items-center justify-between border-b border-amber-200/80 pb-3">
        <h4 className="font-extrabold text-stone-900 text-base">
          ✏️ Edit Listing #{listing.id} ({listing.category.name})
        </h4>
        <button
          type="button"
          onClick={onCancel}
          className="text-xs font-bold text-stone-500 hover:text-stone-800"
        >
          Close Editor ✕
        </button>
      </div>

      <CategorySelect
        categories={categories}
        value={values.category_id}
        onChange={(id) => setValues((current) => ({ ...current, category_id: id }))}
        onCategoryCreated={onCategoryCreated}
        disabled={saving}
        label="Date Fruit Variety"
        id={`edit-category-${listing.id}`}
      />

      <ListingFields
        values={values}
        onChange={(field, value) =>
          setValues((current) => ({ ...current, [field]: value }))
        }
        disabled={saving}
        idPrefix={`edit-${listing.id}`}
      />

      <Field
        label="Replace Photograph (optional)"
        htmlFor={`edit-image-${listing.id}`}
        hint="Select a new photo to replace the existing one"
        error={imageError}
      >
        <input
          id={`edit-image-${listing.id}`}
          type="file"
          accept={ACCEPT_IMAGES}
          onChange={handleImageChange}
          className={`${inputClass} file:mr-3 file:rounded-lg file:border-0 file:bg-stone-200 file:px-3 file:py-1 file:text-xs file:font-semibold`}
          disabled={saving}
        />
      </Field>

      {error && <Alert kind="error">{error}</Alert>}

      <div className="flex flex-wrap items-center gap-3 pt-2">
        <button type="submit" className={buttonClass} disabled={saving || !hasChanges}>
          {saving ? <Spinner label="Saving changes…" /> : "Save Changes"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className={secondaryButtonClass}
          disabled={saving}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

export default function MyListingsSection({ categories, onCategoryCreated, onChanged }) {
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [filterStatus, setFilterStatus] = useState("ALL");
  const [viewMode, setViewMode] = useState("grid");
  const [editingId, setEditingId] = useState(null);
  const [workingId, setWorkingId] = useState(null);
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await api.get("/api/listings/mine");
      setListings(response.data.listings);
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not load your listings."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function replaceListing(updated) {
    setListings((current) =>
      current.map((item) => (item.id === updated.id ? updated : item))
    );
    onChanged?.();
  }

  async function changeStatus(listing, action) {
    if (action === "deactivate") {
      const confirmed = window.confirm(
        `Deactivate "${listing.category.name} at ${listing.shop_name}"?\n\n` +
          "It will be hidden from the public marketplace, but kept in your account to reactivate later."
      );
      if (!confirmed) return;
    }

    setWorkingId(listing.id);
    setError("");
    setNotice("");

    try {
      const response = await api.post(`/api/listings/${listing.id}/${action}`);
      replaceListing(response.data);
      setNotice(
        action === "deactivate"
          ? `"${response.data.category.name}" is now INACTIVE and hidden from public marketplace.`
          : `"${response.data.category.name}" is ACTIVE and back in live marketplace.`
      );
    } catch (requestError) {
      setError(errorMessage(requestError, `Could not ${action} that listing.`));
    } finally {
      setWorkingId(null);
    }
  }

  const activeCount = useMemo(
    () => listings.filter((item) => item.status === "ACTIVE").length,
    [listings]
  );
  const inactiveCount = listings.length - activeCount;

  const filteredListings = useMemo(() => {
    if (filterStatus === "ACTIVE") {
      return listings.filter((item) => item.status === "ACTIVE");
    }
    if (filterStatus === "INACTIVE") {
      return listings.filter((item) => item.status === "INACTIVE");
    }
    return listings;
  }, [listings, filterStatus]);

  return (
    <div className="space-y-6">
      {/* ================= Modern Header Banner ====================== */}
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-r from-stone-900 via-stone-800 to-amber-950 p-6 text-white shadow-xl">
        <div className="absolute -right-10 -bottom-10 w-48 h-48 rounded-full bg-amber-500/10 blur-2xl pointer-events-none" />
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/20 border border-amber-400/30 px-3 py-1 text-xs font-bold text-amber-300">
                <StoreIcon className="w-3.5 h-3.5" />
                Seller Inventory Dashboard
              </span>
            </div>
            <h2 className="text-2xl sm:text-3xl font-black tracking-tight">
              My Shop Listings
            </h2>
            <p className="mt-1 text-xs sm:text-sm text-stone-300 max-w-xl">
              Manage your published date fruit offers, update prices & photos, or pause items from the public marketplace.
            </p>
          </div>

          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="inline-flex items-center gap-2 self-start md:self-center rounded-2xl bg-white/10 hover:bg-white/20 backdrop-blur-md px-4 py-2 text-xs font-bold text-white border border-white/20 transition-all shadow-sm active:scale-95"
          >
            <RefreshIcon className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            Refresh Inventory
          </button>
        </div>
      </div>

      {/* ================= Quick Stats & Controls =================== */}
      <Card className="p-4 sm:p-5">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          {/* Status Filter Pills */}
          <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
            <button
              type="button"
              onClick={() => setFilterStatus("ALL")}
              className={`shrink-0 inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-xs font-extrabold transition-all ${
                filterStatus === "ALL"
                  ? "bg-amber-600 text-white shadow-md shadow-amber-600/20"
                  : "bg-stone-100 text-stone-700 hover:bg-stone-200"
              }`}
            >
              All Listings ({listings.length})
            </button>

            <button
              type="button"
              onClick={() => setFilterStatus("ACTIVE")}
              className={`shrink-0 inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-bold transition-all ${
                filterStatus === "ACTIVE"
                  ? "bg-emerald-600 text-white shadow-md shadow-emerald-600/20"
                  : "bg-stone-100 text-stone-700 hover:bg-stone-200"
              }`}
            >
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              Active ({activeCount})
            </button>

            <button
              type="button"
              onClick={() => setFilterStatus("INACTIVE")}
              className={`shrink-0 inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-bold transition-all ${
                filterStatus === "INACTIVE"
                  ? "bg-stone-700 text-white shadow-md"
                  : "bg-stone-100 text-stone-700 hover:bg-stone-200"
              }`}
            >
              <span className="w-2 h-2 rounded-full bg-stone-400" />
              Paused ({inactiveCount})
            </button>
          </div>

          {/* View Mode Toggle */}
          <div className="flex items-center gap-1.5 self-end md:self-auto">
            <button
              type="button"
              onClick={() => setViewMode("grid")}
              className={`p-2.5 rounded-xl border font-bold text-xs flex items-center gap-1.5 transition-all ${
                viewMode === "grid"
                  ? "bg-amber-600 text-white border-amber-600 shadow-md shadow-amber-600/20"
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
                  ? "bg-amber-600 text-white border-amber-600 shadow-md shadow-amber-600/20"
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
        {notice && (
          <div className="mt-4">
            <Alert kind="success">{notice}</Alert>
          </div>
        )}
      </Card>

      {/* ================= Listings List / Grid ===================== */}
      {loading ? (
        <div className="py-12 text-center">
          <Spinner label="Loading inventory listings…" />
        </div>
      ) : filteredListings.length === 0 ? (
        <Card className="text-center py-12">
          <p className="text-sm font-semibold text-stone-700">
            {listings.length === 0
              ? "You haven't created any shop listings yet."
              : `No ${filterStatus.toLowerCase()} listings found.`}
          </p>
          <p className="mt-1 text-xs text-stone-500">
            Publish your date fruit offers anytime from the <strong>Classify &amp; Publish</strong> tab!
          </p>
        </Card>
      ) : (
        <div
          className={
            viewMode === "grid"
              ? "grid gap-5 sm:grid-cols-2 lg:grid-cols-3"
              : "space-y-4 flex flex-col"
          }
        >
          {filteredListings.map((listing) => {
            const isActive = listing.status === "ACTIVE";
            const busy = workingId === listing.id;
            const isEditing = editingId === listing.id;

            return (
              <div key={listing.id} className="flex flex-col">
                <ListingCard
                  listing={listing}
                  showStatus
                  viewMode={viewMode}
                  hideCallButton
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setEditingId(isEditing ? null : listing.id)}
                      className="inline-flex items-center gap-1 rounded-xl bg-amber-100 hover:bg-amber-200 text-amber-900 text-xs font-bold px-3 py-1.5 transition-all border border-amber-300/80 active:scale-95"
                      disabled={busy}
                    >
                      ✏️ {isEditing ? "Close" : "Edit"}
                    </button>

                    {isActive ? (
                      <button
                        type="button"
                        onClick={() => changeStatus(listing, "deactivate")}
                        className="inline-flex items-center gap-1 rounded-xl bg-stone-100 hover:bg-stone-200 text-stone-700 text-xs font-bold px-3 py-1.5 transition-all border border-stone-300/80 active:scale-95"
                        disabled={busy}
                      >
                        {busy ? <Spinner label="Working…" /> : "⏸️ Pause"}
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => changeStatus(listing, "reactivate")}
                        className="inline-flex items-center gap-1 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold px-3 py-1.5 transition-all shadow-xs active:scale-95"
                        disabled={busy}
                      >
                        {busy ? <Spinner label="Working…" /> : "▶️ Reactivate"}
                      </button>
                    )}
                  </div>
                </ListingCard>

                {isEditing && (
                  <EditForm
                    listing={listing}
                    categories={categories}
                    onCategoryCreated={onCategoryCreated}
                    onSaved={(updated) => {
                      replaceListing(updated);
                      setEditingId(null);
                      setNotice(`Listing #${updated.id} updated successfully.`);
                    }}
                    onCancel={() => setEditingId(null)}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
