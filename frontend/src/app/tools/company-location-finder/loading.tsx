export default function Loading() {
  return (
    <main className="min-h-screen bg-gradient-to-b from-gray-50 to-white py-8 px-4">
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="text-center space-y-2">
          <div className="h-9 w-80 bg-gray-200 rounded-lg mx-auto animate-pulse" />
          <div className="h-5 w-64 bg-gray-100 rounded mx-auto animate-pulse" />
        </div>

        <div className="flex items-center gap-2 justify-center">
          <div className="flex gap-1.5">
            {[1, 2, 3, 4].map((n) => (
              <div key={n} className="w-2.5 h-2.5 rounded-full bg-gray-200 animate-pulse" />
            ))}
          </div>
          <div className="h-4 w-32 bg-gray-100 rounded animate-pulse" />
        </div>

        <div className="bg-white rounded-2xl border border-[#e5e7eb] shadow-sm p-6 sm:p-8">
          <div className="space-y-4">
            <div className="h-10 w-48 bg-gray-100 rounded-lg animate-pulse" />
            <div className="border-2 border-dashed border-gray-200 rounded-xl p-12 flex flex-col items-center gap-3">
              <div className="h-10 w-10 bg-gray-100 rounded-lg animate-pulse" />
              <div className="h-5 w-52 bg-gray-100 rounded animate-pulse" />
              <div className="h-4 w-36 bg-gray-50 rounded animate-pulse" />
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
