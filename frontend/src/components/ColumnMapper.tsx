"use client";

import { useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Building2, MapPin } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// Ordered by specificity — first match wins
const COMPANY_PATTERNS = [
  /company.?name/i,
  /company/i,
  /org(anization)?/i,
  /business.?name/i,
  /business/i,
  /brand/i,
  /^name$/i,
];

const LOCATION_PATTERNS = [
  /location/i,
  /city.?state/i,
  /address/i,
  /city/i,
  /state/i,
  /region/i,
  /geo/i,
  /hq/i,
  /headquarters/i,
];

export function autoDetectColumns(headers: string[]): { company: string; location: string } {
  let company = "";
  for (const pattern of COMPANY_PATTERNS) {
    const match = headers.find((h) => pattern.test(h));
    if (match) {
      company = match;
      break;
    }
  }

  let location = "";
  for (const pattern of LOCATION_PATTERNS) {
    const match = headers.find((h) => pattern.test(h) && h !== company);
    if (match) {
      location = match;
      break;
    }
  }

  return { company, location };
}

interface ColumnMapperProps {
  headers: string[];
  preview: Record<string, string>[];
  companyColumn: string;
  locationColumn: string;
  onCompanyColumnChange: (col: string) => void;
  onLocationColumnChange: (col: string) => void;
}

const PREVIEW_LIMIT = 5;

export default function ColumnMapper({
  headers,
  preview,
  companyColumn,
  locationColumn,
  onCompanyColumnChange,
  onLocationColumnChange,
}: ColumnMapperProps) {
  const prevCompany = useRef(companyColumn);
  const prevLocation = useRef(locationColumn);

  const companyChanged = prevCompany.current !== companyColumn;
  const locationChanged = prevLocation.current !== locationColumn;
  prevCompany.current = companyColumn;
  prevLocation.current = locationColumn;

  const displayRows = preview.slice(0, PREVIEW_LIMIT);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="space-y-6"
    >
      {/* Selectors */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {/* Company Column */}
        <div className="space-y-1.5">
          <label className="flex items-center gap-1.5 text-sm font-medium text-text-primary">
            <Building2 className="h-4 w-4 text-text-secondary" />
            Company Name
            <span className="text-red-500" aria-label="required">
              *
            </span>
          </label>
          <motion.div
            key={companyColumn}
            animate={companyChanged ? { scale: [1, 1.01, 1] } : {}}
            transition={{ duration: 0.25 }}
          >
            <Select value={companyColumn} onValueChange={onCompanyColumnChange}>
              <SelectTrigger
                className={cn(
                  companyColumn &&
                    "border-primary/50 ring-1 ring-primary/20 focus:ring-primary/30"
                )}
              >
                <SelectValue placeholder="Select a column…" />
              </SelectTrigger>
              <SelectContent>
                {headers.map((header) => (
                  <SelectItem key={header} value={header}>
                    {header}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </motion.div>
        </div>

        {/* Location Column */}
        <div className="space-y-1.5">
          <label className="flex items-center gap-1.5 text-sm font-medium text-text-primary">
            <MapPin className="h-4 w-4 text-text-secondary" />
            Location
            <span className="text-xs font-normal text-text-secondary">(recommended)</span>
          </label>
          <motion.div
            key={locationColumn}
            animate={locationChanged ? { scale: [1, 1.01, 1] } : {}}
            transition={{ duration: 0.25 }}
          >
            <Select value={locationColumn || "__none__"} onValueChange={(v) => onLocationColumnChange(v === "__none__" ? "" : v)}>
              <SelectTrigger
                className={cn(
                  locationColumn &&
                    "border-blue-400/50 ring-1 ring-blue-400/20 focus:ring-blue-400/30"
                )}
              >
                <SelectValue placeholder="None" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">— None —</SelectItem>
                {headers.map((header) => (
                  <SelectItem key={header} value={header}>
                    {header}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </motion.div>
        </div>
      </div>

      {/* Preview Table */}
      <AnimatePresence>
        {displayRows.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.2 }}
          >
            <Card className="overflow-hidden">
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="border-b border-border bg-gray-50/80">
                        {headers.map((header) => {
                          const isCompany = header === companyColumn && companyColumn !== "";
                          const isLocation = header === locationColumn && locationColumn !== "";
                          return (
                            <th
                              key={header}
                              scope="col"
                              className={cn(
                                "whitespace-nowrap px-4 py-3 text-left text-xs font-semibold tracking-wide",
                                isCompany && "bg-primary/8 text-primary",
                                isLocation && !isCompany && "bg-blue-50 text-blue-600",
                                !isCompany && !isLocation && "text-text-secondary"
                              )}
                            >
                              <div className="flex items-center gap-1.5">
                                <span className="max-w-[160px] truncate">{header}</span>
                                <AnimatePresence>
                                  {isCompany && (
                                    <motion.div
                                      initial={{ opacity: 0, scale: 0.7 }}
                                      animate={{ opacity: 1, scale: 1 }}
                                      exit={{ opacity: 0, scale: 0.7 }}
                                      transition={{ duration: 0.15 }}
                                    >
                                      <Badge className="bg-primary/15 text-primary text-[10px] px-1.5 py-0">
                                        Company
                                      </Badge>
                                    </motion.div>
                                  )}
                                  {isLocation && !isCompany && (
                                    <motion.div
                                      initial={{ opacity: 0, scale: 0.7 }}
                                      animate={{ opacity: 1, scale: 1 }}
                                      exit={{ opacity: 0, scale: 0.7 }}
                                      transition={{ duration: 0.15 }}
                                    >
                                      <Badge className="bg-blue-100 text-blue-600 text-[10px] px-1.5 py-0">
                                        Location
                                      </Badge>
                                    </motion.div>
                                  )}
                                </AnimatePresence>
                              </div>
                            </th>
                          );
                        })}
                      </tr>
                    </thead>
                    <tbody>
                      {displayRows.map((row, rowIndex) => (
                        <tr
                          key={rowIndex}
                          className={cn(
                            "border-b border-border/50 last:border-0",
                            rowIndex % 2 === 0 ? "bg-white" : "bg-gray-50/50"
                          )}
                        >
                          {headers.map((header) => {
                            const isCompany = header === companyColumn && companyColumn !== "";
                            const isLocation =
                              header === locationColumn && locationColumn !== "";
                            return (
                              <td
                                key={header}
                                className={cn(
                                  "px-4 py-2.5 align-middle",
                                  isCompany && "bg-primary/5",
                                  isLocation && !isCompany && "bg-blue-50/60"
                                )}
                              >
                                <span
                                  className={cn(
                                    "block max-w-[200px] truncate text-xs",
                                    isCompany && "font-medium text-text-primary",
                                    isLocation && !isCompany && "text-blue-700",
                                    !isCompany && !isLocation && "text-text-secondary"
                                  )}
                                  title={row[header]}
                                >
                                  {row[header] || (
                                    <span className="italic text-gray-300">empty</span>
                                  )}
                                </span>
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            <p className="mt-2 text-xs text-text-secondary">
              Showing {displayRows.length} of {preview.length} row
              {preview.length !== 1 ? "s" : ""}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
