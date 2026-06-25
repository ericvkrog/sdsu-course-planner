import { Draggable } from "@hello-pangea/dnd";

// Slot roles that are a *choice* the student can change (vs a fixed requirement).
const ROLE_META = {
  elective: { label: "Elective", chip: "bg-violet-100 text-violet-700" },
  ge: { label: "GE", chip: "bg-sky-100 text-sky-700" },
  grad: { label: "Grad Req", chip: "bg-teal-100 text-teal-700" },
  free: { label: "Free Elective", chip: "bg-amber-100 text-amber-700" },
};

// Fallback when the backend didn't tag a role (e.g. after an untagged adjust).
function roleOf(course) {
  if (course.role) return course.role;
  const c = course.course_code;
  if (c.startsWith("FREE ")) return "free";
  if (c.startsWith("GE ")) return "ge";
  if (c.startsWith("GR ")) return "grad";
  return "requirement";
}

export default function CourseCard({ course, index, onClick }) {
  const deptColor = deptToColor(course.department);
  const role = roleOf(course);
  const meta = ROLE_META[role];           // undefined for fixed requirements
  const isSlot = !!meta;

  return (
    <Draggable draggableId={course.course_code} index={index}>
      {(provided, snapshot) => (
        <div
          ref={provided.innerRef}
          {...provided.draggableProps}
          {...provided.dragHandleProps}
          onClick={() => onClick?.(course)}
          className={[
            "group relative rounded-md px-3 py-2 cursor-pointer select-none transition-shadow",
            // Choice slots get a dashed accent border so they read as "changeable".
            isSlot ? "border-2 border-dashed bg-violet-50/30" : "border bg-white",
            snapshot.isDragging
              ? "shadow-lg ring-2 ring-sdsu-red ring-opacity-50 rotate-1"
              : isSlot
              ? "shadow-sm hover:shadow-md border-violet-300"
              : "shadow-sm hover:shadow-md border-gray-200",
          ].join(" ")}
        >
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="flex items-center gap-1 mb-1">
                <span className={`inline-block text-xs font-bold px-1.5 py-0.5 rounded ${deptColor}`}>
                  {course.department}
                </span>
                {meta && (
                  <span className={`inline-block text-[10px] font-semibold px-1.5 py-0.5 rounded ${meta.chip}`}>
                    {meta.label}
                  </span>
                )}
              </div>
              <p className="text-xs font-semibold text-gray-900 leading-tight truncate">
                {course.course_code}
              </p>
              <p className="text-xs text-gray-500 leading-tight line-clamp-2 mt-0.5">
                {course.title}
              </p>
            </div>
            <div className="shrink-0 flex flex-col items-end gap-1 mt-0.5">
              <span className="text-xs font-medium text-gray-400">{course.units}u</span>
              {isSlot && (
                <span className="text-[10px] text-violet-500 opacity-0 group-hover:opacity-100 transition-opacity">
                  choose ›
                </span>
              )}
            </div>
          </div>
        </div>
      )}
    </Draggable>
  );
}

function deptToColor(dept) {
  const palettes = [
    "bg-blue-100 text-blue-700",
    "bg-green-100 text-green-700",
    "bg-purple-100 text-purple-700",
    "bg-amber-100 text-amber-700",
    "bg-teal-100 text-teal-700",
    "bg-pink-100 text-pink-700",
    "bg-indigo-100 text-indigo-700",
    "bg-orange-100 text-orange-700",
  ];
  let hash = 0;
  for (let i = 0; i < dept.length; i++) {
    hash = (hash * 31 + dept.charCodeAt(i)) & 0xffff;
  }
  return palettes[hash % palettes.length];
}
