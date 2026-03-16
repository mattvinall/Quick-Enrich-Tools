"use client";

import { useState } from "react";

interface EmailGateProps {
  onSubmit: (email: string) => Promise<void>;
  isLoading: boolean;
}

export default function EmailGate({ onSubmit, isLoading }: EmailGateProps) {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");

  function validate(value: string): string {
    if (!value.trim()) return "Email is required.";
    if (!value.includes("@")) return "Please enter a valid email address.";
    return "";
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const validationError = validate(email);
    if (validationError) {
      setError(validationError);
      return;
    }
    setError("");
    await onSubmit(email.trim());
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    setEmail(e.target.value);
    if (error) setError("");
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-1">
        <label
          htmlFor="email-input"
          className="block text-sm font-medium text-foreground"
        >
          Enter your email to start processing
        </label>
        <p className="text-xs text-muted-foreground">
          Results will be emailed to you when complete.
        </p>
      </div>

      <div className="space-y-2">
        <input
          id="email-input"
          type="text"
          value={email}
          onChange={handleChange}
          placeholder="you@example.com"
          disabled={isLoading}
          className="w-full px-3 py-2 text-sm border border-border rounded-md bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-50 disabled:cursor-not-allowed"
        />

        {error && (
          <p className="text-xs text-red-500" role="alert">
            {error}
          </p>
        )}
      </div>

      <button
        type="submit"
        disabled={isLoading}
        className="w-full px-4 py-2 text-sm font-medium rounded-md bg-primary text-white hover:bg-primary-hover hover:-translate-y-0.5 transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed disabled:translate-y-0"
      >
        {isLoading ? "Processing..." : "Start Processing"}
      </button>
    </form>
  );
}
