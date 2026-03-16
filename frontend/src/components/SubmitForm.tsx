"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight, Loader2, AlertCircle, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

interface SubmitFormProps {
  onSubmit: (email: string) => Promise<void>;
  isLoading: boolean;
  rowCount: number;
}

function validateEmail(value: string): string {
  if (!value.trim()) return "Email is required.";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim()))
    return "Please enter a valid email address.";
  return "";
}

export default function SubmitForm({
  onSubmit,
  isLoading,
  rowCount,
}: SubmitFormProps) {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");

  const estimatedMinutes = Math.ceil(rowCount / 2000);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const validationError = validateEmail(email);
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
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
    >
      <Card className="overflow-hidden">
        {/* Gradient top border */}
        <div className="h-1 w-full bg-gradient-to-r from-primary via-blue-400 to-primary/60" />

        <CardContent className="p-6 space-y-5">
          {/* Header */}
          <div className="space-y-1">
            <h3 className="text-lg font-semibold text-text-primary tracking-tight">
              Ready to process
            </h3>
            <p className="text-sm text-text-secondary">
              <span className="font-medium text-text-primary">{rowCount.toLocaleString()}</span>{" "}
              {rowCount === 1 ? "company" : "companies"} will be processed
            </p>
          </div>

          {/* Estimated time */}
          <div
            className={cn(
              "flex items-center gap-2 px-3 py-2 rounded-md",
              "bg-primary/5 border border-primary/15 text-primary"
            )}
          >
            <Clock className="h-3.5 w-3.5 shrink-0" />
            <span className="text-xs font-medium">
              Estimated time: ~{estimatedMinutes}{" "}
              {estimatedMinutes === 1 ? "minute" : "minutes"}
            </span>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <div className="space-y-2">
              <Label htmlFor="submit-email">Email for results delivery</Label>
              <Input
                id="submit-email"
                type="email"
                value={email}
                onChange={handleChange}
                placeholder="you@company.com"
                disabled={isLoading}
                autoComplete="email"
                aria-describedby={error ? "email-error" : "email-hint"}
                className={cn(error && "border-red-400 focus:border-red-400 focus:ring-red-400/20")}
              />
              {error ? (
                <motion.p
                  id="email-error"
                  role="alert"
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex items-center gap-1.5 text-xs text-red-500"
                >
                  <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                  {error}
                </motion.p>
              ) : (
                <p id="email-hint" className="text-xs text-text-secondary">
                  We&apos;ll email you the results CSV when processing is complete.
                </p>
              )}
            </div>

            <motion.div
              whileHover={isLoading ? {} : { scale: 1.015 }}
              whileTap={isLoading ? {} : { scale: 0.98 }}
              transition={{ duration: 0.12 }}
            >
              <Button
                type="submit"
                size="lg"
                disabled={isLoading}
                className="w-full gap-2"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Processing&hellip;
                  </>
                ) : (
                  <>
                    Start Processing
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </Button>
            </motion.div>
          </form>
        </CardContent>
      </Card>
    </motion.div>
  );
}
