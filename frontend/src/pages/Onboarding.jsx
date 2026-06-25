import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { generatePlan, getMajors } from "../api/client.js";

const CURRENT_YEAR = new Date().getFullYear();
const YEARS = Array.from({ length: 4 }, (_, i) => CURRENT_YEAR + i);

export default function Onboarding() {
  const navigate = useNavigate();

  const [majors, setMajors] = useState([{ code: "CS", name: "Computer Science, B.S." }]);
  const [major, setMajor] = useState("CS");
  const [completedInput, setCompletedInput] = useState("");
  const [majorsLoading, setMajorsLoading] = useState(true);
  const [majorsError, setMajorsError] = useState(false);

  useEffect(() => {
    setMajorsLoading(true);
    getMajors()
      .then((list) => {
        if (list?.length) {
          setMajors(list);
          setMajor(list[0].code);
        }
        setMajorsError(false);
      })
      .catch(() => setMajorsError(true)) // surface it; fall back to the CS-only list
      .finally(() => setMajorsLoading(false));
  }, []);
  const [startSemester, setStartSemester] = useState("Fall");
  const [startYear, setStartYear] = useState(CURRENT_YEAR);
  const [maxUnits, setMaxUnits] = useState(15);
  const [includeGe, setIncludeGe] = useState(true);   // always on — everyone needs GE
  const [includeAi, setIncludeAi] = useState(true);  // always on — CA law requirement
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  function parseCompleted(text) {
    return text
      .split(/[\n,]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const plan = await generatePlan({
        major,
        completed_courses: parseCompleted(completedInput),
        start_semester: startSemester,
        start_year: Number(startYear),
        max_units_per_semester: maxUnits,
        target_graduation: `Spring ${Number(startYear) + 4}`,
        include_ge: includeGe,
        include_ai: includeAi,
      });
      const majorName = majors.find((m) => m.code === major)?.name || major;
      navigate("/plan", {
        state: {
          plan,
          settings: { major, majorName, maxUnits },
          completedCourses: parseCompleted(completedInput),
        },
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Nav */}
      <header className="bg-sdsu-red shadow-sm">
        <div className="max-w-2xl mx-auto px-6 py-4">
          <Link to="/" className="flex items-center gap-3 w-fit">
            <div className="w-8 h-8 bg-white rounded-full flex items-center justify-center">
              <span className="text-sdsu-red font-black text-sm">S</span>
            </div>
            <span className="text-white font-bold text-lg tracking-tight">
              SDSU Course Planner
            </span>
          </Link>
        </div>
      </header>

      {/* Main */}
      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-lg">
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="bg-sdsu-red px-8 py-6">
              <h1 className="text-2xl font-bold text-white">
                Build Your 4-Year Plan
              </h1>
              <p className="text-red-100 mt-1 text-sm">
                We'll schedule your courses semester by semester, respecting
                prerequisites and unit caps.
              </p>
            </div>

            <form onSubmit={handleSubmit} className="px-8 py-6 space-y-5">
              {/* Major */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Major
                  {majorsLoading && (
                    <span className="text-gray-400 font-normal"> — loading majors…</span>
                  )}
                </label>
                <select
                  value={major}
                  onChange={(e) => setMajor(e.target.value)}
                  disabled={majorsLoading}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sdsu-red focus:border-sdsu-red disabled:opacity-50"
                >
                  {majors.some((m) => m.verified) ? (
                    <>
                      <optgroup label="Fully Verified">
                        {majors.filter((m) => m.verified).map((m) => (
                          <option key={m.code} value={m.code}>{m.name}</option>
                        ))}
                      </optgroup>
                      <optgroup label="All Majors (auto-generated, beta)">
                        {majors.filter((m) => !m.verified).map((m) => (
                          <option key={m.code} value={m.code}>{m.name}</option>
                        ))}
                      </optgroup>
                    </>
                  ) : (
                    majors.map((m) => (
                      <option key={m.code} value={m.code}>{m.name}</option>
                    ))
                  )}
                </select>
                {majorsError && (
                  <p className="text-xs text-amber-600 mt-1">
                    Couldn't reach the catalog service — showing a limited list.
                    Check that the backend is running, then reload.
                  </p>
                )}
                {!majors.find((m) => m.code === major)?.verified &&
                  majors.find((m) => m.code === major) && (
                    <p className="text-xs text-amber-600 mt-1">
                      Auto-generated from the catalog — requirements may be incomplete.
                    </p>
                  )}
              </div>

              {/* Completed courses */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Completed Courses{" "}
                  <span className="text-gray-400 font-normal">(optional)</span>
                </label>
                <textarea
                  value={completedInput}
                  onChange={(e) => setCompletedInput(e.target.value)}
                  placeholder={"CS 150\nCS 150L\nMATH 150\nMATH 151"}
                  rows={4}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-sdsu-red focus:border-sdsu-red resize-none"
                />
                <p className="text-xs text-gray-400 mt-1">
                  One course code per line, or comma-separated (e.g. CS 150, MATH 150)
                </p>
              </div>

              {/* Start term */}
              <div className="flex gap-3">
                <div className="flex-1">
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Start Semester
                  </label>
                  <select
                    value={startSemester}
                    onChange={(e) => setStartSemester(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sdsu-red focus:border-sdsu-red"
                  >
                    <option value="Fall">Fall</option>
                    <option value="Spring">Spring</option>
                  </select>
                </div>
                <div className="flex-1">
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Start Year
                  </label>
                  <select
                    value={startYear}
                    onChange={(e) => setStartYear(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sdsu-red focus:border-sdsu-red"
                  >
                    {YEARS.map((y) => (
                      <option key={y} value={y}>
                        {y}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Units per semester */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Max Units Per Semester:{" "}
                  <span className="text-sdsu-red font-bold">{maxUnits}</span>
                </label>
                <input
                  type="range"
                  min={12}
                  max={21}
                  value={maxUnits}
                  onChange={(e) => setMaxUnits(Number(e.target.value))}
                  className="w-full accent-sdsu-red"
                />
                <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                  <span>12 (lighter)</span>
                  <span>15 (default)</span>
                  <span>21 (heavy)</span>
                </div>
              </div>

              {/* Graduation requirements */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Include in Plan
                </label>
                <div className="space-y-2">
                  <label className="flex items-start gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={includeGe}
                      onChange={(e) => setIncludeGe(e.target.checked)}
                      className="mt-0.5 accent-sdsu-red"
                    />
                    <span className="text-sm text-gray-700">
                      <span className="font-medium">General Education</span>
                      <span className="text-gray-400"> — 43 units across Areas 1–6 and Upper-Division Explorations</span>
                    </span>
                  </label>
                  <label className="flex items-start gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={includeAi}
                      onChange={(e) => setIncludeAi(e.target.checked)}
                      className="mt-0.5 accent-sdsu-red"
                    />
                    <span className="text-sm text-gray-700">
                      <span className="font-medium">American Institutions</span>
                      <span className="text-gray-400"> — US History &amp; Government (HIST 140 or POLS 101, required by CA law)</span>
                    </span>
                  </label>
                </div>
                <p className="text-xs text-gray-400 mt-2">
                  GWAR is always included · Cultural Diversity is satisfied by GE Area 6
                </p>
              </div>

              {/* Error */}
              {error && (
                <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
                  {error}
                </div>
              )}

              {/* Submit */}
              <button
                type="submit"
                disabled={loading}
                className="w-full bg-sdsu-red text-white font-semibold py-2.5 rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm"
              >
                {loading ? "Generating Plan…" : "Generate My Plan →"}
              </button>
            </form>
          </div>
        </div>
      </main>
    </div>
  );
}
