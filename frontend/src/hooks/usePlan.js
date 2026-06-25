import { useState, useCallback } from "react";
import { adjustPlan as apiAdjust, swapCourse as apiSwap } from "../api/client.js";
import { sortSemesters } from "../utils/terms.js";

export function usePlan(initialPlan, completedCourses = [], maxUnits = 15, major = null) {
  const [plan, setPlan] = useState(initialPlan);
  const [adjusting, setAdjusting] = useState(false);
  const [error, setError] = useState(null);

  const moveCourse = useCallback(
    async ({ courseCode, fromSemester, fromYear, toSemester, toYear }) => {
      setAdjusting(true);
      setError(null);
      try {
        const updated = await apiAdjust({
          plan,
          course_code: courseCode,
          from_semester: fromSemester,
          from_year: fromYear,
          to_semester: toSemester,
          to_year: toYear,
          completed_courses: completedCourses,
          max_units_per_semester: maxUnits,
          major,
        });
        setPlan(updated);
      } catch (err) {
        setError(err.message);
      } finally {
        setAdjusting(false);
      }
    },
    [plan, completedCourses, maxUnits, major]
  );

  const swapCourse = useCallback(
    async ({ fromCode, toCode, semester, year }) => {
      setAdjusting(true);
      setError(null);
      try {
        const updated = await apiSwap({
          plan,
          from_code: fromCode,
          to_code: toCode,
          semester,
          year,
          completed_courses: completedCourses,
          max_units_per_semester: maxUnits,
          major,
        });
        setPlan(updated);
        return updated;
      } catch (err) {
        setError(err.message);
        throw err;
      } finally {
        setAdjusting(false);
      }
    },
    [plan, completedCourses, maxUnits, major]
  );

  // Add an optional empty term (Summer/Winter) as a drag target. Client-side only —
  // no validation needed for an empty term; dragging into it later hits /plan/adjust.
  const addTerm = useCallback((semester, year) => {
    setPlan((p) => {
      if (p.semesters.some((s) => s.semester === semester && s.year === year)) return p;
      const semesters = sortSemesters([
        ...p.semesters,
        { semester, year, courses: [], total_units: 0 },
      ]);
      return { ...p, semesters };
    });
  }, []);

  // Remove an optional term — only allowed when it's empty.
  const removeTerm = useCallback((semester, year) => {
    setPlan((p) => ({
      ...p,
      semesters: p.semesters.filter(
        (s) => !(s.semester === semester && s.year === year && s.courses.length === 0)
      ),
    }));
  }, []);

  return { plan, setPlan, moveCourse, swapCourse, addTerm, removeTerm, adjusting, error, setError };
}
