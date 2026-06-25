import { DragDropContext } from "@hello-pangea/dnd";
import SemesterColumn from "./SemesterColumn.jsx";
import { suggestedTerms } from "../utils/terms.js";

export default function PlanGrid({
  semesters,
  onDragEnd,
  onCourseClick,
  maxUnits,
  adjusting,
  onAddTerm,
  onRemoveTerm,
}) {
  const suggestions = onAddTerm ? suggestedTerms(semesters) : [];

  return (
    <DragDropContext onDragEnd={onDragEnd}>
      <div
        className={`flex gap-4 overflow-x-auto pb-4 pt-2 scrollbar-thin transition-opacity ${
          adjusting ? "opacity-60 pointer-events-none" : ""
        }`}
      >
        {semesters.map((sem) => (
          <SemesterColumn
            key={`${sem.semester}-${sem.year}`}
            semester={sem}
            maxUnits={maxUnits}
            onCourseClick={onCourseClick}
            adjusting={adjusting}
            onRemoveTerm={onRemoveTerm}
          />
        ))}

        {/* Add an optional Summer/Winter term to lighten Fall/Spring loads. */}
        {onAddTerm && (
          <div className="flex flex-col w-48 shrink-0">
            <h3 className="text-sm font-bold text-gray-400 mb-2">Add a term</h3>
            <div className="flex-1 rounded-lg border-2 border-dashed border-gray-200 p-2 space-y-2">
              {suggestions.length === 0 && (
                <p className="text-xs text-gray-300 text-center pt-4">
                  No terms to add
                </p>
              )}
              {suggestions.map((t) => (
                <button
                  key={`${t.semester}-${t.year}`}
                  onClick={() => onAddTerm(t.semester, t.year)}
                  className="w-full text-left rounded-md border border-gray-200 hover:border-sdsu-red hover:bg-red-50 px-3 py-2 text-xs font-medium text-gray-600 transition-colors"
                >
                  + {t.semester} {t.year}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </DragDropContext>
  );
}
