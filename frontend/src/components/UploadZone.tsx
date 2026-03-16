'use client';

import { useRef, useState, DragEvent, ChangeEvent } from 'react';

interface UploadZoneProps {
  onFileSelected: (
    file: File,
    headers: string[],
    preview: Record<string, string>[]
  ) => void;
}

const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024; // 50MB

function parseCsv(text: string): { headers: string[]; preview: Record<string, string>[] } {
  const lines = text.split(/\r?\n/).filter((line) => line.trim() !== '');

  const headers = lines[0]
    .split(',')
    .map((h) => h.trim().replace(/^["']|["']$/g, ''));

  const preview: Record<string, string>[] = lines
    .slice(1, 6)
    .map((line) => {
      const values = line.split(',').map((v) => v.trim().replace(/^["']|["']$/g, ''));
      return headers.reduce<Record<string, string>>((row, header, i) => {
        row[header] = values[i] ?? '';
        return row;
      }, {});
    });

  return { headers, preview };
}

export default function UploadZone({ onFileSelected }: UploadZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function validateAndProcess(file: File) {
    setError(null);

    if (!file.name.toLowerCase().endsWith('.csv')) {
      setError('Invalid file type. Please upload a .csv file.');
      return;
    }

    if (file.size > MAX_FILE_SIZE_BYTES) {
      setError('File is too large. Maximum allowed size is 50MB.');
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result;
      if (typeof text !== 'string') {
        setError('Could not read file contents.');
        return;
      }
      try {
        const { headers, preview } = parseCsv(text);
        if (headers.length === 0) {
          setError('CSV file appears to have no headers.');
          return;
        }
        onFileSelected(file, headers, preview);
      } catch {
        setError('Failed to parse CSV file. Please check the file format.');
      }
    };
    reader.onerror = () => setError('An error occurred while reading the file.');
    reader.readAsText(file);
  }

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) validateAndProcess(file);
  }

  function handleInputChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) validateAndProcess(file);
    // Reset input so the same file can be re-selected if needed
    e.target.value = '';
  }

  function handleClick() {
    inputRef.current?.click();
  }

  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload CSV file"
        onClick={handleClick}
        onKeyDown={(e) => e.key === 'Enter' && handleClick()}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={[
          'border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors duration-150',
          isDragging
            ? 'border-primary bg-primary-light'
            : 'border-[#e5e7eb] hover:border-primary hover:bg-primary-light',
        ].join(' ')}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={handleInputChange}
        />

        <div className="flex flex-col items-center gap-3 pointer-events-none select-none">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="w-10 h-10 text-[#6b7280]"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1.5}
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
            />
          </svg>

          <p className="text-[#1f2937] font-medium">
            Drag &amp; drop your CSV file here
          </p>
          <p className="text-[#6b7280] text-sm">
            or{' '}
            <span className="text-primary underline underline-offset-2">
              click to browse
            </span>
          </p>
          <p className="text-[#6b7280] text-xs mt-1">CSV files only &mdash; max 50MB</p>
        </div>
      </div>

      {error && (
        <p role="alert" className="mt-3 text-sm text-red-600 font-medium">
          {error}
        </p>
      )}
    </div>
  );
}
