'use client';

const COMPANY_REGEX = /company|name|org|business|brand/i;
const LOCATION_REGEX = /location|city|state|address|geo|region/i;

export function autoDetectColumns(headers: string[]): { company: string; location: string } {
  const company = headers.find((h) => COMPANY_REGEX.test(h)) ?? '';
  const location = headers.find((h) => LOCATION_REGEX.test(h)) ?? '';
  return { company, location };
}

interface ColumnMapperProps {
  headers: string[];
  preview: Record<string, string>[];
  companyColumn: string;
  locationColumn: string;
  onCompanyColumnChange: (column: string) => void;
  onLocationColumnChange: (column: string) => void;
}

export default function ColumnMapper({
  headers,
  preview,
  companyColumn,
  locationColumn,
  onCompanyColumnChange,
  onLocationColumnChange,
}: ColumnMapperProps) {
  return (
    <div className="flex flex-col gap-6">
      {/* Column selectors */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Company Name */}
        <div className="flex flex-col gap-1">
          <label
            htmlFor="company-column"
            className="text-sm font-medium text-[#1f2937]"
          >
            Company Name{' '}
            <span className="text-red-500" aria-label="required">
              *
            </span>
          </label>
          <select
            id="company-column"
            value={companyColumn}
            onChange={(e) => onCompanyColumnChange(e.target.value)}
            className="w-full rounded-md border border-[#e5e7eb] bg-white px-3 py-2 text-sm text-[#1f2937] shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="">— Select a column —</option>
            {headers.map((header) => (
              <option key={header} value={header}>
                {header}
              </option>
            ))}
          </select>
        </div>

        {/* Location */}
        <div className="flex flex-col gap-1">
          <label
            htmlFor="location-column"
            className="text-sm font-medium text-[#1f2937]"
          >
            Location{' '}
            <span className="text-[#6b7280] font-normal text-xs">(optional)</span>
          </label>
          <select
            id="location-column"
            value={locationColumn}
            onChange={(e) => onLocationColumnChange(e.target.value)}
            className="w-full rounded-md border border-[#e5e7eb] bg-white px-3 py-2 text-sm text-[#1f2937] shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="">— None —</option>
            {headers.map((header) => (
              <option key={header} value={header}>
                {header}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Preview table */}
      {preview.length > 0 && (
        <div>
          <div className="overflow-x-auto rounded-lg border border-[#e5e7eb]">
            <table className="min-w-full text-sm text-[#1f2937]">
              <thead className="bg-[#f9fafb] border-b border-[#e5e7eb]">
                <tr>
                  {headers.map((header) => {
                    const isCompany = header === companyColumn && companyColumn !== '';
                    const isLocation = header === locationColumn && locationColumn !== '';
                    return (
                      <th
                        key={header}
                        scope="col"
                        className={[
                          'px-4 py-2 text-left font-semibold whitespace-nowrap',
                          isCompany ? 'bg-primary/10' : '',
                          isLocation && !isCompany ? 'bg-blue-50' : '',
                        ]
                          .filter(Boolean)
                          .join(' ')}
                      >
                        <span className="max-w-[200px] block truncate">{header}</span>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {preview.map((row, rowIndex) => (
                  <tr
                    key={rowIndex}
                    className={rowIndex % 2 === 0 ? 'bg-white' : 'bg-[#f9fafb]'}
                  >
                    {headers.map((header) => {
                      const isCompany = header === companyColumn && companyColumn !== '';
                      const isLocation = header === locationColumn && locationColumn !== '';
                      return (
                        <td
                          key={header}
                          className={[
                            'px-4 py-2 align-middle',
                            isCompany ? 'bg-primary/10' : '',
                            isLocation && !isCompany ? 'bg-blue-50' : '',
                          ]
                            .filter(Boolean)
                            .join(' ')}
                        >
                          <span
                            className="max-w-[200px] block truncate text-[#1f2937]"
                            title={row[header]}
                          >
                            {row[header]}
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-[#6b7280]">
            Showing first {preview.length} row{preview.length !== 1 ? 's' : ''}
          </p>
        </div>
      )}
    </div>
  );
}
