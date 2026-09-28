"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [organizationSlug, setOrganizationSlug] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const { access_token } = await api.login(organizationSlug, email, password);
      setToken(access_token);
      router.push("/dashboard");
    } catch (err) {
      // Deliberately generic (spec §53 — don't help an attacker enumerate
      // valid emails); the API already returns a generic message too.
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-lg bg-surface p-8 shadow-sm"
      >
        <h1 className="mb-1 text-2xl font-semibold">RAISA Synapse</h1>
        <p className="mb-6 text-sm text-ink/60">Sign in to your organization</p>

        <label className="mb-3 block text-sm">
          Organization
          <input
            className="mt-1 w-full rounded border border-black/10 px-3 py-2"
            placeholder="demo-pharma"
            value={organizationSlug}
            onChange={(e) => setOrganizationSlug(e.target.value)}
            required
          />
        </label>

        <label className="mb-3 block text-sm">
          Email
          <input
            type="email"
            className="mt-1 w-full rounded border border-black/10 px-3 py-2"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>

        <label className="mb-4 block text-sm">
          Password
          <input
            type="password"
            className="mt-1 w-full rounded border border-black/10 px-3 py-2"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>

        {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

        <button
          type="submit"
            disabled={submitting}
          className="w-full rounded bg-accent px-4 py-2 font-medium text-white disabled:opacity-60"
        >
          {submitting ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </main>
  );
}
