import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import PlanGrid from "../components/PlanGrid.jsx";
import ConflictAlert from "../components/ConflictAlert.jsx";
import CourseDrawer from "../components/CourseDrawer.jsx";
import { usePlan } from "../hooks/usePlan.js";

export default function Plan() {
  const location = useLocation();
  const navigate = useNavigate();

  // If the user lands directly (no state), redirect to onboarding.
  if (!location.state?.plan) {
    navigate("/", { replace: true });
    return null;
  }

  const initialPlan = location.state.plan;
  const settings = location.state.settings || {};
  const completedCourses = location.state.completedCourses || [];

  const { plan, moveCourse, swapCourse, addTerm, removeTerm, adjusting, error, setError } = usePlan(
    initialPlan,
    completedCourses,
    settings.maxUnits ?? 15,
    settings.major
  );
  const [selectedCourse, setSelectedCourse] = useState(null);
  const [conflictsDismissed, setConflictsDismissed] = useState(false);

  // Locate which semester a course currently sits in → { semester, year }.
  function findSlot(p, code) {
    for (const s of p.semesters) {
      if (s.courses.some((c) => c.course_code === code)) {
        return { semester: s.semester, year: s.year };
      }
    }
    return null;
  }

  // Parse droppableId "Fall-2025" → { semester, year }
  function parseDropId(id) {
    const idx = id.lastIndexOf("-");
    return {
      semester: id.slice(0, idx),
      year: Number(id.slice(idx + 1)),
    };
  }

  async function handleDragEnd(result) {
    const { draggableId, source, destination } = result;
    if (!destination) return;
    if (
      source.droppableId === destination.droppableId &&
      source.index === destination.index
    )
      return;

    const from = parseDropId(source.droppableId);
    const to = parseDropId(destination.droppableId);

    await moveCourse({
      courseCode: draggableId,
      fromSemester: from.semester,
      fromYear: from.year,
      toSemester: to.semester,
      toYear: to.year,
    });
  }

  const totalPlaced = plan.semesters.reduce(
    (acc, s) => acc + s.courses.length,
    0
  );
  const totalUnits = plan.semesters.reduce(
    (acc, s) => acc + s.total_units,
    0
  );
  const visibleConflicts =
    !conflictsDismissed && plan.conflicts.length > 0 ? plan.conflicts : [];
  // Only hard errors count as "conflicts" in the stats bar; soft warnings
  // (e.g. a semester above the unit target) are not failures.
  const errorCount = plan.conflicts.filter((c) => c.severity !== "warning").length;

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Nav */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-20">
        <div className="max-w-full px-6 py-3 flex items-center gap-4">
          <button
            onClick={() => navigate("/")}
            className="text-sdsu-red text-sm font-medium hover:underline"
          >
            ← New Plan
          </button>
          <div className="h-5 w-px bg-gray-200" />
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 bg-sdsu-red rounded-full flex items-center justify-center">
              <span className="text-white font-black text-xs">S</span>
            </div>
            <span className="font-bold text-gray-900 text-sm">
              {settings.majorName || "Computer Science, B.S."} — 4-Year Plan
            </span>
          </div>
          <div className="ml-auto flex items-center gap-4 text-sm text-gray-500">
            <span>{totalPlaced} courses</span>
            <span>{totalUnits} units</span>
            {adjusting && (
              <span className="text-sdsu-red animate-pulse">Saving…</span>
            )}
          </div>
        </div>
      </header>

      <main className="flex-1 flex flex-col px-6 py-4">
        {/* Conflicts */}
        {visibleConflicts.length > 0 && (
          <ConflictAlert
            conflicts={visibleConflicts}
            onDismiss={() => setConflictsDismissed(true)}
          />
        )}

        {/* Adjust error */}
        {error && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800 mb-4 flex justify-between">
            <span>Move failed: {error}</span>
            <button onClick={() => setError(null)} className="ml-4 font-medium">
              ×
            </button>
          </div>
        )}

        {/* Stats bar */}
        <div className="flex gap-6 mb-4 text-xs text-gray-500">
          <div>
            <span className="font-semibold text-gray-700">{totalPlaced}</span>{" "}
            courses scheduled
          </div>
          <div>
            <span className="font-semibold text-gray-700">{totalUnits}</span>{" "}
            total units
          </div>
          {errorCount > 0 && (
            <div className="text-red-600">
              <span className="font-semibold">{errorCount}</span>{" "}
              conflict{errorCount !== 1 ? "s" : ""}
            </div>
          )}
        </div>

        {/* Plan grid */}
        <PlanGrid
          semesters={plan.semesters}
          onDragEnd={handleDragEnd}
          onCourseClick={setSelectedCourse}
          maxUnits={settings.maxUnits}
          adjusting={adjusting}
          onAddTerm={addTerm}
          onRemoveTerm={removeTerm}
        />

        <p className="text-xs text-gray-400 mt-4">
          Drag courses between semesters to adjust your plan. Click any course
          for details.
        </p>
      </main>

      {/* Course detail drawer */}
      {selectedCourse && (
        <CourseDrawer
          course={selectedCourse}
          onClose={() => setSelectedCourse(null)}
          major={settings.major}
          plan={plan}
          slot={findSlot(plan, selectedCourse.course_code)}
          completedCourses={completedCourses}
          maxUnits={settings.maxUnits ?? 15}
          onSwap={swapCourse}
        />
      )}
    </div>
  );
}
