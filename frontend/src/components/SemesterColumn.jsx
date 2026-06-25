import { Droppable } from "@hello-pangea/dnd";
import CourseCard from "./CourseCard.jsx";

const DEFAULT_MAX_UNITS = 15;

const OPTIONAL_TERMS = new Set(["Summer", "Winter"]);

export default function SemesterColumn({ semester, onCourseClick, maxUnits = DEFAULT_MAX_UNITS, adjusting = false, onRemoveTerm }) {
  const { semester: term, year, courses, total_units } = semester;
  const semId = `${term}-${year}`;
  const pct = Math.min(100, (total_units / maxUnits) * 100);
  const overCap = total_units > maxUnits;
  const isOptional = OPTIONAL_TERMS.has(term);
  const canRemove = isOptional && courses.length === 0 && onRemoveTerm;

  return (
    <div className="flex flex-col w-52 shrink-0">
      {/* Header */}
      <div className="mb-2">
        <div className="flex items-center gap-1.5">
          <h3 className="text-sm font-bold text-gray-800">
            {term} {year}
          </h3>
          {isOptional && (
            <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-orange-100 text-orange-700">
              optional
            </span>
          )}
          {canRemove && (
            <button
              onClick={() => onRemoveTerm(term, year)}
              className="ml-auto text-gray-300 hover:text-red-500 text-sm leading-none"
              aria-label={`Remove ${term} ${year}`}
              title="Remove this empty term"
            >
              ×
            </button>
          )}
        </div>
        <div className="flex items-center gap-2 mt-1">
          {/* Unit load bar */}
          <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                overCap ? "bg-red-500" : pct > 80 ? "bg-amber-400" : "bg-emerald-400"
              }`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <span
            className={`text-xs font-medium tabular-nums ${
              overCap ? "text-red-600" : "text-gray-500"
            }`}
          >
            {total_units}u
          </span>
        </div>
      </div>

      {/* Drop zone */}
      <Droppable droppableId={semId} isDropDisabled={adjusting}>
        {(provided, snapshot) => (
          <div
            ref={provided.innerRef}
            {...provided.droppableProps}
            className={[
              "flex-1 min-h-32 rounded-lg border-2 border-dashed p-2 space-y-2 transition-colors",
              snapshot.isDraggingOver
                ? "border-sdsu-red bg-red-50"
                : "border-gray-200 bg-white",
            ].join(" ")}
          >
            {courses.map((course, index) => (
              <CourseCard
                key={course.course_code}
                course={course}
                index={index}
                onClick={onCourseClick}
              />
            ))}
            {provided.placeholder}
            {courses.length === 0 && !snapshot.isDraggingOver && (
              <p className="text-xs text-gray-300 text-center pt-4">
                Drop courses here
              </p>
            )}
          </div>
        )}
      </Droppable>
    </div>
  );
}
