import { useEffect, useState } from "react";
import { getCourse, getPrereqGraph, getSwapOptions } from "../api/client.js";
import PrereqGraph from "./PrereqGraph.jsx";

export default function CourseDrawer({
  course,
  onClose,
  // Optional swap context — when provided, the drawer offers legal elective swaps.
  major,
  plan,
  slot,            // { semester, year } the course occupies in the plan
  completedCourses = [],
  maxUnits = 15,
  onSwap,          // ({ fromCode, toCode, semester, year }) => Promise
}) {
  const [detail, setDetail] = useState(null);
  const [graph, setGraph] = useState(null);
  const [loading, setLoading] = useState(false);
  const [swap, setSwap] = useState(null);        // SwapOptionsResponse or null
  const [swapping, setSwapping] = useState(null); // course_code being applied
  const [query, setQuery] = useState("");         // search text for FREE/GWAR slots

  // Load course detail + prereq graph on open.
  useEffect(() => {
    if (!course) return;
    setDetail(null);
    setGraph(null);
    setSwap(null);
    setQuery("");
    setLoading(true);

    Promise.allSettled([
      getCourse(course.course_code),
      getPrereqGraph(course.course_code),
    ]).then(([detailResult, graphResult]) => {
      setDetail(
        detailResult.status === "fulfilled"
          ? detailResult.value
          : { ...course, prerequisites: [] }
      );
      setGraph(
        graphResult.status === "fulfilled"
          ? graphResult.value
          : { nodes: [], edges: [] }
      );
    }).finally(() => setLoading(false));
  }, [course]);

  // Fetch slot fill options whenever the slot or search query changes.
  useEffect(() => {
    if (!course || !major || !plan || !slot) return;
    getSwapOptions({
      major,
      plan,
      course_code: course.course_code,
      semester: slot.semester,
      year: slot.year,
      completed_courses: completedCourses,
      max_units_per_semester: maxUnits,
      query: query || undefined,
    })
      .then((res) => setSwap(res))
      .catch(() => setSwap(null));
  }, [course, query]);

  if (!course) return null;

  async function handleSwap(toCode) {
    if (!onSwap || !slot) return;
    setSwapping(toCode);
    try {
      await onSwap({
        fromCode: course.course_code,
        toCode,
        semester: slot.semester,
        year: slot.year,
      });
      onClose();
    } catch {
      setSwapping(null);
    }
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/20 z-30"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer */}
      <aside className="fixed right-0 top-0 h-full w-96 bg-white shadow-2xl z-40 flex flex-col">
        {/* Header */}
        <div className="flex items-start justify-between p-5 border-b">
          <div>
            <p className="text-xs font-semibold text-sdsu-red uppercase tracking-wide">
              {course.department}
            </p>
            <h2 className="text-lg font-bold text-gray-900 leading-tight">
              {course.course_code}
            </h2>
            <p className="text-sm text-gray-600 mt-0.5">{course.title}</p>
          </div>
          <button
            onClick={onClose}
            className="ml-4 text-gray-400 hover:text-gray-600 text-2xl leading-none mt-1"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {loading && (
            <p className="text-sm text-gray-400 animate-pulse">Loading…</p>
          )}

          {/* Quick stats */}
          <div className="flex gap-3 text-sm">
            <Chip label={`${course.units} units`} />
            {course.offered_fall && <Chip label="Fall" />}
            {course.offered_spring && <Chip label="Spring" />}
            {course.grading_method && <Chip label={course.grading_method} />}
          </div>

          {/* Slot fill / swap options (electives, AI, GWAR, free) */}
          {swap && swap.slot_type !== "requirement" && (
            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Choose a course for this slot
              </h4>
              {swap.area && (
                <p className="text-xs text-gray-400 mb-2">{swap.area}</p>
              )}

              {/* GE slots: picking the specific course needs data we haven't scraped yet. */}
              {swap.needs_data ? (
                <div className="rounded-md bg-sky-50 border border-sky-200 px-3 py-2 text-xs text-sky-800">
                  {swap.hint || "Specific course selection is coming soon."}
                  {detail?.notes && (
                    <p className="text-sky-700 mt-1">{detail.notes}</p>
                  )}
                </div>
              ) : (
                <>
                  {/* Search box for open-ended slots (free electives, GWAR). */}
                  {swap.search && (
                    <input
                      type="text"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder={swap.hint || "Type to search courses…"}
                      className="w-full mb-2 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-sdsu-red"
                    />
                  )}
                  {swap.options.length === 0 ? (
                    <p className="text-xs text-gray-400">
                      {swap.search
                        ? query
                          ? "No matching courses you can take here."
                          : "Type above to find a course."
                        : "No legal alternatives at this point in your plan."}
                    </p>
                  ) : (
                    <ul className="space-y-1.5">
                      {swap.options.map((o) => (
                        <li key={o.course_code}>
                          <button
                            onClick={() => handleSwap(o.course_code)}
                            disabled={!!swapping}
                            className={[
                              "w-full text-left rounded-md border px-3 py-2 transition-colors",
                              "hover:border-sdsu-red hover:bg-red-50 disabled:opacity-50 disabled:cursor-not-allowed",
                              o.eligible === false ? "border-gray-200 bg-gray-50" : "border-gray-200",
                            ].join(" ")}
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="font-mono text-xs font-semibold text-gray-900">
                                {o.course_code}
                              </span>
                              <span className="text-xs text-gray-400">
                                {swapping === o.course_code ? "Swapping…" : `${o.units}u`}
                              </span>
                            </div>
                            <p className="text-xs text-gray-500 leading-tight truncate mt-0.5">
                              {o.title}
                            </p>
                            {o.eligible === false && o.note && (
                              <p className="text-xs text-amber-600 mt-0.5">⚠ {o.note}</p>
                            )}
                            {o.eligible !== false && !o.fits_budget && (
                              <p className="text-xs text-amber-600 mt-0.5">
                                puts this semester above your unit target
                              </p>
                            )}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              )}
            </div>
          )}

          {/* Description */}
          {detail?.description && (
            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Description
              </h4>
              <p className="text-sm text-gray-700 leading-relaxed">
                {detail.description}
              </p>
            </div>
          )}

          {/* Prerequisites */}
          {detail?.prerequisites?.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Prerequisites
              </h4>
              <ul className="space-y-1">
                {detail.prerequisites.map((p, i) => (
                  <li key={i} className="text-sm text-gray-700 flex gap-2">
                    {p.prereq_code && (
                      <span className="font-mono text-xs bg-gray-100 px-1.5 py-0.5 rounded">
                        {p.prereq_code}
                      </span>
                    )}
                    {p.min_standing && (
                      <span className="text-xs text-amber-700">
                        {p.min_standing} standing required
                      </span>
                    )}
                    {p.prereq_type === "recommended" && (
                      <span className="text-xs text-gray-400">(recommended)</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Prereq graph */}
          {graph && (
            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Prerequisite Chain
              </h4>
              <div className="border rounded-lg overflow-hidden bg-gray-50">
                <PrereqGraph graph={graph} highlightCode={course.course_code} />
              </div>
            </div>
          )}

          {detail?.notes && (
            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Notes
              </h4>
              <p className="text-sm text-gray-600">{detail.notes}</p>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}

function Chip({ label }) {
  return (
    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-700">
      {label}
    </span>
  );
}
