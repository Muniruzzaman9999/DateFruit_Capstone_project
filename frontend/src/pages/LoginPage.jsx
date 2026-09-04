import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { PalmIcon } from "../components/icons";
import { Alert, Card, Field, Spinner, buttonClass, inputClass } from "../components/ui";
import { useAuth } from "../context/useAuth";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setBusy(true);
    const result = await login(email, password);
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
          <h1 className="text-2xl font-extrabold text-stone-900">Welcome Back</h1>
          <p className="mt-1 text-xs text-stone-500">
            Log in to manage your listings and compare market prices
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <Field label="Email Address" htmlFor="email">
            <input
              id="email"
              type="email"
              className={inputClass}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="seller@example.com"
              autoComplete="email"
              required
              disabled={busy}
            />
          </Field>

          <Field label="Password" htmlFor="password">
            <input
              id="password"
              type="password"
              className={inputClass}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              required
              disabled={busy}
            />
          </Field>

          <Alert kind="error">{error}</Alert>

          <button type="submit" className={`${buttonClass} w-full py-3`} disabled={busy}>
            {busy ? <Spinner label="Authenticating…" /> : "Log In"}
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-stone-500">
          Don&apos;t have an account yet?{" "}
          <Link to="/register" className="font-bold text-amber-700 hover:underline">
            Register now
          </Link>
        </p>
      </Card>
    </div>
  );
}
