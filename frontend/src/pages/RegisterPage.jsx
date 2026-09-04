import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { PalmIcon } from "../components/icons";
import { Alert, Card, Field, Spinner, buttonClass, inputClass } from "../components/ui";
import { useAuth } from "../context/useAuth";

const MIN_PASSWORD_LENGTH = 8;

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
    contact_number: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function update(field) {
    return (event) => setForm((current) => ({ ...current, [field]: event.target.value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");

    if (form.password.length < MIN_PASSWORD_LENGTH) {
      setError(`Please choose a password of at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }

    setBusy(true);
    const result = await register(form);
    setBusy(false);

    if (result.ok) {
      navigate("/app", { replace: true });
    } else {
      setError(result.message);
    }
  }

  return (
    <div className="mx-auto max-w-md py-6">
      <Card className="border-amber-100 shadow-xl">
        <div className="text-center mb-6">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-600 text-white shadow-md shadow-amber-600/20 mb-3">
            <PalmIcon className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-2xl font-extrabold text-stone-900">Create Account</h1>
          <p className="mt-1 text-xs text-stone-500">
            Join the Date Fruit AI Marketplace to publish &amp; compare prices
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <Field label="Full Name" htmlFor="name">
            <input
              id="name"
              type="text"
              className={inputClass}
              value={form.name}
              onChange={update("name")}
              placeholder="e.g. Munir Ahmed"
              autoComplete="name"
              required
              disabled={busy}
            />
          </Field>

          <Field label="Email Address" htmlFor="email">
            <input
              id="email"
              type="email"
              className={inputClass}
              value={form.email}
              onChange={update("email")}
              placeholder="munir@example.com"
              autoComplete="email"
              required
              disabled={busy}
            />
          </Field>

          <Field
            label="Password"
            htmlFor="password"
            hint={`Must be at least ${MIN_PASSWORD_LENGTH} characters.`}
          >
            <input
              id="password"
              type="password"
              className={inputClass}
              value={form.password}
              onChange={update("password")}
              placeholder="••••••••"
              autoComplete="new-password"
              required
              disabled={busy}
            />
          </Field>

          <Field
            label="Contact Number"
            htmlFor="contact_number"
            hint="For buyers to reach your shop (e.g. 01711223344)"
          >
            <input
              id="contact_number"
              type="tel"
              className={inputClass}
              value={form.contact_number}
              onChange={update("contact_number")}
              placeholder="01711223344"
              autoComplete="tel"
              required
              disabled={busy}
            />
          </Field>

          <Alert kind="error">{error}</Alert>

          <button type="submit" className={`${buttonClass} w-full py-3`} disabled={busy}>
            {busy ? <Spinner label="Creating account…" /> : "Create Account"}
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-stone-500">
          Already registered?{" "}
          <Link to="/login" className="font-bold text-amber-700 hover:underline">
            Log in here
          </Link>
        </p>
      </Card>
    </div>
  );
}
