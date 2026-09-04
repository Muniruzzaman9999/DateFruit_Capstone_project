/**
 * The date-fruit category dropdown, including the "Other / New Category" flow.
 *
 * The list is always read from the database, never from a hard-coded array. That
 * is the whole point of dynamic categories: the application starts with the nine
 * varieties the model knows, and grows as people add their own.
 */

import { useState } from "react";

import { api, errorMessage } from "../services/api";
import { Alert, Field, Spinner, inputClass, secondaryButtonClass } from "./ui";

/** The dropdown value that means "I want to type a new name". */
const NEW_CATEGORY = "__new__";

export default function CategorySelect({
  categories,
  value,
  onChange,
  onCategoryCreated,
  disabled = false,
  label = "Date-fruit category",
  id = "category",
}) {
  const [addingNew, setAddingNew] = useState(false);
  const [newName, setNewName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // The nine the AI can predict, and the ones people have added, shown as two
  // labelled groups. Worth separating: it tells the person which varieties the
  // model could ever have recognised, rather than implying it knows all of them.
  const modelCategories = categories.filter((item) => item.source === "MODEL");
  const userCategories = categories.filter((item) => item.source === "USER");

  function handleSelectChange(event) {
    const selected = event.target.value;

    if (selected === NEW_CATEGORY) {
      setAddingNew(true);
      setError("");
      // Clear the chosen category: "Other" is not itself a category, so nothing
      // is selected until the new name has actually been created.
      onChange("");
      return;
    }

    setAddingNew(false);
    onChange(selected);
  }

  async function handleCreate() {
    const name = newName.trim();
    if (!name) {
      setError("Please type a category name.");
      return;
    }

    setError("");
    setBusy(true);

    try {
      // POST /api/categories normalises the name and either creates it (201) or
      // returns the one that already matches (200). Both are a success here, and
      // that is exactly why duplicates cannot happen: "Barhi", "barhi" and
      // " BARHI " all resolve to the same single row.
      const response = await api.post("/api/categories", { name });
      const category = response.data;

      onCategoryCreated?.(category);
      onChange(String(category.id));

      setAddingNew(false);
      setNewName("");
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not add that category."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <Field label={label} htmlFor={id}>
        <select
          id={id}
          className={inputClass}
          // `addingNew` keeps "Other / New Category" showing as the selected
          // option while the text box is open, even though `value` is empty.
          value={addingNew ? NEW_CATEGORY : value}
          onChange={handleSelectChange}
          disabled={disabled || busy}
        >
          <option value="">Select a category…</option>

          {modelCategories.length > 0 && (
            <optgroup label="Recognised by the AI">
              {modelCategories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </optgroup>
          )}

          {userCategories.length > 0 && (
            <optgroup label="Added by users">
              {userCategories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </optgroup>
          )}

          <option value={NEW_CATEGORY}>Other / New Category…</option>
        </select>
      </Field>

      {addingNew && (
        <div className="rounded-md border border-stone-200 bg-stone-50 p-3">
          <Field
            label="Enter date-fruit category"
            htmlFor={`${id}-new`}
            hint="Capitals and extra spaces do not matter - 'barhi' and 'Barhi' are the same category."
          >
            <input
              id={`${id}-new`}
              type="text"
              className={inputClass}
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              // Enter would otherwise submit the surrounding listing form, which
              // is not what pressing Enter in this box should do.
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  handleCreate();
                }
              }}
              placeholder="For example: Barhi"
              disabled={busy}
            />
          </Field>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={handleCreate}
              className={secondaryButtonClass}
              disabled={busy}
            >
              {busy ? <Spinner label="Adding…" /> : "Add category"}
            </button>
            <button
              type="button"
              onClick={() => {
                setAddingNew(false);
                setNewName("");
                setError("");
              }}
              className="text-sm text-stone-500 hover:text-stone-800 hover:underline"
              disabled={busy}
            >
              Cancel
            </button>
          </div>

          {error && (
            <div className="mt-3">
              <Alert kind="error">{error}</Alert>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
