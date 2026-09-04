import { useEffect, useMemo, useState } from "react";

import { api, errorMessage } from "../services/api";
import { confidencePercent } from "../services/format";
import { ACCEPT_IMAGES, validateImageFile } from "../services/uploads";
import CategorySelect from "./CategorySelect";
import ListingFields from "./ListingFields";
import {
  AlertTriangleIcon,
  CameraIcon,
  CheckCircleIcon,
  CloseIcon,
  RefreshIcon,
  SparklesIcon,
  TagIcon,
  UploadIcon,
} from "./icons";
import {
  Alert,
  Card,
  Spinner,
  buttonClass,
  secondaryButtonClass,
} from "./ui";

const EMPTY_DETAILS = {
  price: "",
  quantity: "1",
  unit: "kg",
  shop_name: "",
  contact_number: "",
  shop_location: "",
};

export default function ClassifySection({ categories, onCategoryCreated, onPublished }) {
  const [file, setFile] = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [classifying, setClassifying] = useState(false);

  const [categoryId, setCategoryId] = useState("");
  const [correcting, setCorrecting] = useState(false);
  const [resolving, setResolving] = useState(false);

  const [details, setDetails] = useState(EMPTY_DETAILS);
  const [publishing, setPublishing] = useState(false);

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [dragActive, setDragActive] = useState(false);

  const previewUrl = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);

  useEffect(() => {
    if (!previewUrl) return;
    return () => URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  const selectedCategory = categories.find(
    (category) => String(category.id) === String(categoryId)
  );

  function resetPhoto() {
    setFile(null);
    setPrediction(null);
    setCategoryId("");
    setCorrecting(false);
    setError("");
  }

  function handleFileSelected(chosen) {
    if (!chosen) return;
    setSuccess("");
    const problem = validateImageFile(chosen);
    if (problem) {
      resetPhoto();
      setError(problem);
      return;
    }
    resetPhoto();
    setFile(chosen);
  }

  function handleFileChange(event) {
    const chosen = event.target.files?.[0];
    handleFileSelected(chosen);
  }

  function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(true);
  }

  function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
  }

  function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  }

  async function handleClassify() {
    if (!file) return;

    setError("");
    setSuccess("");
    setPrediction(null);
    setCategoryId("");
    setCorrecting(false);
    setClassifying(true);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await api.post("/api/ml/predict", formData);
      setPrediction(response.data);
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not classify that image."));
    } finally {
      setClassifying(false);
    }
  }

  async function handleConfirm() {
    // Strictly prevent confirming if non-date fruit
    if (prediction && prediction.is_date_fruit === false) {
      setError(prediction.message || "This is not a date fruit! Only date fruits can be published.");
      return;
    }

    const name = prediction?.prediction;
    if (!name) return;

    const match = categories.find((category) => category.name === name);
    if (match) {
      setCategoryId(String(match.id));
      setCorrecting(false);
      return;
    }

    setResolving(true);
    setError("");
    try {
      const response = await api.post("/api/categories", { name });
      onCategoryCreated?.(response.data);
      setCategoryId(String(response.data.id));
      setCorrecting(false);
    } catch (requestError) {
      setError(errorMessage(requestError, `Could not select the category ${name}.`));
    } finally {
      setResolving(false);
    }
  }

  async function handlePublish(event) {
    event.preventDefault();

    if (!file || !categoryId) return;

    // Strict validation check before publishing
    if (prediction && prediction.is_date_fruit === false) {
      setError(prediction.message || "Cannot publish non-date fruit items!");
      return;
    }

    setError("");
    setSuccess("");
    setPublishing(true);

    try {
      const formData = new FormData();
      formData.append("image", file);
      formData.append("category_id", categoryId);
      formData.append("price", details.price);
      formData.append("quantity", details.quantity);
      formData.append("unit", details.unit);
      formData.append("shop_name", details.shop_name);
      formData.append("contact_number", details.contact_number);
      formData.append("shop_location", details.shop_location);

      const response = await api.post("/api/listings", formData);

      setSuccess(
        `Published: ${response.data.category.name} at ${response.data.shop_name}. ` +
          `It is now visible to everyone in the marketplace.`
      );

      resetPhoto();
      setDetails((current) => ({
        ...EMPTY_DETAILS,
        shop_name: current.shop_name,
        contact_number: current.contact_number,
        shop_location: current.shop_location,
      }));

      onPublished?.();
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not publish that listing."));
    } finally {
      setPublishing(false);
    }
  }

  const busy = classifying || publishing || resolving;
  const confidenceScore = prediction?.confidence ? Math.round(prediction.confidence * 100) : 0;

  // Calculate current active step (1, 2, or 3)
  const currentStep = useMemo(() => {
    if (!file) return 1;
    if (!categoryId) return 2;
    return 3;
  }, [file, categoryId]);

  return (
    <div className="space-y-6">
      {/* ================= Step Indicator Progress Bar ==================== */}
      <div className="rounded-2xl border border-stone-200/80 bg-white p-4 shadow-xs">
        <div className="grid grid-cols-3 gap-2 text-center">
          <div
            className={`flex flex-col items-center gap-1 p-2 rounded-xl transition-all ${
              currentStep === 1
                ? "bg-amber-100/90 text-amber-900 font-extrabold border border-amber-300"
                : currentStep > 1
                ? "bg-emerald-50 text-emerald-800 font-bold"
                : "text-stone-400 font-medium"
            }`}
          >
            <span className="text-xs">Step 1</span>
            <span className="text-xs sm:text-sm">📸 Upload Photo</span>
          </div>

          <div
            className={`flex flex-col items-center gap-1 p-2 rounded-xl transition-all ${
              currentStep === 2
                ? "bg-amber-100/90 text-amber-900 font-extrabold border border-amber-300"
                : currentStep > 2
                ? "bg-emerald-50 text-emerald-800 font-bold"
                : "text-stone-400 font-medium"
            }`}
          >
            <span className="text-xs">Step 2</span>
            <span className="text-xs sm:text-sm">🤖 AI Recognition</span>
          </div>

          <div
            className={`flex flex-col items-center gap-1 p-2 rounded-xl transition-all ${
              currentStep === 3
                ? "bg-amber-100/90 text-amber-900 font-extrabold border border-amber-300"
                : "text-stone-400 font-medium"
            }`}
          >
            <span className="text-xs">Step 3</span>
            <span className="text-xs sm:text-sm">🏷️ Publish Deal</span>
          </div>
        </div>
      </div>

      {/* ================= 1. Upload & AI Classification Panel ========================== */}
      <Card className="border-stone-200/90">
        <div className="flex items-center gap-2 mb-1">
          <SparklesIcon className="w-5 h-5 text-amber-600" />
          <h2 className="text-lg font-black text-stone-900">AI Variety Classifier</h2>
        </div>
        <p className="text-xs text-stone-500 mb-5">
          Select or drop a clear date-fruit photograph (JPG, PNG, WEBP max 5MB). Only date fruits are accepted for publishing.
        </p>

        {!file ? (
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`relative rounded-2xl border-2 border-dashed p-8 text-center transition-all ${
              dragActive
                ? "border-amber-500 bg-amber-50/80 scale-[1.01]"
                : "border-stone-200 bg-stone-50/50 hover:border-amber-400 hover:bg-stone-50"
            }`}
          >
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-100/80 text-amber-700 mb-3 shadow-inner">
              <UploadIcon className="w-7 h-7" />
            </div>
            <p className="text-sm font-bold text-stone-800">
              Drag &amp; drop your date fruit photo here
            </p>
            <p className="text-xs text-stone-500 mt-1">or browse from your device gallery</p>

            <div className="mt-5 flex flex-wrap justify-center gap-3">
              <label className={buttonClass + " cursor-pointer"}>
                <UploadIcon className="w-4 h-4" />
                Browse Photo
                <input
                  type="file"
                  accept={ACCEPT_IMAGES}
                  onChange={handleFileChange}
                  className="hidden"
                  disabled={busy}
                />
              </label>

              <label className={secondaryButtonClass + " cursor-pointer"}>
                <CameraIcon className="w-4 h-4 text-stone-600" />
                Use Camera
                <input
                  type="file"
                  accept="image/*"
                  capture="environment"
                  onChange={handleFileChange}
                  className="hidden"
                  disabled={busy}
                />
              </label>
            </div>
          </div>
        ) : (
          <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
            <div className="flex flex-col sm:flex-row items-center gap-4">
              <div className="relative group shrink-0">
                <img
                  src={previewUrl}
                  alt="Selected date fruit preview"
                  className="h-36 w-36 rounded-xl border border-stone-200 object-cover shadow-sm"
                />
                <button
                  type="button"
                  onClick={resetPhoto}
                  className="absolute -top-2 -right-2 flex h-7 w-7 items-center justify-center rounded-full bg-stone-900 text-white shadow-md hover:bg-red-600 transition"
                  title="Remove image"
                >
                  <CloseIcon className="w-4 h-4" />
                </button>
              </div>

              <div className="flex-1 space-y-2 text-center sm:text-left">
                <div className="inline-flex items-center gap-1.5 rounded-md bg-stone-200/80 px-2.5 py-1 text-xs font-mono font-medium text-stone-700">
                  📷 {file?.name} &middot; {(file?.size / 1024).toFixed(0)} KB
                </div>

                <p className="text-xs text-stone-500">
                  Ready for AI recognition. Click <strong className="text-stone-800">Classify Photo</strong> below to process.
                </p>

                <div className="pt-2 flex flex-wrap gap-2 justify-center sm:justify-start">
                  <button
                    type="button"
                    onClick={handleClassify}
                    className={buttonClass}
                    disabled={busy}
                  >
                    {classifying ? <Spinner label="Analyzing neural network…" /> : (
                      <>
                        <SparklesIcon className="w-4 h-4 text-white" />
                        Classify Photo
                      </>
                    )}
                  </button>

                  <button
                    type="button"
                    onClick={resetPhoto}
                    className={secondaryButtonClass}
                    disabled={busy}
                  >
                    Change Image
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="mt-4">
            <Alert kind="error">{error}</Alert>
          </div>
        )}
        {success && (
          <div className="mt-4">
            <Alert kind="success">{success}</Alert>
          </div>
        )}
      </Card>

      {/* ================= 2. AI Result Card ===================== */}
      {prediction && !categoryId && !correcting && (
        <Card className={`border-2 transition-all duration-300 ${
          prediction.is_date_fruit
            ? "border-emerald-500/30 bg-gradient-to-br from-white via-emerald-50/20 to-amber-50/20 shadow-md"
            : "border-red-500/80 bg-gradient-to-br from-red-50/80 via-white to-red-50/30 shadow-md"
        }`}>
          {prediction.is_date_fruit ? (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-stone-100 pb-3">
                <div className="inline-flex items-center gap-2 rounded-full bg-emerald-100 px-3.5 py-1 text-xs font-bold text-emerald-800 border border-emerald-300/60">
                  <CheckCircleIcon className="w-4 h-4 text-emerald-600 shrink-0" />
                  Date Fruit Verified
                </div>
                <span className="text-xs font-semibold text-stone-500">
                  Confidence Score: <strong className="text-emerald-700 font-mono">{confidencePercent(prediction.confidence)}</strong>
                </span>
              </div>

              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-stone-400">
                  AI Predicted Variety
                </p>
                <h3 className="text-3xl font-black text-stone-900 mt-0.5 tracking-tight">
                  {prediction.prediction}
                </h3>
              </div>

              {/* Visual confidence meter bar */}
              <div className="space-y-1 bg-stone-100/70 p-3 rounded-xl border border-stone-200/60">
                <div className="flex justify-between text-[11px] font-semibold text-stone-600">
                  <span>Confidence Level ({confidenceScore}%)</span>
                  <span className="text-emerald-700 font-mono">High Quality Match</span>
                </div>
                <div className="h-2.5 w-full rounded-full bg-stone-200 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-amber-500 to-emerald-500 transition-all duration-500"
                    style={{ width: `${Math.min(100, Math.max(10, confidenceScore))}%` }}
                  />
                </div>
              </div>

              <div className="flex flex-wrap gap-3 pt-2">
                <button
                  type="button"
                  onClick={handleConfirm}
                  className={buttonClass}
                  disabled={busy}
                >
                  {resolving ? <Spinner label="Setting category…" /> : (
                    <>
                      <CheckCircleIcon className="w-4 h-4" />
                      Confirm &amp; Set Price
                    </>
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setCorrecting(true);
                    setCategoryId("");
                  }}
                  className={secondaryButtonClass}
                  disabled={busy}
                >
                  Wrong variety? Choose manually
                </button>
              </div>
            </div>
          ) : (
            /* Strict Non-Date Rejection Display */
            <div className="space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-red-200 pb-3">
                <div className="inline-flex items-center gap-2 rounded-full bg-red-100 px-3.5 py-1 text-xs font-bold text-red-900 border border-red-300">
                  <AlertTriangleIcon className="w-4 h-4 text-red-700 shrink-0" />
                  Non-Date Fruit Image Rejected
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-semibold text-stone-500">Detection Confidence:</span>
                  <span className="rounded-md bg-red-200/90 px-2 py-0.5 text-xs font-mono font-bold text-red-950">
                    {confidencePercent(prediction.confidence)}
                  </span>
                </div>
              </div>

              <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
                <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-red-100 text-red-800 shadow-inner">
                  <AlertTriangleIcon className="w-7 h-7" />
                </div>
                <div className="space-y-1">
                  <h3 className="text-lg font-extrabold text-red-900 leading-snug">
                    {prediction.message || "This is not a date fruit! Please upload a date fruit only."}
                  </h3>
                  <p className="text-xs text-stone-700 font-medium leading-relaxed">
                    ⚠️ <strong>Publish Blocked:</strong> Only genuine date fruits (e.g. Ajwa, Medjool, Sokari, etc.) can be listed on this Date Fruit AI Marketplace. Non-date items cannot be published.
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-3 pt-3 border-t border-red-200">
                <button
                  type="button"
                  onClick={resetPhoto}
                  className={buttonClass + " bg-red-700 hover:bg-red-800 text-white"}
                  disabled={busy}
                >
                  <UploadIcon className="w-4 h-4" />
                  Upload Date Fruit Photo
                </button>
              </div>
            </div>
          )}
        </Card>
      )}

      {/* ================= 3. Manual Correction Category Selector (Only for date fruits) ====================== */}
      {correcting && !categoryId && prediction?.is_date_fruit !== false && (
        <Card className="border-2 border-amber-400/80 shadow-lg bg-white">
          <div className="flex items-center justify-between mb-2 pb-2 border-b border-stone-100">
            <div className="flex items-center gap-2">
              <TagIcon className="w-5 h-5 text-amber-600" />
              <h3 className="text-base font-bold text-stone-900">
                Select Date Fruit Variety
              </h3>
            </div>
            {prediction && (
              <button
                type="button"
                onClick={() => setCorrecting(false)}
                className="text-xs font-semibold text-stone-500 hover:text-stone-800"
              >
                Back to AI Result ✕
              </button>
            )}
          </div>
          <p className="text-xs text-stone-500 mb-4">
            Select an existing variety or add a custom variety name to proceed with publishing your listing.
          </p>

          <CategorySelect
            categories={categories}
            value={categoryId}
            onChange={(selected) => {
              setCategoryId(selected);
              if (selected) setCorrecting(false);
            }}
            onCategoryCreated={onCategoryCreated}
            disabled={busy}
            label="Date Variety"
            id="correction-category"
          />
        </Card>
      )}

      {/* ================= 4. Clean Unified Listing Publishing Form (Only for date fruits) ======================= */}
      {file && categoryId && prediction?.is_date_fruit !== false && (
        <Card className="border-emerald-500/40 ring-2 ring-emerald-500/10 shadow-lg">
          <div className="flex flex-wrap items-center justify-between border-b border-stone-200/80 pb-3.5 mb-5 gap-2">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-100 text-emerald-700 border border-emerald-300">
                <CheckCircleIcon className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-black text-stone-900 tracking-tight">Listing Details</h3>
                <p className="text-xs text-stone-500">
                  Publishing date fruit deal to live marketplace
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1 text-xs font-extrabold text-amber-900 bg-amber-100 border border-amber-300/80 px-3 py-1 rounded-full shadow-2xs">
                🏷️ Variety: {selectedCategory?.name}
              </span>
              <button
                type="button"
                onClick={() => {
                  setCategoryId("");
                  setCorrecting(true);
                }}
                className="text-xs font-bold text-amber-700 hover:underline"
              >
                Change
              </button>
            </div>
          </div>

          <form onSubmit={handlePublish} className="space-y-5" noValidate>
            <ListingFields
              values={details}
              onChange={(fieldName, value) =>
                setDetails((current) => ({ ...current, [fieldName]: value }))
              }
              disabled={publishing}
              idPrefix="publish"
            />

            <div className="pt-3 border-t border-stone-100 flex flex-wrap items-center justify-between gap-3">
              <button type="submit" className={buttonClass + " w-full sm:w-auto text-sm py-3 px-6 shadow-md"} disabled={publishing}>
                {publishing ? <Spinner label="Publishing listing to marketplace…" /> : "🚀 Publish Listing"}
              </button>
              <p className="text-xs text-stone-400 italic">
                Your offer will be instantly visible to all marketplace buyers.
              </p>
            </div>
          </form>
        </Card>
      )}
    </div>
  );
}
