import { Field, inputClass } from "./ui";

const UNITS = ["gram", "kg", "piece"];

export default function ListingFields({
  values,
  onChange,
  disabled = false,
  idPrefix = "listing",
}) {
  const handle = (field) => (event) => onChange(field, event.target.value);
  const fieldId = (name) => `${idPrefix}-${name}`;

  return (
    <div className="space-y-4">
      {/* Price & Quantity Grid */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Price (৳)" htmlFor={fieldId("price")}>
          <input
            id={fieldId("price")}
            type="number"
            step="0.01"
            min="0.01"
            className={inputClass}
            value={values.price}
            onChange={handle("price")}
            placeholder="850"
            required
            disabled={disabled}
          />
        </Field>

        <Field label="Quantity" htmlFor={fieldId("quantity")}>
          <input
            id={fieldId("quantity")}
            type="number"
            step="0.001"
            min="0.001"
            className={inputClass}
            value={values.quantity}
            onChange={handle("quantity")}
            placeholder="1"
            required
            disabled={disabled}
          />
        </Field>

        <Field label="Unit" htmlFor={fieldId("unit")}>
          <select
            id={fieldId("unit")}
            className={inputClass}
            value={values.unit}
            onChange={handle("unit")}
            required
            disabled={disabled}
          >
            {UNITS.map((unit) => (
              <option key={unit} value={unit}>
                {unit}
              </option>
            ))}
          </select>
        </Field>
      </div>

      <div className="rounded-xl bg-amber-50/70 border border-amber-200/80 p-3.5 text-xs text-amber-900 leading-relaxed">
        💡 <strong>Pricing Guide:</strong> Enter total price for the quantity. For 1kg at ৳850, use price <strong>850</strong>, qty <strong>1</strong>, unit <strong>kg</strong>. For a 200g pack at ৳180, enter price <strong>180</strong>, qty <strong>200</strong>, unit <strong>gram</strong>.
      </div>

      {/* Shop Info */}
      <Field label="Shop Name" htmlFor={fieldId("shop_name")}>
        <input
          id={fieldId("shop_name")}
          type="text"
          maxLength={120}
          className={inputClass}
          value={values.shop_name}
          onChange={handle("shop_name")}
          placeholder="Rahim Dates Store"
          required
          disabled={disabled}
        />
      </Field>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Contact Number"
          htmlFor={fieldId("contact_number")}
          hint="Phone number for interested buyers"
        >
          <input
            id={fieldId("contact_number")}
            type="tel"
            maxLength={30}
            className={inputClass}
            value={values.contact_number}
            onChange={handle("contact_number")}
            placeholder="01711222333"
            required
            disabled={disabled}
          />
        </Field>

        <Field
          label="Shop Location"
          htmlFor={fieldId("shop_location")}
          hint="Area & City (e.g. Mirpur, Dhaka)"
        >
          <input
            id={fieldId("shop_location")}
            type="text"
            maxLength={255}
            className={inputClass}
            value={values.shop_location}
            onChange={handle("shop_location")}
            placeholder="Mirpur-10, Dhaka"
            required
            disabled={disabled}
          />
        </Field>
      </div>
    </div>
  );
}
