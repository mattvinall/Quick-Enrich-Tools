"use client";

import { useRef, useState, DragEvent, ChangeEvent, useCallback } from "react";
import Papa from "papaparse";
import { motion, AnimatePresence } from "framer-motion";
import { Upload, FileText, X, ClipboardPaste, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

interface UploadZoneProps {
  onDataReady: (
    file: File | null,
    headers: string[],
    rows: Record<string, string>[],
    rawText?: string
  ) => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface ParsedFile {
  file: File;
  headers: string[];
  rows: Record<string, string>[];
}

export default function UploadZone({ onDataReady }: UploadZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [parsedFile, setParsedFile] = useState<ParsedFile | null>(null);
  const [pasteText, setPasteText] = useState("");
  const [isParsing, setIsParsing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const parseFile = useCallback(
    (file: File) => {
      setError(null);

      if (!file.name.toLowerCase().endsWith(".csv")) {
        setError("Invalid file type. Please upload a .csv file.");
        return;
      }

      if (file.size > MAX_FILE_SIZE) {
        setError(`File is too large. Maximum allowed size is 50MB (got ${formatBytes(file.size)}).`);
        return;
      }

      setIsParsing(true);

      Papa.parse<Record<string, string>>(file, {
        header: true,
        skipEmptyLines: true,
        transformHeader: (h) => h.trim(),
        complete: (results) => {
          setIsParsing(false);
          const headers = results.meta.fields ?? [];

          if (headers.length === 0) {
            setError("CSV file appears to have no headers. Please check the file format.");
            return;
          }

          const rows = results.data.slice(0, 5);
          setParsedFile({ file, headers, rows });
          onDataReady(file, headers, results.data, undefined);
        },
        error: () => {
          setIsParsing(false);
          setError("Failed to parse CSV file. Please check the file format.");
        },
      });
    },
    [onDataReady]
  );

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragging(false);
    }
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) parseFile(file);
  };

  const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) parseFile(file);
    e.target.value = "";
  };

  const handleRemoveFile = () => {
    setParsedFile(null);
    setError(null);
  };

  const handleParsePaste = () => {
    const text = pasteText.trim();
    if (!text) {
      setError("Please paste some data before parsing.");
      return;
    }
    setError(null);

    // Detect delimiter: tab-separated vs comma-separated
    const firstLine = text.split(/\r?\n/)[0] ?? "";
    const tabCount = (firstLine.match(/\t/g) ?? []).length;
    const commaCount = (firstLine.match(/,/g) ?? []).length;
    const delimiter = tabCount >= commaCount ? "\t" : ",";

    const result = Papa.parse<Record<string, string>>(text, {
      header: true,
      skipEmptyLines: true,
      delimiter,
      transformHeader: (h) => h.trim(),
    });

    const headers = result.meta.fields ?? [];

    if (headers.length === 0) {
      setError("Could not detect columns. Make sure your first line contains headers.");
      return;
    }

    onDataReady(null, headers, result.data, text);
  };

  return (
    <Tabs defaultValue="upload" className="w-full">
      <TabsList className="mb-2">
        <TabsTrigger value="upload" className="gap-2">
          <Upload className="h-4 w-4" />
          Upload CSV
        </TabsTrigger>
        <TabsTrigger value="paste" className="gap-2">
          <ClipboardPaste className="h-4 w-4" />
          Paste Data
        </TabsTrigger>
      </TabsList>

      {/* Upload Tab */}
      <TabsContent value="upload">
        <AnimatePresence mode="wait">
          {parsedFile ? (
            <motion.div
              key="file-pill"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
              className="flex items-center gap-3 rounded-xl border border-border bg-white p-4 shadow-sm"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                <FileText className="h-5 w-5 text-primary" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-text-primary">
                  {parsedFile.file.name}
                </p>
                <p className="text-xs text-text-secondary">
                  {formatBytes(parsedFile.file.size)} &mdash;{" "}
                  {parsedFile.headers.length} columns
                </p>
              </div>
              <button
                type="button"
                onClick={handleRemoveFile}
                aria-label="Remove file"
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
              >
                <X className="h-4 w-4" />
              </button>
            </motion.div>
          ) : (
            <motion.div
              key="drop-zone"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
            >
              <motion.div
                animate={isDragging ? { scale: 1.02 } : { scale: 1 }}
                transition={{ type: "spring", stiffness: 400, damping: 25 }}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => inputRef.current?.click()}
                onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
                role="button"
                tabIndex={0}
                aria-label="Upload CSV file by clicking or dragging"
                className={cn(
                  "group relative flex cursor-pointer flex-col items-center justify-center gap-4 rounded-xl border-2 border-dashed px-8 py-12 text-center transition-colors duration-200",
                  isDragging
                    ? "border-primary bg-primary/5"
                    : "border-border hover:border-primary/60 hover:bg-gray-50/60"
                )}
              >
                <input
                  ref={inputRef}
                  type="file"
                  accept=".csv"
                  className="hidden"
                  onChange={handleInputChange}
                />

                <motion.div
                  animate={isDragging ? { y: -4 } : { y: 0 }}
                  transition={{ type: "spring", stiffness: 400, damping: 20 }}
                  className={cn(
                    "flex h-14 w-14 items-center justify-center rounded-xl transition-colors duration-200",
                    isDragging
                      ? "bg-primary/15 text-primary"
                      : "bg-gray-100 text-gray-400 group-hover:bg-primary/10 group-hover:text-primary"
                  )}
                >
                  <Upload className="h-6 w-6" />
                </motion.div>

                <div className="space-y-1">
                  <p className="text-sm font-semibold text-text-primary">
                    {isDragging ? "Drop your file here" : "Drag & drop your CSV file"}
                  </p>
                  <p className="text-sm text-text-secondary">
                    or{" "}
                    <span className="font-medium text-primary underline underline-offset-2">
                      click to browse
                    </span>
                  </p>
                  <p className="text-xs text-gray-400">.csv only &mdash; max 50MB</p>
                </div>

                {isParsing && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="absolute inset-0 flex items-center justify-center rounded-xl bg-white/80 backdrop-blur-sm"
                  >
                    <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                  </motion.div>
                )}
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.15 }}
              className="mt-3 flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-600"
              role="alert"
            >
              <AlertCircle className="h-4 w-4 shrink-0" />
              {error}
            </motion.div>
          )}
        </AnimatePresence>
      </TabsContent>

      {/* Paste Tab */}
      <TabsContent value="paste">
        <div className="space-y-3">
          <Textarea
            value={pasteText}
            onChange={(e) => {
              setPasteText(e.target.value);
              setError(null);
            }}
            rows={10}
            placeholder={
              "Paste your data here... one company per line\n\nExamples:\nAcme Corp, Chicago IL\nGlobex Inc, New York NY"
            }
            className="font-mono text-xs leading-relaxed"
          />

          <div className="flex items-center justify-between">
            <p className="text-xs text-text-secondary">
              Supports comma-separated or tab-separated data. First row should be headers.
            </p>
            <Button
              onClick={handleParsePaste}
              disabled={!pasteText.trim() || isParsing}
              size="sm"
              className="shrink-0"
            >
              Parse Data
            </Button>
          </div>

          <AnimatePresence>
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.15 }}
                className="flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-600"
                role="alert"
              >
                <AlertCircle className="h-4 w-4 shrink-0" />
                {error}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </TabsContent>
    </Tabs>
  );
}
